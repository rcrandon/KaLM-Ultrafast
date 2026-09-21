# Start the already-staged desktop model and its private SSH forward together.
[CmdletBinding()]
param(
    [ValidatePattern('^[A-Za-z0-9_][A-Za-z0-9_.-]*@[A-Za-z0-9_][A-Za-z0-9_.:-]*$')]
    [string]$SshTarget = 'User@192.168.1.200',
    [string]$RemoteRuntime = '',
    [ValidateRange(1024, 65535)][int]$LocalPort = 8767,
    [ValidateRange(1024, 65535)][int]$RemotePort = 8767,
    [ValidateRange(1, 64)][int]$Threads = 4,
    [ValidateRange(10, 600)][int]$StartupTimeoutSeconds = 120,
    [string]$LogDirectory = ''
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
if (-not $LogDirectory) { $LogDirectory = Join-Path $PSScriptRoot '..\artifacts\desktop-staging' }

function ConvertTo-WindowsArgument([string]$Value) {
    $escaped = [regex]::Replace($Value, '(\\*)"', '$1$1\"')
    $escaped = [regex]::Replace($escaped, '(\\+)$', '$1$1')
    return '"' + $escaped + '"'
}

$listeners = [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()
if ($listeners | Where-Object { $_.Port -eq $LocalPort }) {
    throw "Local port $LocalPort is already in use. The existing tunnel or service was left running."
}
$sshExe = (Get-Command ssh -ErrorAction Stop).Source
$remoteLauncher = Join-Path $PSScriptRoot 'start-kalm-desktop.ps1'
if (-not (Test-Path -LiteralPath $remoteLauncher -PathType Leaf)) {
    throw "Desktop launcher is missing: $remoteLauncher"
}
# Send the checked-in launcher itself, so restart does not depend on ignored artifacts.
# Send source through stdin rather than exceeding Windows' remote command-line limit.
$remoteScript = "& {`n" + (Get-Content -LiteralPath $remoteLauncher -Raw) + "`n} -Port $RemotePort -Threads $Threads"
if ($RemoteRuntime) {
    $remoteScript += " -RuntimeRoot '" + $RemoteRuntime.Replace("'", "''") + "'"
}
$remoteScript = "try {`n" + $remoteScript + "`n} catch { Write-Output `$_.Exception.Message; exit 1 }"
New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
$LogDirectory = (Resolve-Path -LiteralPath $LogDirectory).Path
$stdout = Join-Path $LogDirectory 'ssh-kalm.stdout.log'
$stderr = Join-Path $LogDirectory 'ssh-kalm.stderr.log'
$stdin = Join-Path $LogDirectory 'start-remote.ps1'
# The blank line terminates the compound command for PowerShell's stdin parser.
[IO.File]::WriteAllText($stdin, $remoteScript + "`n`n", [Text.UTF8Encoding]::new($false))
$sshArgs = @(
    '-T', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
    '-o', 'ConnectTimeout=10', '-o', 'ExitOnForwardFailure=yes',
    '-o', 'ServerAliveInterval=30', '-o', 'ServerAliveCountMax=3',
    '-L', "127.0.0.1:${LocalPort}:127.0.0.1:${RemotePort}",
    $SshTarget, 'powershell', '-NoProfile', '-NonInteractive', '-Command', '-'
)
$argumentLine = ($sshArgs | ForEach-Object { ConvertTo-WindowsArgument $_ }) -join ' '
$process = Start-Process -FilePath $sshExe -ArgumentList $argumentLine -WindowStyle Hidden -PassThru -RedirectStandardInput $stdin -RedirectStandardOutput $stdout -RedirectStandardError $stderr
$process.Id | Set-Content -LiteralPath (Join-Path $LogDirectory 'ssh-kalm.pid')
$endpoint = "http://127.0.0.1:$LocalPort"
Write-Output "Starting the desktop model and private tunnel; SSH process $($process.Id)."
Write-Output "Waiting for $endpoint/health. Logs: $stdout and $stderr"
$deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
try {
    while ((Get-Date) -lt $deadline) {
        $process.Refresh()
        if ($process.HasExited) {
            if (Test-Path -LiteralPath $stdout) { Get-Content -LiteralPath $stdout -Tail 15 | Write-Output }
            if (Test-Path -LiteralPath $stderr) { Get-Content -LiteralPath $stderr -Tail 10 | Write-Output }
            throw "Desktop SSH session exited with code $($process.ExitCode). Inspect the logs above."
        }
        try {
            $health = Invoke-RestMethod -Uri "$endpoint/health" -TimeoutSec 3
            $startupLog = Get-Content -LiteralPath $stdout -Raw -ErrorAction SilentlyContinue
            $startedRemote = $startupLog -match 'Starting KaLM Nano on desktop loopback port'
            if ($startedRemote -and $health.status -eq 'ok' -and $health.model -eq 'kalm-jev-nano') {
                Write-Output "KaLM Nano is ready at $endpoint. Keep SSH process $($process.Id) running."
                return
            }
        } catch { }
        Start-Sleep -Milliseconds 500
    }
    throw "KaLM did not become ready within $StartupTimeoutSeconds seconds. Inspect $stdout and $stderr, plus the desktop runtime logs."
} catch {
    # Only close the SSH process created by this invocation, never another service.
    $process.Refresh()
    if (-not $process.HasExited) { $process.Kill() }
    throw
}
