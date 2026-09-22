param([string]$Destination = '', [int]$Port = 8767)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'desktop-config.ps1')
$Destination = Resolve-JevSshTarget $Destination
try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 3
    if ($health.status -eq 'ok' -and $health.model -eq 'kalm-jev-nano') {
        Write-Output "KaLM Nano is already reachable on port $Port."
        exit 0
    }
} catch {}
# Foreground tunnel: Ctrl+C closes only this forward. Existing text-model forwards are untouched.
& ssh -N -T -o BatchMode=yes -o StrictHostKeyChecking=yes -o ExitOnForwardFailure=yes `
    -o ConnectTimeout=10 -o ServerAliveInterval=30 -o ServerAliveCountMax=3 `
    -L "127.0.0.1:${Port}:127.0.0.1:${Port}" $Destination
exit $LASTEXITCODE
