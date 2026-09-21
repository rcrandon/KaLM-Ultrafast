param([int]$Port = 9222)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$chromeCandidates = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
)
$chromePath = $chromeCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $chromePath) { throw 'Google Chrome was not found. Install Chrome before starting the browser.' }
try {
    $null = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/json/version" -TimeoutSec 2
    Write-Output "A debugging browser is already available on port $Port."
    exit 0
} catch {}
$profilePath = Join-Path $projectRoot 'artifacts\chrome-profile'
$arguments = @(
    '--headless=new', '--no-first-run', '--no-default-browser-check',
    "--remote-debugging-port=$Port", '--remote-debugging-address=127.0.0.1',
    "--user-data-dir=`"$profilePath`"", 'about:blank'
)
$browserProcess = Start-Process -FilePath $chromePath -ArgumentList $arguments -WindowStyle Hidden -PassThru
Write-Output "Started the project browser (PID $($browserProcess.Id))."
Write-Output "Set BU_CDP_URL=http://127.0.0.1:$Port and BU_NAME=jev-browserUse in .env."
