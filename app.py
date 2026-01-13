from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import os
import json
import pandas as pd
import threading
import uuid
import time
from datetime import datetime, timedelta
from urllib.parse import unquote
from utils import extract_and_process_tar, allowed_file
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'supersecretkey'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
EXTRACT_FOLDER = os.path.join(BASE_DIR, 'extracted')
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['EXTRACT_FOLDER'] = EXTRACT_FOLDER

# Global storage for the current session data (Simple in-memory store)
DATA_STORE = {
    'df': None,
    'dropped_files': [],
    'global_stats': None
}

# Task storage for background processes
TASKS = {}

def background_task(task_id, filepath):
    # Link the live log to the session store so "View Log" can see it immediately
    DATA_STORE['process_log'] = TASKS[task_id]['log']

    def update_progress(message, percent):
        TASKS[task_id]['message'] = message
        TASKS[task_id]['percent'] = percent
        TASKS[task_id]['log'].append(f"{datetime.now().strftime('%H:%M:%S')} - {message}")

    try:
        TASKS[task_id]['state'] = 'processing'
        TASKS[task_id]['message'] = 'Starting process'
        
        # Process the file
        df, dropped_files, error = extract_and_process_tar(filepath, app.config['EXTRACT_FOLDER'], progress_callback=update_progress)
        
        if error:
            TASKS[task_id]['state'] = 'failed'
            TASKS[task_id]['error'] = error
            DATA_STORE['process_log'] = TASKS[task_id]['log']
        else:
            # Store Data
            DATA_STORE['df'] = df
            DATA_STORE['dropped_files'] = dropped_files
            DATA_STORE['global_stats'] = None # Reset cache
            
            # Save Log
            TASKS[task_id]['percent'] = 100
            TASKS[task_id]['log'].append(f"{datetime.now().strftime('%H:%M:%S')} - Process completed successfully.")
            DATA_STORE['process_log'] = TASKS[task_id]['log']
            
            TASKS[task_id]['state'] = 'completed'
            TASKS[task_id]['message'] = 'Process completed successfully.'
            TASKS[task_id]['filepath'] = filepath # return path so client can cookie it
            
    except Exception as e:
        TASKS[task_id]['state'] = 'failed'
        TASKS[task_id]['error'] = str(e)
        TASKS[task_id]['log'].append(f"{datetime.now().strftime('%H:%M:%S')} - Exception: {str(e)}")
        DATA_STORE['process_log'] = TASKS[task_id]['log']
        print(f"Task {task_id} failed: {e}")

# Config Management
def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {'input_directory': '', 'recents': []}

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

def update_recents(filepath):
    config = load_config()
    recents = config.get('recents', [])
    # Remove if exists to move to top
    if filepath in recents:
        recents.remove(filepath)
    recents.insert(0, filepath)
    config['recents'] = recents[:10] # Keep last 10
    save_config(config)

# Ensure directories exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(EXTRACT_FOLDER, exist_ok=True)

@app.context_processor
def inject_menu_items():
    config = load_config()
    version = config.get('version', '')
    
    menu_data = dict(menu_grids=[], menu_customers=[], grid_col=None, app_version=version)

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
        
        menu_data.update(dict(menu_grids=grids, menu_customers=customers, grid_col=grid_col))
    
    return menu_data

def get_dashboard_stats(df, full_df=None):
    # Identify Grid Column
    grid_col = None
    for col in df.columns:
        if col.lower() == 'grid':
            grid_col = col
            break
            
    all_grids_list = sorted(df[grid_col].unique().tolist()) if grid_col else []

    # Calculate Customer Stats
    total_customers = 0
    total_clients = 0
    recent_customers = 0
    upcoming_expirations = 0
    expiration_breakdown = {}
    
    # Determine reference "Today" date
    # Default to actual system time
    TODAY = datetime.now()
    is_override = False

    # Check for completed_date column to detect stale data
    # Use full_df if provided for consistent reporting date across subset views
    date_ref_df = full_df if full_df is not None else df
    
    if 'completed_date' in date_ref_df.columns:
        try:
             # Check max date
             max_date_ts = pd.to_datetime(date_ref_df['completed_date'], errors='coerce').max()
             
             if pd.notnull(max_date_ts):
                 max_date = max_date_ts.to_pydatetime()
                 # If data max date is older than yesterday, use it as reference
                 if max_date < (datetime.now() - timedelta(days=1)):
                     TODAY = max_date
                     is_override = True
        except Exception as e:
            print(f"Error determining max date: {e}")

    seven_days_ago = TODAY - timedelta(days=7)
    next_thirty_days = TODAY + timedelta(days=30)
    
    seven_days_ago_ts = seven_days_ago.timestamp()
    next_thirty_days_ts = next_thirty_days.timestamp()

    # Initialize breakdown variables
    recent_customers = 0
    recent_total_clients = 0
    recent_grids = 0
    activity_breakdown = {}
    bytes_breakdown = {}
    retention_types_breakdown = {}
    top_clients_breakdown = {}
    top_inactive_clients_breakdown = {}
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
        all_customers_list = sorted(df['extracted_customer'].unique().tolist())

        # Calculate Total Clients
        client_col_global = next((c for c in ['client_name', 'client', 'hostname'] if c in df.columns), None)
        if client_col_global:
            total_clients = df[client_col_global].nunique()
            all_clients_list = sorted(df[client_col_global].unique().tolist())
        else:
            all_clients_list = []
        
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
             # Identify Expiry Column Early for Top Chart Details
             expiry_col = None
             for col in ['expiry_date', 'expire_at', 'expiration_date']:
                 if col in df.columns:
                     expiry_col = col
                     break
                     
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
             active_customers_list = sorted(recent_df['extracted_customer'].unique().tolist())
             recent_grids = recent_df[grid_col].nunique() if grid_col else 0
             active_grids_list = sorted(recent_df[grid_col].unique().tolist()) if grid_col else []
             
             # Calculate Recent Clients (distinct from customers)
             client_col = next((c for c in ['client_name', 'client', 'hostname'] if c in recent_df.columns), None)
             if client_col:
                 recent_total_clients = recent_df[client_col].nunique()
                 active_clients_list = sorted(recent_df[client_col].unique().tolist())
             else:
                 # Fallback: if we can extract from domain? For now just 0
                 recent_total_clients = 0
                 active_clients_list = []

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
                     # Top 5 Clients (Active)
                     if client_col:
                         # Group by client, sum bytes
                         top_clients_s = recent_df.groupby(client_col)[byte_col].apply(
                             lambda x: pd.to_numeric(x, errors='coerce').sum()
                         )
                         
                         # Get Top 5 Keys
                         top5_keys = top_clients_s.nlargest(5).index.tolist()
                         
                         top_clients_breakdown = []
                         for client in top5_keys:
                             size_gb = round(top_clients_s[client] / (1024**3), 2)
                             
                             # Find oldest backup expiry for this client in RECENT data? 
                             # Or in all data? Assuming recent activity chart refers to recent backups.
                             oldest_expiry = "N/A"
                             if expiry_col:
                                 # Get subset
                                 c_df = recent_df[recent_df[client_col] == client]
                                 try:
                                     # Convert expiry col to datetime if not already suitable
                                     # But dataframe might have string.
                                     # Let's try direct sort if format allows, else convert
                                     min_val = c_df[expiry_col].min()
                                     oldest_expiry = str(min_val)
                                 except:
                                     pass
                                     
                             top_clients_breakdown.append({
                                 'client': str(client).split('.')[0],
                                 'gb': size_gb,
                                 'oldest_expiry': oldest_expiry
                             })
                         
                         # --- Top 5 Inactive Clients Logic ---
                         # Identify clients in FULL df but NOT in recent_df
                         all_clients = df[client_col].unique()
                         active_clients = recent_df[client_col].unique()
                         inactive_clients = set(all_clients) - set(active_clients)
                         
                         if inactive_clients:
                             # Filter original df for these clients
                             inactive_mask = df[client_col].isin(inactive_clients)
                             inactive_df = df.loc[inactive_mask]
                             
                             top_inactive_s = inactive_df.groupby(client_col)[byte_col].apply(
                                 lambda x: pd.to_numeric(x, errors='coerce').sum()
                             )
                             
                             top5_inactive_keys = top_inactive_s.nlargest(5).index.tolist()
                             
                             top_inactive_clients_breakdown = []
                             for client in top5_inactive_keys:
                                 size_gb = round(top_inactive_s[client] / (1024**3), 2)
                                 
                                 oldest_expiry = "N/A"
                                 if expiry_col:
                                     c_df = inactive_df[inactive_df[client_col] == client]
                                     try:
                                        min_val = c_df[expiry_col].min()
                                        oldest_expiry = str(min_val)
                                     except:
                                        pass
                                 
                                 top_inactive_clients_breakdown.append({
                                     'client': str(client).split('.')[0],
                                     'gb': size_gb,
                                     'oldest_expiry': oldest_expiry
                                 })

                     # Top 5 Customers
                     top_cust_s = recent_df.groupby('extracted_customer')[byte_col].apply(
                         lambda x: pd.to_numeric(x, errors='coerce').sum()
                     )
                     top_5_cust_keys = top_cust_s.nlargest(5).index.tolist() # Get keys in order
                     top_customers_breakdown = {}
                     for cust in top_5_cust_keys:
                        top_customers_breakdown[cust] = round(top_cust_s[cust] / (1024**3), 2)
                        
                     # We will convert this to list of dicts later if we face issues, but py3.7+ dicts preserve insertion order.
                     # Wait, for Chart.js in template we use Object.keys/values, which DOES NOT guarantee order in JS for all browsers/versions similarly to arrays.
                     # Better to use List of Dicts.
                     top_customers_breakdown = []
                     for cust in top_5_cust_keys:
                         top_customers_breakdown.append({
                             'customer': cust,
                             'gb': round(top_cust_s[cust] / (1024**3), 2)
                         })

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
             
             # Expiring in the next 30 days
             expiring_mask = (expire_ts > TODAY.timestamp()) & (expire_ts <= next_thirty_days_ts)
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
                            # Return list of dicts to preserve order and structure
                            top_5_series = top_ex_clients_s.nlargest(5)
                            top_expiring_clients_breakdown = []
                            for client, size_bytes in top_5_series.items():
                                top_expiring_clients_breakdown.append({
                                    'client': str(client).split('.')[0],
                                    'gb': round(size_bytes / (1024**3), 2)
                                })
                        
                        # Top 5 Expiring Customers (GB)
                        if 'extracted_customer' in expiring_df.columns:
                            top_ex_cust_s = expiring_df.groupby('extracted_customer')[ex_byte_col].apply(
                                lambda x: pd.to_numeric(x, errors='coerce').sum()
                            )
                            top_5_ex_cust_keys = top_ex_cust_s.nlargest(5).index.tolist()
                            
                            top_expiring_customers_breakdown = []
                            for cust in top_5_ex_cust_keys:
                                top_expiring_customers_breakdown.append({
                                    'customer': cust,
                                    'gb': round(top_ex_cust_s[cust] / (1024**3), 2)
                                })

                except Exception as e:
                    print(f"Error calculating breakdown: {e}")
                    expiration_breakdown = {}

    # Inventory Summary (Customer Breakdown)
    inventory_summary = []
    if 'extracted_customer' in df.columns:
         # Find byte col for summary
         inv_byte_col = next((c for c in ['scanned_bytes', 'bytes_scanned'] if c in df.columns), None)
         inv_client_col = next((c for c in ['client_name', 'client', 'hostname'] if c in df.columns), None)
         
         if inv_byte_col:
             try:
                 inv_mode = 'customer' # Default to grouping by customer
                 unique_customers = df['extracted_customer'].nunique()
                 
                 # Logic: If we are viewing a single customer, break down by CLIENT
                 if unique_customers == 1 and inv_client_col:
                     inv_mode = 'client'
                 
                 if inv_mode == 'client':
                     # Group by CLIENT
                     aggs = {
                         'backup_count': ('extracted_customer', 'count'),
                         'total_bytes': (inv_byte_col, lambda x: pd.to_numeric(x, errors='coerce').sum())
                     }
                     summary_df = df.groupby(inv_client_col).agg(**aggs).reset_index()
                     
                     # Rename client col to 'extracted_customer' for template compatibility
                     summary_df.rename(columns={inv_client_col: 'extracted_customer'}, inplace=True)
                     summary_df['client_count'] = 1 # 1 Client per row
                     
                 else:
                     # Group by CUSTOMER
                     aggs = {
                         'backup_count': ('extracted_customer', 'count'),
                         'total_bytes': (inv_byte_col, lambda x: pd.to_numeric(x, errors='coerce').sum())
                     }
                     if inv_client_col:
                         aggs['client_count'] = (inv_client_col, 'nunique')

                     summary_df = df.groupby('extracted_customer').agg(**aggs).reset_index()
                 
                 # Common Post-Processing
                 # Convert to GB and round
                 summary_df['total_gb'] = (summary_df['total_bytes'] / (1024**3)).round(2)
                 
                 # Ensure client_count exists if not aggregated (edge case)
                 if 'client_count' not in summary_df.columns:
                     summary_df['client_count'] = 0

                 # Sort by GB descending
                 summary_df = summary_df.sort_values('total_gb', ascending=False)
                 
                 inventory_summary = summary_df[['extracted_customer', 'client_count', 'backup_count', 'total_gb']].to_dict('records')
             except Exception as e:
                 print(f"Error creating inventory summary: {e}")

    # General Stats
    # Define desired sort order for buckets
    desired_order = ['7 days', '30 days', '90 days', '1 year', '7 years']
    
    def sort_buckets(keys):
        # Map known keys to index, unknown keys get 999
        order_map = {k: i for i, k in enumerate(desired_order)}
        return sorted(keys, key=lambda k: order_map.get(k, 999))

    # Sort activity_breakdown keys
    sorted_activity_keys = sort_buckets(activity_breakdown.keys())
    sorted_expiration_keys = sort_buckets(expiration_breakdown.keys())

    stats = {
        'total_records': len(df),
        'total_grids': df[grid_col].nunique() if grid_col else 0,
        'all_grids_list': all_grids_list,
        'recent_grids': recent_grids,
        'active_grids_list': active_grids_list,
        'total_customers': total_customers,
        'all_customers_list': all_customers_list,
        'total_clients': total_clients,
        'all_clients_list': all_clients_list,
        'recent_customers': recent_customers,
        'active_customers_list': active_customers_list,
        'recent_clients': recent_total_clients,
        'active_clients_list': active_clients_list,
        'upcoming_expirations': upcoming_expirations,
        'expiration_breakdown': expiration_breakdown,
        'sorted_expiration_keys': sorted_expiration_keys,
        'activity_breakdown': activity_breakdown,
        'sorted_activity_keys': sorted_activity_keys,
        'bytes_breakdown': bytes_breakdown,
        'retention_types_breakdown': retention_types_breakdown,
        'top_clients_breakdown': top_clients_breakdown, # Now a list of dicts
        'top_inactive_clients_breakdown': top_inactive_clients_breakdown, # Now a list of dicts
        'top_customers_breakdown': top_customers_breakdown,
        'top_expiring_clients_breakdown': top_expiring_clients_breakdown,
        'top_expiring_customers_breakdown': top_expiring_customers_breakdown,
        'inventory_summary': inventory_summary,
        'simulated_date': TODAY.strftime('%Y-%m-%d'),
        # Add column names for debugging in template if needed
        'debug_cols': list(df.columns) if not df.empty else [],
        'is_override': is_override
    }
    return stats

@app.route('/')
def index():
    # If we have data, go to dashboard, else show upload
    if DATA_STORE['df'] is not None:
         return redirect(url_for('dashboard'))
    
    config = load_config()
    file_options = []
    input_dir = config.get('input_directory')
    
    if input_dir and os.path.exists(input_dir) and os.path.isdir(input_dir):
        try:
            for f in os.listdir(input_dir):
                if f.lower().endswith(('.tar.gz', '.tgz', '.tar')):
                    file_options.append(f)
        except Exception as e:
            print(f"Error reading input directory: {e}")

    # Use cookie for recents if available
    cookie_recents = request.cookies.get('recents')
    recents_list = []
    if cookie_recents:
        try:
            # Decode if urlencoded
            decoded_cookie = unquote(cookie_recents)
            recents_list = json.loads(decoded_cookie)
        except:
            # Fallback for unencoded
            try:
                recents_list = json.loads(cookie_recents)
            except:
                pass
            
    # Fallback to config if cookie is empty/invalid (or merge?)
    # For now, let's just use cookie if present, else empty since user said config one is broken/empty
    # But we can display the config one as backup if needed.
    # The requirement is "The recent file lists is remaining empty" -> switch to cookie.
    
    # We pass 'recents_list' which overrides config.recents within the template context logic
    # Actually, we should probably update the config object passed to template
    if recents_list:
        config['recents'] = recents_list
            
    return render_template('index.html', config=config, file_options=file_options)

@app.route('/update_settings', methods=['POST'])
def update_settings():
    input_directory = request.form.get('input_directory', '').strip()
    config = load_config()
    config['input_directory'] = input_directory
    save_config(config)
    flash('Settings updated successfully.')
    return redirect(url_for('index'))

@app.route('/load_local', methods=['POST'])
def load_local():
    # Can come from either the 'select from storage' list (filename) 
    # OR the 'recents' list (full path)
    filename = request.form.get('filename')
    filepath_param = request.form.get('filepath')
    
    config = load_config()
    target_path = None
    
    if filepath_param:
        # Full path provided (from Recents)
        target_path = filepath_param
    elif filename:
        # Filename provided (from Storage list)
        input_dir = config.get('input_directory')
        if not input_dir:
             # Default to UPLOAD_FOLDER if no input directory configured
             input_dir = app.config['UPLOAD_FOLDER']
             
        if input_dir:
            target_path = os.path.join(input_dir, filename)
            
    if target_path and os.path.exists(target_path):
        # Create Task
        task_id = str(uuid.uuid4())
        TASKS[task_id] = {
            'state': 'pending', 
            'percent': 0, 
            'message': 'Initializing', 
            'log': [],
            'error': None
        }
        
        # Start Thread
        t = threading.Thread(target=background_task, args=(task_id, target_path))
        t.start()
        
        return redirect(url_for('processing', task_id=task_id))
    else:
        flash('File not found or invalid path.')
        return redirect(url_for('index'))

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
        
        # Create Task
        task_id = str(uuid.uuid4())
        TASKS[task_id] = {
            'state': 'pending', 
            'percent': 0, 
            'message': 'Initializing', 
            'log': [],
            'error': None
        }
        
        # Start Thread
        t = threading.Thread(target=background_task, args=(task_id, filepath))
        t.start()
        
        return redirect(url_for('processing', task_id=task_id))
    else:
        flash('Invalid file type. Please upload a .tar.gz file.')
        return redirect(url_for('index'))

@app.route('/processing/<task_id>')
def processing(task_id):
    if task_id not in TASKS:
        flash("Invalid processing task.")
        return redirect(url_for('index'))
    return render_template('processing.html', task_id=task_id)

@app.route('/status/<task_id>')
def task_status(task_id):
    if task_id not in TASKS:
        return jsonify({'state': 'error', 'message': 'Unknown task'}), 404
    return jsonify(TASKS[task_id])

@app.route('/dashboard')
def dashboard():
    if DATA_STORE['df'] is None:
        return redirect(url_for('index'))
    
    # Check cache for Global Dashboard
    if DATA_STORE['global_stats'] is None:
        print("DEBUG: Calculating Global Dashboard Stats (Cache Miss)")
        DATA_STORE['global_stats'] = get_dashboard_stats(DATA_STORE['df'], full_df=DATA_STORE['df'])
    else:
        print("DEBUG: Serving Global Dashboard Stats from Cache")
        
    stats = DATA_STORE['global_stats']
    return render_template('dashboard.html', stats=stats, dropped_files=DATA_STORE['dropped_files'], title="Global Dashboard")

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
    stats = get_dashboard_stats(grid_df, full_df=DATA_STORE['df'])
    return render_template('dashboard.html', stats=stats, dropped_files=[], title=f"Avamar Grid: {grid_name}")

@app.route('/customer/<path:customer_name>')
def customer_report(customer_name):
    if DATA_STORE['df'] is None:
         return redirect(url_for('index'))
    
    df = DATA_STORE['df']
    
    if 'extracted_customer' in df.columns:
        cust_df = df[df['extracted_customer'] == customer_name]
        stats = get_dashboard_stats(cust_df, full_df=DATA_STORE['df'])
        return render_template('dashboard.html', stats=stats, dropped_files=[], title=f"Customer Report: {customer_name}")
    else:
        flash("Could not identify Customer column.")
        return redirect(url_for('dashboard'))

@app.route('/reset')
def reset():
    DATA_STORE['df'] = None
    DATA_STORE['dropped_files'] = []
    DATA_STORE['global_stats'] = None
    return redirect(url_for('index'))

@app.route('/api/log')
def get_log():
    log_data = DATA_STORE.get('process_log', [])
    return jsonify(log=log_data)

if __name__ == '__main__':
    app.run(debug=True)
