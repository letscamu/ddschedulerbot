# DynaBot

A Discrete Event Simulation (DES) based production scheduling web application for stator manufacturing, deployed on Google Cloud Run with persistent storage via Google Cloud Storage.

**Live at:** https://www.dynabot.biz

## Features

### Web Application
- **Dashboard** - Schedule summary, file status, recent reports
- **File Upload** - Upload input Excel files via drag-and-drop or file picker
- **Schedule Viewer** - Interactive DataTable with sorting, filtering, and Excel export
- **Reports** - Download generated Excel reports (Master Schedule, BLAST, Core Oven, Pending Core, Impact Analysis)
- **Visual Simulation** - Animated factory floor showing parts moving through operations
- **Authentication** - Role-based login (Admin, Planner, Customer Service, Guest)

### Core Scheduling
- **DES (Discrete Event Simulation) Scheduler** - Pipeline-based simulation for accurate production scheduling
- **5-Tier Priority System** - Hot ASAP > Hot Dated > Rework > Normal > CAVO ordering
- **Hot List Processing** - Supports both ASAP and dated priority entries with REDLINE rubber override
- **Rework/Re-BLAST Detection** - Automatically detects orders requiring rework via REMOV RB work center
- **Core Allocation & Lifecycle Tracking** - Manages core assignment and tracks state through operations

### Work Schedule
- 4-day work week support (Monday-Thursday)
- Dual shifts with configurable times
- Break and handover time handling
- Core oven preheat scheduling

### Resource Management
- 5 injection machines with rubber type tracking
- Rubber type assignment (HR, XE, etc.)
- Machine utilization tracking

### Cloud Infrastructure
- **Google Cloud Run** - Serverless container deployment, scales to zero
- **Google Cloud Storage** - Persistent file storage for uploads, reports, and schedule state
- **Schedule Persistence** - Generated schedules survive container restarts and are available to all users

## Project Structure

```
EstradaBot/
├── backend/
│   ├── algorithms/          # DES scheduler implementation
│   │   ├── des_scheduler.py # Main scheduling engine
│   │   └── scheduler.py     # Scheduling utilities
│   ├── exporters/           # Excel report generators
│   │   ├── excel_exporter.py
│   │   └── impact_analysis_exporter.py
│   ├── parsers/             # Input file parsers
│   │   ├── sales_order_parser.py
│   │   ├── core_mapping_parser.py
│   │   ├── shop_dispatch_parser.py
│   │   ├── pegging_parser.py
│   │   ├── hot_list_parser.py
│   │   └── order_filters.py
│   ├── templates/           # Jinja2 HTML templates
│   │   ├── base.html
│   │   ├── login.html
│   │   ├── index.html       # Dashboard
│   │   ├── upload.html
│   │   ├── schedule.html
│   │   ├── reports.html
│   │   └── simulation.html
│   ├── static/              # CSS and JavaScript
│   │   ├── css/simulation.css
│   │   └── js/simulation.js
│   ├── app.py               # Flask web application
│   ├── gcs_storage.py       # Google Cloud Storage helper
│   ├── data_loader.py       # Data loading and validation
│   └── validators.py        # Input validation
├── deployment/              # Deployment config examples
│   ├── nginx.conf.example
│   ├── dd-scheduler.service.example
│   └── run_windows.bat
├── Dockerfile               # Container build (Python 3.11 + gunicorn)
├── requirements.txt         # Python dependencies
├── run_production.py        # Local production server launcher
├── DEPLOY.md                # Deployment guide and credentials
├── implementation_plan.md   # Implementation plan with phase status
└── requirements_document.md # Original requirements specification
```

## Setup

### Local Development

1. Create and activate virtual environment:
   ```bash
   python -m venv venv
   venv\Scripts\activate  # Windows
   source venv/bin/activate  # Linux/Mac
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file:
   ```
   SECRET_KEY=your-random-secret-key
   ADMIN_USERNAME=admin
   ADMIN_PASSWORD=your-password
   USERS=Planner:pass1,MfgEng:pass2
   ```

4. Run the development server:
   ```bash
   python run_production.py
   # Or directly:
   cd backend && python app.py
   ```

5. Open http://localhost:5000

### Deploy to Google Cloud Run

```bash
gcloud run deploy estradabot --source . --region us-central1 --allow-unauthenticated
```

See [DEPLOY.md](DEPLOY.md) for full deployment details, DNS setup, and GCS bucket configuration.

## Usage

### Uploading Files

Log in and navigate to the **Upload** page. Upload the following Excel files:

| File | Description | Who Uploads |
|------|-------------|-------------|
| `Open Sales Order *.xlsx` | Open work orders with BLAST dates, customers, promise dates | Planner |
| `Shop Dispatch *.xlsx` | Shop floor dispatch data with work center operations | Planner |
| `Pegging Report *.XLSX` | Pegging report with actual start dates | Planner |
| `HOT LIST *.xlsx` | Hot list with priority orders (ASAP or dated) | Planner / Customer Service |
| `Core Mapping.xlsx` | Core mapping and process times reference | Admin |
| `Stators Process VSM.xlsx` | Operation routing and process parameters | Admin |

Files are stored in Google Cloud Storage and persist across sessions and deployments. Admin-uploaded reference files (Core Mapping, Process VSM) are available to all users.

### Generating a Schedule

1. Navigate to the **Schedule** page
2. Click **Generate New**
3. The scheduler loads all uploaded files from GCS, runs the DES simulation, and generates reports
4. Results are displayed in the interactive schedule table
5. Reports are uploaded to GCS and available on the **Reports** page

### Downloading Reports

Navigate to the **Reports** page to download generated Excel files:

| Report | Description |
|--------|-------------|
| Master Schedule | Complete schedule with all orders and operation times |
| BLAST Schedule | BLAST operation sequence for shop floor |
| Core Oven Schedule | Core preheat timing schedule |
| Pending Core Report | Orders waiting for core availability |
| Impact Analysis | Comparison of baseline vs hot list schedule (if hot list uploaded) |

## Architecture

### Technology Stack

- **Backend:** Python 3.11, Flask, Jinja2
- **Frontend:** Bootstrap 5, jQuery, DataTables
- **Scheduler:** Custom DES engine (`des_scheduler.py`)
- **Storage:** Google Cloud Storage (`gcs_storage.py`)
- **Deployment:** Google Cloud Run, Docker, gunicorn
- **Authentication:** Flask-Login with role-based access

### Data Flow

1. Users upload Excel files via web UI -> stored in `gs://estradabot-files/uploads/`
2. User clicks "Generate Schedule" -> files downloaded from GCS to temp dir
3. DataLoader parses files -> DES scheduler runs simulation
4. Reports generated as Excel files -> uploaded to `gs://estradabot-files/outputs/`
5. Schedule state saved as JSON -> `gs://estradabot-files/state/current_schedule.json`
6. On container restart, schedule state is restored from GCS automatically

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/upload` | POST | Upload a file to GCS |
| `/api/generate` | POST | Generate schedule from uploaded files |
| `/api/schedule` | GET | Get current schedule data as JSON |
| `/api/download/<filename>` | GET | Download a report file from GCS |
| `/api/files` | GET | List uploaded files |
| `/api/reports` | GET | List generated reports |
| `/api/simulation-data` | GET | Get simulation animation data |

## Dependencies

- pandas
- openpyxl
- python-dateutil
- flask
- flask-cors
- flask-login
- python-dotenv
- waitress
- werkzeug
- gunicorn
- google-cloud-storage
