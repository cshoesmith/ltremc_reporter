import tarfile
import pandas as pd
import os
import io
import shutil
from datetime import datetime, timedelta

UPLOAD_FOLDER = 'uploads'
EXTRACT_FOLDER = 'extracted'

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in {'gz', 'tar'}

def extract_and_process_tar(filepath, extract_to, progress_callback=None):
    """
    Extracts a tar.gz file matches 'grids' directory, filters old data,
    and returns a list of dataframes or summary data.
    """
    def report_progress(message, percent):
        if progress_callback:
            progress_callback(message, percent)

    if not os.path.exists(extract_to):
        os.makedirs(extract_to)
    
    # Clear previous extractions if needed
    report_progress("Cleaning up previous session data", 5)
    for filename in os.listdir(extract_to):
        file_path = os.path.join(extract_to, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print(f'Failed to delete {file_path}. Reason: {e}')

    try:
        if filepath.endswith("tar.gz") or filepath.endswith(".tgz"):
            report_progress("Extracting archive (GZ)", 10)
            with tarfile.open(filepath, "r:gz") as tar:
                tar.extractall(path=extract_to)
        elif filepath.endswith(".tar"):
             report_progress("Extracting archive (TAR)", 10)
             with tarfile.open(filepath, "r:") as tar:
                tar.extractall(path=extract_to)
    except Exception as e:
        return None, [], f"Error extracting file: {str(e)}"

    # 1. Identify valid CSVs and load them efficiently
    dfs = []
    
    # Count total files for progress calculation
    csv_files = []
    for root, dirs, files in os.walk(extract_to):
        for file in files:
            if file.lower().endswith(".csv"):
                csv_files.append(os.path.join(root, file))
    
    total_files = len(csv_files)
    report_progress(f"Found {total_files} CSV reports to process.", 20)
    
    for i, full_path in enumerate(csv_files):
        filename = os.path.basename(full_path)
        
        # Calculate progress from 20% to 80%
        current_percent = 20 + int((i / total_files) * 60) if total_files > 0 else 20
        report_progress(f"Processing {filename}", current_percent)

        try:
            df = pd.read_csv(full_path)
            df['source_file'] = filename
            
            # Logic to extract Customer from Domain
            # "Customer: This is name of the source file (user said this, but likely means Avamar Grid), 
            #  and it is the first section of the domain column."
            
            # We will prioritize the Domain column extraction
            customer_col = None
            for col in df.columns:
                if col.lower() == 'domain':
                    customer_col = col
                    break
            
            if customer_col:
                # Logic to extract Customer from Domain
                # Standard format: /Customer/Client
                # Replication format: /REPLICATE/SourceGrid/Customer/Client
                
                # Optimized list comprehension instead of .apply() which is slow
                customers = []
                replicas = []
                
                for val in df[customer_col]:
                    is_replica = False
                    customer = 'Unknown'
                    
                    if not pd.isna(val):
                        # Split by / and remove empty strings
                        parts = [p for p in str(val).split('/') if p]
                        
                        if parts:
                            # Check for REPLICATE prefix
                            if parts[0].upper() == 'REPLICATE':
                                is_replica = True
                                # Usually /REPLICATE/Grid/Customer/...
                                if len(parts) >= 3:
                                    customer = parts[2]
                                elif len(parts) >= 2:
                                    customer = parts[1]
                                else:
                                    customer = parts[0]
                            else:
                                customer = parts[0]
                    
                    customers.append(customer)
                    replicas.append(is_replica)

                df['extracted_customer'] = customers
                df['is_replica'] = replicas
            else:
                df['extracted_customer'] = 'Unknown'
                df['is_replica'] = False

            dfs.append(df)
        except Exception as e:
            print(f"Error reading {filename}: {e}")

    if not dfs:
        return [], [], "No CSV files found in archive."

    # 2. Determine High Water Mark (Global Max Date) for filtering
    # Combine all collected_at to find the true 'current' timestamp
    # We assume 'collected_at' column exists as per requirements
    
    all_dates = []
    for df in dfs:
        if 'collected_at' in df.columns:
            # Drop NaNs just in case
            valid_dates = pd.to_numeric(df['collected_at'], errors='coerce').dropna()
            all_dates.append(valid_dates)
    
    dropped_files = []
    
    if all_dates:
        full_date_series = pd.concat(all_dates)
        if not full_date_series.empty:
            # Convert to seconds if it looks huge? Assuming standard unix epoch seconds
            # User example: 12-09-2023. 
            max_epoch = full_date_series.max()
            
            # 12 hours = 12 * 3600 = 43200 seconds
            cutoff_epoch = max_epoch - 43200 
            
            # Filter each dataframe (File level filtering)
            filtered_dfs = []
            for df in dfs:
                if 'collected_at' in df.columns:
                    # Check the timestamp of the file (assuming it's consistent for the file)
                    # We use the max timestamp in the file to be safe
                    file_timestamp = pd.to_numeric(df['collected_at'], errors='coerce').max()
                    
                    if file_timestamp >= cutoff_epoch:
                        # Add readable date and keep the file
                        df['collected_at_readable'] = pd.to_datetime(df['collected_at'], unit='s')
                        filtered_dfs.append(df)
                    else:
                        fname = df.get('source_file', ['unknown'])[0]
                        print(f"Dropping outdated file {fname} (Timestamp: {file_timestamp})")
                        dropped_files.append(fname)
                else:
                    # Keep if no date column? Or discard? 
                    # Assuming we keep but can't filter
                    filtered_dfs.append(df)
            
            dfs = filtered_dfs
            
    # 3. Generate Summaries for the UI (Legacy support for upload success page if needed, but we prefer Master DF)
    # We will combine all data into one Master DataFrame for easier querying
    report_progress("Merging datasets...", 90)
    if dfs:
        master_df = pd.concat(dfs, ignore_index=True)
    else:
        master_df = pd.DataFrame()

    report_progress("Processing complete.", 100)
    return master_df, dropped_files, None
