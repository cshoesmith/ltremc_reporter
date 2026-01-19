#!/bin/bash

# Ubuntu 22+ Installer for LTREMC Reporter
# Target Python Version: 3.10+ (Ubuntu 22.04 default is 3.10, 24.04 is 3.12)

set -e

INSTALL_DIR="/opt/ltremc_reporter"
SERVICE_NAME="ltremc-reporter"

echo "=== LTREMC Reporter Installer [Offline Mode - Ubuntu] ==="

# 1. Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 could not be found."
    echo "Please install it using: sudo apt update && sudo apt install python3 python3-venv"
    exit 1
fi

PYTHON_CMD="python3"
PYVER=$($PYTHON_CMD -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo "[-] Found Python $PYVER"

# Check minimum version 3.10
# (Simple string comparison for 3.10, 3.11, 3.12)
MAJOR=$(echo $PYVER | cut -d. -f1)
MINOR=$(echo $PYVER | cut -d. -f2)

if [ "$MAJOR" -ne 3 ] || [ "$MINOR" -lt 10 ]; then
    echo "Error: Python version 3.10 or higher is required. Found $PYVER."
    exit 1
fi

# 2. Setup Directory
echo "[-] Setting up installation directory at $INSTALL_DIR..."
if [ -d "$INSTALL_DIR" ]; then
    echo "    Backing up existing directory..."
    mv "$INSTALL_DIR" "${INSTALL_DIR}_backup_$(date +%s)"
fi
mkdir -p "$INSTALL_DIR"
cp -r ./* "$INSTALL_DIR/"

# 3. Create Virtual Environment
echo "[-] Creating Virtual Environment..."
cd "$INSTALL_DIR"

# Ensure venv module is available (on Ubuntu sometimes it's a separate package)
if ! $PYTHON_CMD -c "import venv" &> /dev/null; then
    echo "Error: 'venv' module not found."
    echo "Please run: sudo apt install python3-venv"
    exit 1
fi

$PYTHON_CMD -m venv venv
source venv/bin/activate

# 4. Install Dependencies from local wheels
echo "[-] Installing dependencies from ./wheels..."
echo "    Upgrading pip/setuptools first..."

# Upgrade pip using python -m pip
$PYTHON_CMD -m pip install --no-index --find-links=wheels pip setuptools wheel

# Install requirements
# Try to install. If specific version wheels are missing for the current python version,
# it might fail in offline mode if we only bundled for 3.10 and user is on 3.12.
echo "    Installing packages..."
if $PYTHON_CMD -m pip install --no-index --find-links=wheels -r requirements.txt; then
    echo "    [OK] Installation successful."
else
    echo "    [ERROR] Pip install failed."
    echo "    This bundle contains wheels for Python 3.10 (Ubuntu 22.04)."
    echo "    If you are on a different version, you may need internet access to fetch compatible wheels,"
    echo "    or use the bundle matching your OS."
    exit 1
fi

# 5. Create Systemd Service
echo "[-] Configuring Systemd Service..."
cat <<EOF > /etc/systemd/system/${SERVICE_NAME}.service
[Unit]
Description=LTREMC Reporter Gunicorn Service
After=network.target

[Service]
User=root
Group=root
WorkingDirectory=$INSTALL_DIR
Environment="PATH=$INSTALL_DIR/venv/bin"
# Using 1 worker with threads
ExecStart=$INSTALL_DIR/venv/bin/gunicorn --workers 1 --threads 8 --timeout 0 --bind 0.0.0.0:9002 app:app
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# 6. Enable and Start
echo "[-] Reloading systemd daemon..."
systemctl daemon-reload
echo "[-] Enabling service..."
systemctl enable ${SERVICE_NAME}
echo "[-] Starting service..."
systemctl restart ${SERVICE_NAME}

# 7. Firewall Check (UFW)
echo "[-] Checking UFW Status for Port 9002..."
if command -v ufw &> /dev/null; then
    if ufw status | grep -q "Active"; then
        if ufw status | grep -q "9002"; then
             echo "    [OK] Port 9002 rule exists."
        else
             echo "    [WARNING] Port 9002 does NOT appear to be allowed in UFW."
             echo "              To allow it, run: ufw allow 9002/tcp"
        fi
    else
        echo "    [INFO] UFW is inactive."
    fi
else
    echo "    [INFO] UFW not found."
fi

echo "=== Installation Complete ==="
echo "Access the reporter at http://<server-ip>:9002"
