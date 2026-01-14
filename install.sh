#!/bin/bash

# RHEL8 Installer for LTREMC Reporter (Legacy Support)
# Target Python Version: 3.6 (Standard RHEL8 python3)

set -e

INSTALL_DIR="/opt/ltremc_reporter"
SERVICE_NAME="ltremc-reporter"

echo "=== LTREMC Reporter Installer [Offline Mode] ==="

# 1. Check for Python 3.6
if ! command -v python3.6 &> /dev/null; then
    echo "Error: python3.6 could not be found."
    echo "Please install it using: sudo dnf install python36"
    # Fallback check for python3 if it is 3.6
    if command -v python3 &> /dev/null; then
        PYVER=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
        if [ "$PYVER" == "3.6" ]; then
            echo "Found python3 ($PYVER), proceeding..."
            PYTHON_CMD="python3"
        else
            echo "Found python3 but version is $PYVER. Need 3.6."
            exit 1
        fi
    else
        exit 1
    fi
else
    PYTHON_CMD="python3.6"
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
$PYTHON_CMD -m venv venv
source venv/bin/activate

# 4. Install Dependencies from local wheels
echo "[-] Installing dependencies from ./wheels..."
echo "    Upgrading pip/setuptools first..."

# Upgrade pip using python -m pip to ensure the active environment pip is updated
$PYTHON_CMD -m pip install --no-index --find-links=wheels pip setuptools wheel

# Using requirements.rhel8.python36.txt if it exists, else requirements.txt
if [ -f "requirements.rhel8.python36.txt" ]; then
    $PYTHON_CMD -m pip install --no-index --find-links=wheels -r requirements.rhel8.python36.txt
else
    $PYTHON_CMD -m pip install --no-index --find-links=wheels -r requirements.txt
fi

# 5. Create Systemd Service
echo "[-] configuring Systemd Service..."
cat <<EOF > /etc/systemd/system/${SERVICE_NAME}.service
[Unit]
Description=LTREMC Reporter Gunicorn Service
After=network.target

[Service]
User=root
Group=root
WorkingDirectory=$INSTALL_DIR
Environment="PATH=$INSTALL_DIR/venv/bin"
# Using 1 worker with threads to ensure the in-memory TASKS dict is shared. 
# Increasing workers would require an external store like Redis.
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

# 7. Firewall Check
echo "[-] Checking Firewall Status for Port 9002..."
if command -v firewall-cmd &> /dev/null; then
    if systemctl is-active --quiet firewalld; then
        if firewall-cmd --list-ports | grep -q "9002/tcp"; then
             echo "    [OK] Port 9002 is already open in firewalld."
        else
             echo "    [WARNING] Port 9002 does NOT appear to be open in the current zone."
             echo "              To open it, run: firewall-cmd --add-port=9002/tcp --permanent && firewall-cmd --reload"
        fi
    else
        echo "    [INFO] firewalld is installed but not active. Skipping check."
    fi
else
    echo "    [INFO] firewall-cmd not found. Skipping firewalld check."
fi

echo "=== Installation Complete ==="
echo "App should be running at http://$(hostname -I | awk '{print $1}'):9002"
