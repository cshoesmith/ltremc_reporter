# Copilot Instructions

## Versioning Workflow

To increment the application version:
1.  Open `config.json` in the root directory.
2.  Update the `version` string (e.g., change `19.12 build23` to `19.12 build24`).
3.  Restart the application service or rebuild the container.
4.  The new version will automatically appear on the landing page below the file input card.

## Build & Release Workflow (RHEL 8 / Python 3.6)

This project is deployed to an offline RHEL 8 server running Python 3.6.8.

### 1. Build the Offline Bundle
Run the PowerShell build script from the project root. This script:
- Cleans previous builds.
- Copies only necessary source files (excludes `.venv`, `release_builds`, etc.).
- Downloads Python 3.6 compatible wheels (manylinux2014) for RHEL 8.
- Force-downloads backports (`dataclasses`, `contextvars`) required for Flask on Py3.6.
- Packages everything into a `.tar.gz` in `release_builds/`.

```powershell
.\build_rhel_bundle.ps1
```

### 2. Deploy to Server
Copy the generated tarball to the target server (SCP/SFTP).
```bash
scp "release_builds/ltremc_reporter_rhel8_py36_v19.12_build33.tar.gz" user@rhel8-server:/tmp/
```

### 3. Install on Server
On the RHEL 8 server:
```bash
# Extract
tar -xzvf ltremc_reporter_rhel8_py36_v19.12_build33.tar.gz
cd ltremc_reporter_rhel8_bundle

# Run Installer (Sets up venv, installs wheels, configures firewall)
chmod +x install.sh
./install.sh
```
