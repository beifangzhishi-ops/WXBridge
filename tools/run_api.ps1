# Launch the same local read-only Tailscale API service on either Windows node.
# Secret remains in an ignored local file, never in Git or command arguments.
param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('6v', 'noha')]
    [string] $Node,
    [Parameter(Mandatory=$true)]
    [string] $Bind
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$tokenFile = Join-Path $root '.state\api-token.txt'
if (-not (Test-Path -LiteralPath $tokenFile)) {
    throw 'api_token_missing: provision the private .state/api-token.txt locally first'
}
$secret = (Get-Content -LiteralPath $tokenFile -Raw -ErrorAction Stop).Trim()
if ($secret.Length -lt 24) { throw 'api_token_too_short' }

$python = if ($Node -eq '6v') {
    Join-Path $root '.vendor\replica-db39\Scripts\python.exe'
} else {
    Join-Path $root '.venv\Scripts\python.exe'
}
if (-not (Test-Path -LiteralPath $python)) { throw 'api_python_not_installed' }
$env:WXBRIDGE_API_TOKEN = $secret
$env:WXBRIDGE_NODE_ID = $Node
$env:PYTHONPATH = Join-Path $root 'src'
try {
    Push-Location $root
    & $python -m wxbridge.api --bind $Bind --port 18763
    exit $LASTEXITCODE
} finally {
    Pop-Location
    Remove-Item Env:\WXBRIDGE_API_TOKEN -ErrorAction SilentlyContinue
}
