# Build the single Windows CLI frontend (API routing only, no local Reader).
# Each API host owns its own Python Reader and separately verified upstream.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $root '.vendor\replica-db39\Scripts\python.exe'
if (-not (Test-Path $python)) { throw 'missing_exe_build_python_environment' }

$arguments = @(
    '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--console',
    '--name', 'WXBridge',
    '--contents-directory', '_wxbridge_runtime',
    '--paths', (Join-Path $root 'src'),
    '--specpath', (Join-Path $root 'build'),
    '--workpath', (Join-Path $root 'build\pyinstaller'),
    '--distpath', (Join-Path $root 'build\exe-out'),
    (Join-Path $root 'tools\exe_entry.py')
)
& $python @arguments
if ($LASTEXITCODE -ne 0) { throw 'pyinstaller_failed' }

$bundle = Join-Path $root 'build\exe-out\WXBridge'
if (-not (Test-Path (Join-Path $bundle 'WXBridge.exe'))) { throw 'exe_missing' }
Copy-Item -LiteralPath (Join-Path $bundle 'WXBridge.exe') -Destination (Join-Path $root 'WXBridge.exe') -Force
# Remove old runtime contents; they previously contained embedded Reader and
# upstream libraries, which the new API-only client must not carry.
$runtime = Join-Path $root '_wxbridge_runtime'
if (Test-Path -LiteralPath $runtime) {
    $resolved = (Resolve-Path -LiteralPath $runtime).Path
    if ($resolved -ne (Join-Path $root '_wxbridge_runtime')) { throw 'unsafe_runtime_target' }
    Remove-Item -LiteralPath $runtime -Recurse -Force
}
Copy-Item -LiteralPath (Join-Path $bundle '_wxbridge_runtime') -Destination $root -Recurse -Force
Write-Output ("built=" + (Join-Path $root 'WXBridge.exe'))
Write-Output ("runtime=" + $runtime)
