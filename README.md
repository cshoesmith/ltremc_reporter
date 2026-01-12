# LTREMC Reporter

A Flask-based web application to upload and visualize Avamar Backup Inventory CSV reports.

## Features
- Upload `.tar.gz` archives containing CSV files.
- Automatically extracts and processes the CSVs.
- Displays an overview dashboard with record counts.
- Shows data previews for each file found.

## Setup

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the Application**
   ```bash
   python app.py
   ```

3. **Access the Web Interface**
   Open your browser and navigate to `http://127.0.0.1:5000`.

## Project Structure
- `app.py`: Main Flask application entry point.
- `utils.py`: Logic for file extraction and CSV processing.
- `templates/`: HTML templates (Upload and Report pages).
- `uploads/`: Temporary storage for uploaded archives.
- `extracted/`: Temporary storage for extracted CSV files.
