# Unload only this project's staged KaLM listener and close its recorded SSH forward.
[CmdletBinding()]
param(
    [ValidatePattern('^[A-Za-z0-9_][A-Za-z0-9_.-]*@[A-Za-z0-9_][A-Za-z0-9_.:-]*$')]
    [string]$SshTarget = '',
    [string]$RemoteRuntime = '',
    [ValidateRange(1024, 65535)][int]$LocalPort = 8767,
    [ValidateRange(1024, 65535)][int]$RemotePort = 8767,
    [switch]$InspectOnly
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'desktop-config.ps1')
$SshTarget = Resolve-JevSshTarget $SshTarget
$runtimeLiteral = if ($RemoteRuntime) { "'" + $RemoteRuntime.Replace("'", "''") + "'" } else { "(Join-Path `$env:USERPROFILE 'jev-browserUse-runtime')" }
$remoteScript = @'
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try {
    $runtime = [IO.Path]::GetFullPath(__RUNTIME__)
    $server = Join-Path $runtime 'scripts\serve_kalm.py'
    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort __PORT__ -ErrorAction SilentlyContinue)
    $owners = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
    if ($owners.Count -eq 0) { Write-Output 'KaLM is already stopped.'; exit 0 }
    if ($owners.Count -ne 1) { throw 'Multiple listener processes; no processes stopped.' }
    $ownedProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($owners[0])"
    $scriptPattern = '(?i)(?:^|\s)"?' + [regex]::Escape($server) + '"?(?:\s|$)'
    $portPattern = '(?:^|\s)"?--port"?\s+"?__PORT__"?(?:\s|$)'
    if ($ownedProcess.Name -ne 'python.exe' -or $ownedProcess.CommandLine -notmatch $scriptPattern -or $ownedProcess.CommandLine -notmatch $portPattern) {
        throw 'Listener does not match this project runtime and port; no processes stopped.'
    }
    Write-Output "Verified project KaLM listener: process $($ownedProcess.ProcessId), port __PORT__."
    if (__INSPECT__) { exit 0 }
    Stop-Process -Id $ownedProcess.ProcessId -ErrorAction Stop
    Write-Output 'KaLM unloaded. The existing text model was left running.'
} catch { Write-Output $_.Exception.Message; exit 1 }
'@
$remoteScript = $remoteScript.Replace('__RUNTIME__', $runtimeLiteral).Replace('__PORT__', [string]$RemotePort)
$remoteScript = $remoteScript.Replace('__INSPECT__', $(if ($InspectOnly) { '$true' } else { '$false' }))
$encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($remoteScript))
& ssh -T -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 $SshTarget powershell -NoProfile -NonInteractive -EncodedCommand $encoded
if ($LASTEXITCODE -ne 0) { throw 'Remote stop failed; the local tunnel was left untouched.' }
if ($InspectOnly) { return }
$pidFile = Join-Path $PSScriptRoot '..\artifacts\desktop-staging\ssh-kalm.pid'
if (Test-Path -LiteralPath $pidFile) {
    $tunnelId = [int](Get-Content -LiteralPath $pidFile -Raw).Trim()
    $tunnel = Get-CimInstance Win32_Process -Filter "ProcessId=$tunnelId"
    if ($tunnel) {
        $forward = "127.0.0.1:${LocalPort}:127.0.0.1:${RemotePort}"
        if ($tunnel.Name -ne 'ssh.exe' -or -not $tunnel.CommandLine.Contains($forward) -or -not $tunnel.CommandLine.Contains($SshTarget)) {
            throw 'Recorded SSH PID belongs to a different command; it was left untouched.'
        }
        Stop-Process -Id $tunnelId -ErrorAction SilentlyContinue
    }
}
Write-Output 'Project desktop runtime stopped.'
