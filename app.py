from flask import Flask, render_template, request, redirect, url_for, flash
import os
import pandas as pd
from datetime import datetime, timedelta
from utils import extract_and_process_tar, allowed_file
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'supersecretkey'  # Needed for flash messages

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
EXTRACT_FOLDER = os.path.join(BASE_DIR, 'extracted')

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['EXTRACT_FOLDER'] = EXTRACT_FOLDER

# Date Override Configuration
# Set to a date string (e.g., '2023-12-09') to simulate a specific "Today".
# Set to None to use the actual system current date.
app.config['DATE_OVERRIDE'] = '2023-09-12'

# Global storage for the current session data (Simple in-memory store)
DATA_STORE = {
    'df': None,
    'dropped_files': []
}

# Ensure directories exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(EXTRACT_FOLDER, exist_ok=True)

@app.context_processor
def inject_menu_items():
    if DATA_STORE['df'] is not None and not DATA_STORE['df'].empty:
        df = DATA_STORE['df']
        
        # Identify Grid Column (Case insensitive search)
        grid_col = None
        for col in df.columns:
            if col.lower() == 'grid':
                grid_col = col
                break
        
        # Identify Avamar Grid (from column, not file)
        grids = []
        if grid_col:
            grids = sorted(df[grid_col].dropna().unique().tolist())
        
        # Identify Customer (Using the extracted column)
        customers = []
        if 'extracted_customer' in df.columns:
            customers = sorted(df['extracted_customer'].dropna().unique().tolist())
        
        return dict(menu_grids=grids, menu_customers=customers, grid_col=grid_col)
    return dict(menu_grids=[], menu_customers=[], grid_col=None)

@app.route('/')
def index():
    # If we have data, go to dashboard, else show upload
    if DATA_STORE['df'] is not None:
         return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash('No file part')
        return redirect(request.url)
    
    file = request.files['file']
    
    if file.filename == '':
        flash('No selected file')
        return redirect(request.url)
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Process the file
        df, dropped_files, error = extract_and_process_tar(filepath, app.config['EXTRACT_FOLDER'])
        
        if error:
            flash(error)
            return redirect(url_for('index'))
            
        # Store Data
        DATA_STORE['df'] = df
        DATA_STORE['dropped_files'] = dropped_files
        
        flash(f"Successfully loaded {len(df)} records. Dropped {len(dropped_files)} outdated files.")
        return redirect(url_for('dashboard'))
    else:
        flash('Invalid file type. Please upload a .tar.gz file.')
        return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if DATA_STORE['df'] is None:
        return redirect(url_for('index'))
    
    df = DATA_STORE['df']
    
    # Identify Grid Column
    grid_col = None
    for col in df.columns:
        if col.lower() == 'grid':
            grid_col = col
            break

    # Calculate Customer Stats
    total_customers = 0
    total_clients = 0
    recent_customers = 0
    upcoming_expirations = 0
    expiration_breakdown = {}
    
    # Determine reference "Today" date
    if app.config.get('DATE_OVERRIDE'):
        try:
            TODAY = datetime.strptime(app.config['DATE_OVERRIDE'], '%Y-%m-%d')
        except ValueError:
            # Fallback to now if format is wrong
            TODAY = datetime.now()
    else:
        TODAY = datetime.now()

    seven_days_ago = TODAY - timedelta(days=7)
    next_seven_days = TODAY + timedelta(days=7)
    
    seven_days_ago_ts = seven_days_ago.timestamp()
    next_seven_days_ts = next_seven_days.timestamp()

    # Initialize breakdown variables
    recent_customers = 0
    recent_total_clients = 0
    recent_grids = 0
    activity_breakdown = {}
    bytes_breakdown = {}
    retention_types_breakdown = {}
    top_clients_breakdown = {}
    top_customers_breakdown = {}
    expiration_breakdown = {}
    top_expiring_clients_breakdown = {}
    top_expiring_customers_breakdown = {}

    # Define Helper for Bucketing
    def get_bucket(val):
        try:
             # Handle strings like "30 days" or "30"
             s = str(val).lower().replace('days','').replace('day','').replace('years','').replace('year','').strip()
             d = float(s)
             if d <= 9: return "7 days"
             if d <= 35: return "30 days"
             if d <= 100: return "90 days"
             if d <= 400: return "1 year"
             return "7 years"
        except:
             # If conversion fails, return the string itself (or mapped if needed)
             return str(val) if val else "Unknown"

    if 'extracted_customer' in df.columns:
        # Total Customers with backups in this report
        total_customers = df['extracted_customer'].nunique()

        # Calculate Total Clients
        client_col_global = next((c for c in ['client_name', 'client', 'hostname'] if c in df.columns), None)
        if client_col_global:
            total_clients = df[client_col_global].nunique()
        
        # 1. Recent Activity based on 'completed_date'
        # Check standard columns logic
        
        # Checking columns for exact match or close match
        date_col = None
        # Debug: Print all columns to help identify mismatch
        print(f"DEBUG: Available Columns: {list(df.columns)}")
        
        for col in ['completed_at', 'completed_date', 'completed_ts']:
            if col in df.columns:
                date_col = col
                break
        
        if date_col:
             print(f"DEBUG: Found date column: {date_col}")
             # Try to convert to timestamp
             try:
                # First try numeric (epoch)
                backup_ts = pd.to_numeric(df[date_col], errors='raise')
                print("DEBUG: Converted as numeric (epoch)")
             except:
                # If that fails, try datetime conversion and convert to epoch
                try:
                    # Convert to datetime (handles most string formats)
                    dt_series = pd.to_datetime(df[date_col], errors='coerce')
                    print(f"DEBUG: Sample Datetime conversion: {dt_series.head().tolist()}")
                    # Convert to seconds (timestamp)
                    backup_ts = dt_series.apply(lambda x: x.timestamp() if pd.notnull(x) else None)
                    print("DEBUG: Converted via to_datetime")
                except Exception as e:
                    print(f"Date conversion failed for {date_col}: {e}")
                    backup_ts = pd.Series()

             # Fill NaNs with 0 to avoid errors in comparison
             backup_ts = backup_ts.fillna(0)
             
             # Debug Values
             print(f"DEBUG: Threshold (7 Days Ago): {seven_days_ago_ts}")
             print(f"DEBUG: Max Date in Data: {backup_ts.max()}")
             
             # Filter: completed >= 7 days ago
             recent_mask = (backup_ts >= seven_days_ago_ts)
             recent_df = df.loc[recent_mask].copy()
             recent_customers = recent_df['extracted_customer'].nunique()
             recent_grids = recent_df[grid_col].nunique() if grid_col else 0
             
             # Calculate Recent Clients (distinct from customers)
             client_col = next((c for c in ['client_name', 'client', 'hostname'] if c in recent_df.columns), None)
             if client_col:
                 recent_total_clients = recent_df[client_col].nunique()
             else:
                 # Fallback: if we can extract from domain? For now just 0
                 recent_total_clients = 0

             # Calculate Recent Activity Breakdowns
             # Determine columns to use
             r_col = None
             if 'retention_days' in recent_df.columns:
                 r_col = 'retention_days'
             elif 'retention_string' in recent_df.columns:
                 r_col = 'retention_string'
             
             if r_col:
                 recent_df['retention_bucket'] = recent_df[r_col].apply(get_bucket)
                 
                 # 1. Activities per retention (Count)
                 activity_breakdown = recent_df['retention_bucket'].value_counts().to_dict()
                 
                 # 2. Scanned Bytes per retention (GB)
                 byte_col = None
                 for col in ['scanned_bytes', 'bytes_scanned']:
                     if col in recent_df.columns:
                         byte_col = col
                         break
                 
                 if byte_col:
                     # Group by bucket, sum bytes, convert to GB
                     gb_series = recent_df.groupby('retention_bucket')[byte_col].apply(
                        lambda x: pd.to_numeric(x, errors='coerce').sum()
                     ) / (1024**3)
                     bytes_breakdown = gb_series.round(2).to_dict()
                     
                 # 3. Retention Types count (per retention)
                 # Find policy name column - Try various common names
                 policy_col = next((c for c in ['retention_policy', 'policy_name', 'retention_tag', 'schedule', 'schedule_name', 'group_name', 'plugin_name'] if c in recent_df.columns), None)
                 
                 # If no explicit policy column, fallback to the retention column itself (often the string IS the policy)
                 if not policy_col and r_col:
                     policy_col = r_col

                 if policy_col:
                     types_series = recent_df.groupby('retention_bucket')[policy_col].nunique()
                     retention_types_breakdown = types_series.to_dict()

                 # 4. Top 5 Clients & Customers (GB Written)
                 # Re-use byte_col from step 2 if available
                 if byte_col:
                     # Top 5 Clients
                     if client_col:
                         # Group by client, sum bytes
                         top_clients_s = recent_df.groupby(client_col)[byte_col].apply(
                             lambda x: pd.to_numeric(x, errors='coerce').sum()
                         )
                         # Take top 5 and convert to GB
                         top_clients_breakdown_raw = (top_clients_s.nlargest(5) / (1024**3)).round(2).to_dict()
                         # Shorten Client Names (FQDN -> Hostname)
                         top_clients_breakdown = {str(k).split('.')[0]: v for k, v in top_clients_breakdown_raw.items()}
                     
                     # Top 5 Customers
                     top_cust_s = recent_df.groupby('extracted_customer')[byte_col].apply(
                         lambda x: pd.to_numeric(x, errors='coerce').sum()
                     )
                     top_customers_breakdown = (top_cust_s.nlargest(5) / (1024**3)).round(2).to_dict()

        else:
             print("DEBUG: No suitable 'completed' date column found.")

        # 2. Upcoming Expirations based on 'expiry_date'
        # Exhpirations in the next 7 days? Or total active expiring soon?
        expiry_col = None
        for col in ['expiry_date', 'expire_at', 'expiration_date']:
             if col in df.columns:
                 expiry_col = col
                 break
             
        if expiry_col:
             try:
                expire_ts = pd.to_numeric(df[expiry_col], errors='raise')
             except:
                try:
                    dt_series = pd.to_datetime(df[expiry_col], errors='coerce')
                    expire_ts = dt_series.apply(lambda x: x.timestamp() if pd.notnull(x) else None)
                except:
                    expire_ts = pd.Series()
             
             expire_ts = expire_ts.fillna(0)
             
             # Expiring in the next 7 days
             expiring_mask = (expire_ts > TODAY.timestamp()) & (expire_ts <= next_seven_days_ts)
             upcoming_expirations = df.loc[expiring_mask].shape[0]
             
             if upcoming_expirations > 0:
                expiring_df = df.loc[expiring_mask].copy()
                try:
                    if 'retention_days' in expiring_df.columns:
                         expiration_breakdown = expiring_df['retention_days'].apply(get_bucket).value_counts().to_dict()
                    elif 'retention_string' in expiring_df.columns:
                        expiration_breakdown = expiring_df['retention_string'].fillna('Unknown').value_counts().to_dict()
                    else:
                        expiration_breakdown = {}
                        
                    # Calculate Top 5 Expiring by Bytes Released (if available) or Count
                    # Re-find byte column if not already found (reuse logic safely)
                    ex_byte_col = None
                    for col in ['scanned_bytes', 'bytes_scanned']:
                        if col in expiring_df.columns:
                            ex_byte_col = col
                            break
                    
                    if ex_byte_col:
                        # Top 5 Expiring Clients (GB)
                        ex_client_col = next((c for c in ['client_name', 'client', 'hostname'] if c in expiring_df.columns), None)
                        if ex_client_col:
                            top_ex_clients_s = expiring_df.groupby(ex_client_col)[ex_byte_col].apply(
                                lambda x: pd.to_numeric(x, errors='coerce').sum()
                            )
                            top_expiring_clients_breakdown_raw = (top_ex_clients_s.nlargest(5) / (1024**3)).round(2).to_dict()
                            # Shorten Client Names (FQDN -> Hostname)
                            top_expiring_clients_breakdown = {str(k).split('.')[0]: v for k, v in top_expiring_clients_breakdown_raw.items()}
                        
                        # Top 5 Expiring Customers (GB)
                        if 'extracted_customer' in expiring_df.columns:
                            top_ex_cust_s = expiring_df.groupby('extracted_customer')[ex_byte_col].apply(
                                lambda x: pd.to_numeric(x, errors='coerce').sum()
                            )
                            top_expiring_customers_breakdown = (top_ex_cust_s.nlargest(5) / (1024**3)).round(2).to_dict()

                except Exception as e:
                    print(f"Error calculating breakdown: {e}")
                    expiration_breakdown = {}

    # General Stats
    # Sort activity_breakdown keys to ensure proper order in stats object (optional since template sorts)
    sorted_activity_keys = sorted(activity_breakdown.keys(), key=lambda k: activity_breakdown[k], reverse=True)
    sorted_expiration_keys = sorted(expiration_breakdown.keys(), key=lambda k: expiration_breakdown[k], reverse=True)

    stats = {
        'total_records': len(df),
        'total_grids': df[grid_col].nunique() if grid_col else 0,
        'recent_grids': recent_grids,
        'total_customers': total_customers,
        'total_clients': total_clients,
        'recent_customers': recent_customers,
        'recent_clients': recent_total_clients,
        'upcoming_expirations': upcoming_expirations,
        'expiration_breakdown': expiration_breakdown,
        'sorted_expiration_keys': sorted_expiration_keys,
        'activity_breakdown': activity_breakdown,
        'sorted_activity_keys': sorted_activity_keys,
        'bytes_breakdown': bytes_breakdown,
        'retention_types_breakdown': retention_types_breakdown,
        'top_clients_breakdown': top_clients_breakdown,
        'top_customers_breakdown': top_customers_breakdown,
        'top_expiring_clients_breakdown': top_expiring_clients_breakdown,
        'top_expiring_customers_breakdown': top_expiring_customers_breakdown,
        'simulated_date': TODAY.strftime('%Y-%m-%d'),
        # Add column names for debugging in template if needed
        'debug_cols': list(df.columns) if not df.empty else [],
        'is_override': bool(app.config.get('DATE_OVERRIDE'))
    }

    
    # Try to calculate logical capacity if column exists
    for col in ['bytes_scanned', 'capacity', 'logical_capacity']:
        # Case insensitive check would be better, but keeping simple
        pass

    return render_template('dashboard.html', stats=stats, dropped_files=DATA_STORE['dropped_files'])

@app.route('/grid/<grid_name>')
def grid_report(grid_name):
    if DATA_STORE['df'] is None:
         return redirect(url_for('index'))
    
    df = DATA_STORE['df']
    
    # Identify Grid Column again
    grid_col = None
    for col in df.columns:
        if col.lower() == 'grid':
            grid_col = col
            break
            
    if grid_col is None:
        flash("Could not identify 'grid' column in the dataset.")
        return redirect(url_for('dashboard'))

    grid_df = df[df[grid_col] == grid_name]
    
    table_html = grid_df.head(100).to_html(classes='table table-striped table-sm', index=False)
    
    return render_template('report_generic.html', title=f"Avamar Grid: {grid_name}", table=table_html)

@app.route('/customer/<path:customer_name>')
def customer_report(customer_name):
    if DATA_STORE['df'] is None:
         return redirect(url_for('index'))
    
    df = DATA_STORE['df']
    
    if 'extracted_customer' in df.columns:
        cust_df = df[df['extracted_customer'] == customer_name]
        table_html = cust_df.drop(columns=['extracted_customer']).head(100).to_html(classes='table table-striped table-sm', index=False)
        return render_template('report_generic.html', title=f"Customer Report: {customer_name}", table=table_html)
    else:
        flash("Could not identify Customer column.")
        return redirect(url_for('dashboard'))

@app.route('/reset')
def reset():
    DATA_STORE['df'] = None
    DATA_STORE['dropped_files'] = []
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
