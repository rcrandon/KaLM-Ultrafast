# Resolve only the SSH destination from local configuration; never execute .env contents.
function Resolve-JevSshTarget([string]$ExplicitTarget) {
    $target = $ExplicitTarget
    if (-not $target) { $target = $env:JEV_SSH_TARGET }
    if (-not $target) {
        $envFile = Join-Path $PSScriptRoot '..\.env'
        if (Test-Path -LiteralPath $envFile -PathType Leaf) {
            foreach ($line in [IO.File]::ReadAllLines($envFile)) {
                if ($line -match '^\s*JEV_SSH_TARGET\s*=(.*)$') {
                    $target = $Matches[1].Trim().Trim('"').Trim("'")
                    break
                }
            }
        }
    }
    if (-not $target -or $target -notmatch '^[A-Za-z0-9_][A-Za-z0-9_.-]*@[A-Za-z0-9_][A-Za-z0-9_.:-]*$') {
        throw 'Set JEV_SSH_TARGET=user@desktop in your ignored .env, or supply an explicit SSH destination.'
    }
    return $target
}
