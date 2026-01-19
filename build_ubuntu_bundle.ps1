# PowerShell Script to bundle the app for Ubuntu 22.04+ (Python 3.10)
$ErrorActionPreference = "Stop"

$TARGET_DIR = "dist\ltremc_reporter_ubuntu_bundle"
$WHEELS_DIR = "$TARGET_DIR\wheels"
$RELEASE_DIR = "release_builds"

Write-Host "=== Creating Ubuntu 22+ Deployment Bundle ===" -ForegroundColor Cyan

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

$FilesToCopy = @(
    "app.py",
    "utils.py",
    "install_ubuntu.sh",
    "requirements.txt",
    "README.md",
    "ADMIN_GUIDE.md"
)

$FoldersToCopy = @(
    "templates",
    "static"
)

foreach ($File in $FilesToCopy) {
    if (Test-Path $File) {
        Copy-Item -Path $File -Destination $TARGET_DIR
    } else {
        Write-Warning "File not found: $File"
    }
}

foreach ($Folder in $FoldersToCopy) {
    if (Test-Path $Folder) {
        Copy-Item -Path $Folder -Destination "$TARGET_DIR\$Folder" -Recurse
    } else {
        Write-Warning "Folder not found: $Folder"
    }
}

# 2b. Generate Clean config.json for Production
Write-Host "[-] Generating clean config.json..."
if (Test-Path "config.json") {
    $CurrentConfig = Get-Content "config.json" | ConvertFrom-Json
} else {
    $CurrentConfig = @{ version = "1.0.0" }
}

$CleanConfig = @{
    version = $CurrentConfig.version
    input_directory = "uploads"
    recents = @()
}
$CleanConfig | ConvertTo-Json -Depth 2 | Set-Content "$TARGET_DIR\config.json"

# 3. Download Wheels for Ubuntu 22.04 (Python 3.10)
# Ubuntu 22.04 uses Python 3.10 by default.
# We download manylinux_2_31_x86_64 or manylinux2014_x86_64 wheels.
# Using 'cp310' abi.

Write-Host "[-] Downloading Python 3.10 wheels for Ubuntu 22.04 (Linux x86_64)..."
Write-Host "    Note: This requires internet access."

pip download `
    --dest $WHEELS_DIR `
    --only-binary=:all: `
    --platform manylinux2014_x86_64 `
    --python-version 3.10 `
    --implementation cp `
    --abi cp310 `
    -r requirements.txt

# 4. Download Pip/Setuptools/Wheel Upgrade
Write-Host "[-] Downloading pip/setuptools/wheel..."
pip download `
    --dest $WHEELS_DIR `
    --only-binary=:all: `
    --platform manylinux2014_x86_64 `
    --python-version 3.10 `
    --implementation cp `
    --abi cp310 `
    pip setuptools wheel

# 5. Check install script
if (-not (Test-Path "$TARGET_DIR\install_ubuntu.sh")) {
    Write-Error "install_ubuntu.sh not found in target."
} else {
    # Rename it to install.sh in the bundle for simplicity? 
    # Or keep it as install_ubuntu.sh so user knows.
    # User might expect 'install.sh'. Let's rename it to install.sh inside the bundle,
    # but the source file remains install_ubuntu.sh.
    # Actually, keeping it as install_ubuntu.sh is clearer if they look at files.
    # But usually people run ./install.sh.
    # I'll create a symlink or just rename it.
    Rename-Item -Path "$TARGET_DIR\install_ubuntu.sh" -NewName "install.sh"
}

# 6. Create Tarball
Write-Host "[-] Compressing bundle to .tar.gz..."
$Version = $CurrentConfig.version.Replace(' ', '_')
$TarFileName = "ltremc_reporter_ubuntu22_py310_v${Version}.tar.gz"
$TarFile = Join-Path $RELEASE_DIR $TarFileName

# Using tar if available
tar -czf "$TarFile" -C dist ltremc_reporter_ubuntu_bundle

Write-Host "=== Bundle Created Successfully ===" -ForegroundColor Green
Write-Host "Bundle: $TarFile"
