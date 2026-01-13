# PowerShell Script to bundle the app for RHEL8
$ErrorActionPreference = "Stop"

$TARGET_DIR = "dist\ltremc_reporter_rhel8_bundle"
$WHEELS_DIR = "$TARGET_DIR\wheels"
$RELEASE_DIR = "release_builds"

Write-Host "=== Creating RHEL8 Deployment Bundle ===" -ForegroundColor Cyan

# 1. Clean/Create Dist Directory
if (Test-Path $TARGET_DIR) {
    Remove-Item -Recurse -Force $TARGET_DIR
}
if (-not (Test-Path $RELEASE_DIR)) {
    New-Item -ItemType Directory -Path $RELEASE_DIR | Out-Null
}
New-Item -ItemType Directory -Path $WHEELS_DIR | Out-Null

# 2. Copy Application Files
Write-Host "[-] Copying application files..."
$ExcludeItems = @(".venv", "__pycache__", ".git", "dist", "tests", "*.pyc", "*.ps1")
Get-ChildItem -Path . -Exclude $ExcludeItems | ForEach-Object {
    if ($_.Name -ne "dist" -and $_.Name -ne ".venv" -and $_.Name -ne ".git" -and $_.Name -ne "config.json") {
        Copy-Item -Path $_.FullName -Destination $TARGET_DIR -Recurse
    }
}

# 2b. Generate Clean config.json for Production
Write-Host "[-] Generating clean config.json..."
$CurrentConfig = Get-Content "config.json" | ConvertFrom-Json
$CleanConfig = @{
    version = $CurrentConfig.version
    input_directory = "uploads"
    recents = @()
}
$CleanConfig | ConvertTo-Json -Depth 2 | Set-Content "$TARGET_DIR\config.json"

# 3. Download Wheels for RHEL8 (manylinux2014_x86_64 / Python 3.6 - Legacy Support)
Write-Host "[-] Downloading Python 3.6 wheels for RHEL8 (Linux x86_64)..."
Write-Host "    Note: This requires internet access."

# Targeting Python 3.6 (RHEL8 Default)
# Using 'cp36m' abi (default for 3.6 on linux)
# Using special requirements file with pinned legacy versions
# Promoting manylinux1 for maximum compatibility with older pips
pip download `
    --dest $WHEELS_DIR `
    --only-binary=:all: `
    --platform manylinux1_x86_64 `
    --python-version 3.6.8 `
    --implementation cp `
    --abi cp36m `
    -r requirements.rhel8.python36.txt

# 3a. Force Download 'dataclasses' (Ignored by pip above because build env is > 3.6)
Write-Host "[-] Force downloading dataclasses backport for Python 3.6..."
pip download `
    --dest $WHEELS_DIR `
    --only-binary=:all: `
    --platform manylinux1_x86_64 `
    --python-version 3.6.8 `
    --implementation cp `
    --abi cp36m `
    dataclasses

# 3b. Force Download Pure Python Backports (Source Only available for contextvars)
# contextvars is needed by Werkzeug < 3.7. It provides the API, implemented by immutables.
Write-Host "[-] Force downloading contextvars (source)..."
pip download `
    --dest $WHEELS_DIR `
    --no-deps `
    --python-version 3.6.8 `
    contextvars==2.4

# 3c. Force Download Binary Backports (Linux Wheels)
# immutables: needed by contextvars (C extension, must match RHEL8)
# importlib-metadata: needed by Click < 3.8
Write-Host "[-] Force downloading binary backports (immutables, importlib-metadata)..."
pip download `
    --dest $WHEELS_DIR `
    --only-binary=:all: `
    --platform manylinux1_x86_64 `
    --python-version 3.6.8 `
    --implementation cp `
    --abi cp36m `
    immutables==0.19 `
    importlib-metadata==4.8.3 `
    zipp==3.6.0

# 4. Download Pip/Setuptools/Wheel Upgrade
Write-Host "[-] Downloading pip/setuptools/wheel..."
pip download `
    --dest $WHEELS_DIR `
    --only-binary=:all: `
    --platform manylinux1_x86_64 `
    --python-version 3.6.8 `
    --implementation cp `
    --abi cp36m `
    pip setuptools wheel

# 5. Permissions (Optional, Tar will handle them, but good to check install.sh exists)
if (-not (Test-Path "$TARGET_DIR\install.sh")) {
    Write-Error "install.sh not found in target. Make sure you created it."
}

# 6. Create Tarball
Write-Host "[-] Compressing bundle to .tar.gz..."
$Version = (Get-Content config.json | ConvertFrom-Json).version.Replace(' ', '_')
$TarFileName = "ltremc_reporter_rhel8_py36_v${Version}.tar.gz"
$TarFile = Join-Path $RELEASE_DIR $TarFileName

# Using tar if available (Windows 10+ includes tar.exe)
tar -czf "$TarFile" -C dist ltremc_reporter_rhel8_bundle

# 6. Copy README to Release Dir (if not already there, just to be sure it's fresh)
Copy-Item "release_builds\README.install" -Destination "$RELEASE_DIR\README.install" -ErrorAction SilentlyContinue

Write-Host "=== Bundle Created Successfully ===" -ForegroundColor Green
Write-Host "Bundle: $TarFile"
Write-Host "Instructions: $RELEASE_DIR\README.install"

