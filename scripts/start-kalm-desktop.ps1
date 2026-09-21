# Run on the desktop, or through start-desktop.ps1. Keep this SSH session open.
[CmdletBinding()]
param(
    [string]$RuntimeRoot = (Join-Path $env:USERPROFILE 'jev-browserUse-runtime'),
    [ValidateRange(1024, 65535)][int]$Port = 8767,
    [ValidateRange(1, 64)][int]$Threads = 4
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

function ConvertTo-WindowsArgument([string]$Value) {
    # Start-Process joins its ArgumentList; preserve spaces, quotes and trailing slashes.
    $escaped = [regex]::Replace($Value, '(\\*)"', '$1$1\"')
    $escaped = [regex]::Replace($escaped, '(\\+)$', '$1$1')
    return '"' + $escaped + '"'
}

$listeners = [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()
if ($listeners | Where-Object { $_.Port -eq $Port }) {
    throw "Desktop port $Port is already in use. Existing services were left running."
}
if (-not (Test-Path -LiteralPath $RuntimeRoot -PathType Container)) {
    throw "Desktop runtime is missing: $RuntimeRoot. Stage the model environment first."
}
$RuntimeRoot = (Resolve-Path -LiteralPath $RuntimeRoot).Path
$pythonExe = Join-Path $RuntimeRoot '.venv\Scripts\python.exe'
$serverScript = Join-Path $RuntimeRoot 'scripts\serve_kalm.py'
$modelPath = Join-Path $RuntimeRoot 'models\KaLM-Reranker-V1-Nano-R2-3902d6453ea915007dcbf88fbc8a1d7dd5f8df10'
$required = @($pythonExe, $serverScript, (Join-Path $RuntimeRoot 'jev_ultrafast\kalm_backend.py'))
$required += @('config.json', 'tokenizer.json', 'tokenizer_config.json', 'model.safetensors', 'kalm_reranker.py', 'kalm_reranker_utils.py') | ForEach-Object { Join-Path $modelPath $_ }
foreach ($path in $required) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required staged file is missing: $path"
    }
}

$env:OMP_NUM_THREADS = [string]$Threads
$env:MKL_NUM_THREADS = [string]$Threads
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:HF_HUB_DISABLE_TELEMETRY = '1'
$env:PYTHONUNBUFFERED = '1'
$serverArgs = @(
    $serverScript, '--model-path', $modelPath, '--device', 'cpu', '--dtype', 'float32',
    '--threads', [string]$Threads, '--query-max-length', '4096',
    '--document-max-length', '1024', '--decoder-max-length', '6144',
    '--port', [string]$Port, '--verify-readout', '--verification-output',
    (Join-Path $RuntimeRoot 'readout-parity.json')
)
$argumentLine = ($serverArgs | ForEach-Object { ConvertTo-WindowsArgument $_ }) -join ' '
$stdout = Join-Path $RuntimeRoot 'kalm.stdout.log'
$stderr = Join-Path $RuntimeRoot 'kalm.stderr.log'
$process = Start-Process -FilePath $pythonExe -ArgumentList $argumentLine -WorkingDirectory $RuntimeRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
$process.Id | Set-Content -LiteralPath (Join-Path $RuntimeRoot 'kalm.pid')
Write-Output "Starting KaLM Nano on desktop loopback port $Port; process $($process.Id)."
Write-Output "Readout verification runs before the server becomes ready. Logs: $stdout and $stderr"

# Windows OpenSSH terminates child processes when its session closes.
# Waiting here lets the local hidden SSH process hold the model service open.
$process.WaitForExit()
if ($process.ExitCode -ne 0) {
    if (Test-Path -LiteralPath $stderr) { Get-Content -LiteralPath $stderr -Tail 25 | Write-Output }
    throw "KaLM exited with code $($process.ExitCode). See $stderr"
}
Write-Output 'KaLM service stopped.'
