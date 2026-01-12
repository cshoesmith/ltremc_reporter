# LTREMC Reporter - Installation Guide

The **LTREMC Reporter** is a specialized analytics tool designed to visualize and report on Avamar backup environments. This query-able dashboard provides insights into backup grids, customer consumption, active clients, and retention policies.

## Prerequisites

Before installing the LTR Reporter, ensure the following software is installed on the host machine:

*   **Operating System:** Windows 10/11, Windows Server 2016+, or Linux (Ubuntu/CentOS).
*   **Python:** Version 3.8 or higher. [Download Python](https://www.python.org/downloads/)
*   **Git:** (Optional) For cloning the repository. [Download Git](https://git-scm.com/downloads)
*   **Web Browser:** Microsoft Edge, Google Chrome, or Firefox.

## Installation Steps

### 1. Download the Source Code

Extract the provided source code archive to a directory on your machine (e.g., `C:\LtremcReporter`) or clone the repository using Git:

```bash
git clone https://github.com/cshoesmith/ltremc_reporter.git
cd ltremc_reporter
```

### 2. Set Up a Virtual Environment (Recommended)

It is best practice to run Python applications in an isolated environment to avoid dependency conflicts.

**Windows (PowerShell):**
```powershell
# Create the virtual environment
python -m venv .venv

# Activate the environment
.\.venv\Scripts\Activate.ps1
```

**Linux/MacOS:**
```bash
# Create the virtual environment
python3 -m venv .venv

# Activate the environment
source .venv/bin/activate
```

### 3. Install Dependencies

Install the required Python libraries using `pip`:

```bash
pip install -r requirements.txt
```

*Key dependencies include: `Flask` (Web Framework), `pandas` (Data Processing), and `openpyxl` (Excel support).*

## Configuration

The application uses a `config.json` file to store settings. A default one will be created if it does not exist, but you can configure it manually.

1.  **Input Directory:** You can define a default server-side directory where `.tar.gz` archive files are stored for quick loading.
2.  **Uploads Folder:** The application requires an `uploads` and `extracted` folder in the root directory. These are created automatically upon start-up.

**Example `config.json`:**
```json
{
    "input_directory": "C:\\Backups\\Archives",
    "recents": []
}
```

## Running the Application

To start the web server, run the `app.py` script from your terminal (ensure your virtual environment is active):

```bash
python app.py
```

You should see output indicating the server is running:
```
 * Serving Flask app 'app'
 * Debug mode: off
 * Running on http://127.0.0.1:5000
```

## Accessing the Dashboard

Open your web browser and navigate to:

**[http://localhost:5000](http://localhost:5000)**

## Troubleshooting

*   **Port in use:** If port 5000 is occupied, you may need to modify the `app.run()` call in `app.py` or free up the port.
*   **Permission Errors:** Ensure the user running the script has read/write permissions to the `uploads` and `extracted` directories.
*   **Missing Imports:** If you see `ModuleNotFoundError`, ensure you have activated your virtual environment and ran the `pip install` command successfully.
