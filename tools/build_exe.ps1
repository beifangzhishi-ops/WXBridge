# Build one Windows EXE containing reviewed upstream read-only source files.
# The DB-core Python environment is separate from the upstream GUI environment.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $root '.vendor\replica-db39\Scripts\python.exe'
if (-not (Test-Path $python)) { throw 'missing_db_core_python_environment' }

$verify = @'
import hashlib, pathlib, subprocess, sys
root = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(root / 'src'))
from wxbridge.runtime import SOURCE_HASHES
vendor = root / '.vendor' / 'replica-src'
head = subprocess.check_output(['git', '-C', str(vendor), 'rev-parse', 'HEAD'], text=True).strip()
if head != '6e603974bbac3bda93d88bbd6995510ae2547f5c':
    raise SystemExit('unexpected_upstream_git_commit')
for name, expected in SOURCE_HASHES.items():
    source = vendor / 'wechatauto' / name
    if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
        raise SystemExit('modified_upstream_' + name)
print('upstream_sources_verified=' + str(len(SOURCE_HASHES)))
'@
$verify | & $python - $root
if ($LASTEXITCODE -ne 0) { throw 'cannot_build_unverified_upstream' }

$arguments = @(
    '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--console',
    '--name', 'WXBridge',
    '--contents-directory', '_wxbridge_runtime',
    '--paths', (Join-Path $root 'src'),
    '--specpath', (Join-Path $root 'build'),
    '--workpath', (Join-Path $root 'build\pyinstaller'),
    '--distpath', (Join-Path $root 'build\exe-out'),
    '--add-data', ((Join-Path $root 'pyproject.toml') + ';.'),
    '--add-data', ((Join-Path $root '.vendor\replica-src\wechatauto\db.py') + ';upstream\wechatauto'),
    '--add-data', ((Join-Path $root '.vendor\replica-src\wechatauto\media.py') + ';upstream\wechatauto'),
    '--add-data', ((Join-Path $root '.vendor\replica-src\wechatauto\moment.py') + ';upstream\wechatauto'),
    '--hidden-import', 'cryptography.hazmat.primitives.ciphers',
    '--hidden-import', 'zstandard',
    (Join-Path $root 'tools\exe_entry.py')
)
# db.py and media.py are intentionally imported from separately verified
# Python source files at runtime. Static analysis does not see their imports.
# Enumerate all standard-library top-level imports they require, without
# asking PyInstaller to collect the original wechatauto UI/send package.
$dynamic = @(
    'ctypes', 'glob', 'hashlib', 'hmac', 'json', 'os', 'queue',
    're', 'shutil', 'sqlite3', 'struct', 'sys', 'tempfile',
    'threading', 'time', 'unicodedata', 'typing', 'cryptography'
)
$arguments = $arguments[0..($arguments.Length - 2)] + @(
    foreach ($module in $dynamic) { '--hidden-import'; $module }
) + @((Join-Path $root 'tools\exe_entry.py'))
& $python @arguments
if ($LASTEXITCODE -ne 0) { throw 'pyinstaller_failed' }
$bundle = Join-Path $root 'build\exe-out\WXBridge'
if (-not (Test-Path (Join-Path $bundle 'WXBridge.exe'))) { throw 'exe_missing' }
Copy-Item -LiteralPath (Join-Path $bundle 'WXBridge.exe') -Destination (Join-Path $root 'WXBridge.exe') -Force
Copy-Item -LiteralPath (Join-Path $bundle '_wxbridge_runtime') -Destination $root -Recurse -Force
Write-Output ("built=" + (Join-Path $root 'WXBridge.exe'))
Write-Output ("runtime=" + (Join-Path $root '_wxbridge_runtime'))
