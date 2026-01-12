#  LTREMC Reporter
## Administration & User Guide

**Version:** 1.0  
**Date:** January 2026  
**Confidentiality:** Internal Use Only

---

## Table of Contents

1.  [Executive Summary](#executive-summary)
2.  [Getting Started](#getting-started)
3.  [Dashboard Overview](#dashboard-overview)
4.  [Data Processing](#data-processing)
5.  [Detailed Reporting](#detailed-reporting)
    *   [Avamar Grid Reports](#avamar-grid-reports)
    *   [Customer Reports](#customer-reports)
6.  [Administration](#administration)

---

## 1. Executive Summary <a name="executive-summary"></a>

The **LTR Reporter** is a comprehensive analytics platform designed to ingest, process, and visualize long-term retention backup data from Avamar environments. Tailored for Service Providers and Backup Administrators, it transforms raw CSV logs into actionable insights, highlighting capacity consumption, client activity, and retention policy distribution.

Key capabilities include:
*   **Automated Parsing:** Ingestion of complex `.tar.gz` log archives.
*   **Activity Tracking:** Identification of "Active" vs. "Inactive" clients based on recent backup history.
*   **Capacity Planning:** Visualization of expiring data to reclaim storage.
*   **Multi-Tenancy View:** Drill-down reporting by Avamar Grid or Customer entity.

---

## 2. Getting Started <a name="getting-started"></a>

### Accessing the Portal
Navigate to the hosted URL provided by your administrator (e.g., `http://localhost:5000`).

### The Landing Page
Upon initial access, the user is presented with the **Data Ingestion Interface**.

**[Figure 1: Landing Page Interface]**
> *Description: A clean, Dell-styled interface featuring three tabs: "Upload File", "Select from Storage", and "Recent Files". A "Settings" button is visible in the top right.*

*   **Upload File:** Drag and drop a local `.tar.gz` archive containing Avamar CSV reports.
*   **Select from Storage:** Choose a file from the server's pre-configured input directory.
*   **Recent Files:** Quickly reload one of the last 5 processed datasets.

---

## 3. Dashboard Overview <a name="dashboard-overview"></a>

Once a dataset is processed, the **Executive Dashboard** provides a high-level health check of the environment.

**[Figure 2: Executive Dashboard]**
> *Description: The dashboard features a row of four KPI cards at the top (Total Backups, Avamar Grids, Customers, Clients). Each card displays a "Total" count and an "Active" count (activity within the last 7 days). The cards use the Dell color palette (Blue, Green, Orange, Grey).*

### Key Performance Indicators (KPIs)

*   **Total Backups:** The aggregate number of backup records found in the uploaded logs.
*   **Avamar Grids:** Distinct backup grids detected.
    *   *Interactive:* Click "Total" to view a full list of Grid names.
*   **Customers:** Unique customer entities extracted from domain structures (e.g., `/REPLICATE/Grid/CustomerA`).
*   **Clients:** Unique client hostnames or FQDNs.

### Visual Analytics

**1. Activity Timeline (Last 30 Days)**
A chart displaying backup frequency over time. Spikes indicate heavy backup windows, while flatlines may suggest failed jobs or outages.

**2. Active vs. Inactive Clients**
A critical operational metric.
*   **Active:** Clients with backup jobs successfully completed in the last 7 days.
*   **Inactive:** Clients present in the inventory but with no recent backups. This serves as an immediate "Call to Action" for administrators to investigate connectivity or agent issues.

**3. Retention Distribution**
A breakdown of data based on retention policies (e.g., 7 Days, 30 Days, 1 Year, 7 Years). This helps ensure compliance with SLA requirements.

---

## 4. Data Processing <a name="data-processing"></a>

The LTR Reporter utilizes a multi-threaded background processing engine to handle large datasets without freezing the user interface.

**[Figure 3: Processing Status Screen]**
> *Description: A focused modal showing a blue progress bar. The status text reads "Processing [Filename]..." with a percentage indicator. The font is clean and minimal.*

**Workflow:**
1.  **Ingestion:** The `.tar.gz` is uploaded to the server.
2.  **Extraction:** The archive is unpacked in a secure temporary directory.
3.  **Parsing:** The engine scans for `.csv` files, filtering out irrelevant system files.
4.  **Transformation:** Data is normalized (dates converted to timestamps, sizes to GB).
5.  **Analytics:** Aggregations for "Active" and "Inactive" states are calculated in real-time.
6.  **Cleanup:** Temporary files are purposly retained for the session duration but cleared on next upload.

---

## 5. Detailed Reporting <a name="detailed-reporting"></a>

The application supports deep-dive reporting via the top navigation menu.

### Avamar Grid Reports
Select a specific grid (e.g., `ave-01`) to view:
*   Total storage consumption for that specific grid.
*   Client list isolated to that grid.
*   Oldest expiring backups specific to that infrastructure.

### Customer Reports
Select a customer (e.g., `FinanceDept`) to view:
*   **Chargeback Data:** Total GBs consumed by the customer.
*   **Client Inventory:** A specific list of machines owned by that customer.
*   **Compliance:** Verification that the customer's backups fall into the agreed retention buckets.

**[Figure 4: Customer Report View]**
> *Description: Similar layout to the main dashboard but filtered. A prominent "Total Consumption" metric is displayed in GB/TB. A table at the bottom lists the "Top 5 Clients by Storage Usage".*

---

## 6. Administration <a name="administration"></a>

### Configuration Settings
Accessible via the **Settings** button on the home page.
*   **Input Directory:** Define a local server path (e.g., `D:\Archives`) to allow users to load files directly from the server storage without re-uploading.

### Viewing Logs
For troubleshooting ingestion issues, admins can view the live processing log.
1.  Click **View Log** in the top navigation bar.
2.  A modal window will display the real-time backend log, including file extraction success/failure and parsing errors.

### Reset Data
To clear the current session and upload a new dataset, click **Reset Data** in the navigation menu. This purges the in-memory dataframe and returns the user to the Landing Page.


---
