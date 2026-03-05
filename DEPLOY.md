# EstradaBot - Deployment Guide

## Live URLs

| URL | Status |
|-----|--------|
| https://estradabot-969733401480.us-central1.run.app | Live (direct Cloud Run — URL will update after first deploy) |
| https://estradabot.biz | Live |
| https://www.estradabot.biz | Live |

## User Accounts

| Username | Role | Password Source |
|----------|------|-----------------|
| admin | Admin | See `env.yaml` (not committed) or GCP Secret Manager |
| MfgEng | User | See `env.yaml` or GCP Secret Manager |
| Planner | User | See `env.yaml` or GCP Secret Manager |
| CustomerService | User | See `env.yaml` or GCP Secret Manager |
| Guest | User | See `env.yaml` or GCP Secret Manager |

> **Note:** Passwords are managed through environment variables and should never be stored in version-controlled files. Ask the project admin for credentials.

## Google Cloud Project

- **Project ID:** ddschedulerbot
- **Project Number:** 969733401480
- **Region:** us-central1
- **GCP Account:** sean@figsocap.com (consultantbot.bar org)
- **GCS Bucket (prod):** `gs://ddschedulerbot-files`
- **GCS Bucket (dev):** `gs://ddschedulerbot-files-dev`
- **Service Account:** `github-actions-sa@ddschedulerbot.iam.gserviceaccount.com`
- **WIF Provider:** `projects/969733401480/locations/global/workloadIdentityPools/github-pool/providers/github-provider`

## Architecture

```
User Browser
    |
    v
Google Cloud Run (estradabot)
    |-- Flask web app (gunicorn, 2 workers, 4 threads)
    |-- Reads/writes files to GCS bucket
    |
    v
Google Cloud Storage (estradabot-files)
    |-- uploads/       <-- Uploaded input files (Core Mapping, Sales Order, etc.)
    |-- outputs/       <-- Generated reports (Master Schedule, BLAST, etc.)
    |-- state/         <-- Persisted schedule state (current_schedule.json)
```

Files persist in GCS across container restarts, deployments, and scaling events. The last generated schedule is automatically restored when the container starts.

## Deployment Commands

### Deploy Updates

```bash
cd "C:\Users\SeanFilipow\CAMU\ddschedulerbot"
gcloud run deploy estradabot --source . --region us-central1 --allow-unauthenticated --project ddschedulerbot
```

### View Logs

```bash
gcloud run logs read estradabot --region us-central1 --project=ddschedulerbot --limit=50
```

### Check Domain Status

```bash
gcloud beta run domain-mappings describe --domain estradabot.biz --region us-central1 --project=ddschedulerbot
```

### View GCS Bucket Contents

```bash
gcloud storage ls gs://ddschedulerbot-files/uploads/
gcloud storage ls gs://ddschedulerbot-files/outputs/
gcloud storage ls gs://ddschedulerbot-files/state/
```

## DNS Configuration (Namecheap)

### Root Domain (estradabot.biz)

| Type | Host | Value |
|------|------|-------|
| A | @ | 216.239.32.21 |
| A | @ | 216.239.34.21 |
| A | @ | 216.239.36.21 |
| A | @ | 216.239.38.21 |

### WWW Subdomain

| Type | Host | Value |
|------|------|-------|
| CNAME | www | ghs.googlehosted.com |

### Optional IPv6

| Type | Host | Value |
|------|------|-------|
| AAAA | @ | 2001:4860:4802:32::15 |
| AAAA | @ | 2001:4860:4802:34::15 |
| AAAA | @ | 2001:4860:4802:36::15 |
| AAAA | @ | 2001:4860:4802:38::15 |

## Environment Variables

Environment variables are stored in `env.yaml` (not committed to git):

- SECRET_KEY - Flask session encryption
- ADMIN_USERNAME / ADMIN_PASSWORD - Admin account
- USERS - Additional user accounts (format: `username1:password1,username2:password2`)
- BEHIND_PROXY - Set to true for Cloud Run
- GCS_BUCKET - GCS bucket name (default: `estradabot-files`)

## IAM / Permissions

The Cloud Run service account needs `storage.objectAdmin` on the GCS bucket. This was granted with:

```bash
gcloud storage buckets add-iam-policy-binding gs://ddschedulerbot-files \
  --member="serviceAccount:github-actions-sa@ddschedulerbot.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"
```

## Cost Estimate

- **Cloud Run:** Free tier covers 2 million requests/month. Expected cost for a small team: $0-5/month
- **GCS Storage:** $0.020/GB/month for Standard storage. A few MB of Excel files costs essentially nothing
- **Cloud Build:** Free tier covers 120 build-minutes/day

## Stopping the Service

To stop and avoid all charges:

```bash
# Delete the Cloud Run service
gcloud run services delete estradabot --region us-central1 --project=ddschedulerbot

# Optionally delete the GCS bucket and all files
gcloud storage rm -r gs://ddschedulerbot-files
```

## Files Overview

| File | Purpose |
|------|---------|
| `Dockerfile` | Container build configuration (Python 3.11, gunicorn) |
| `.dockerignore` | Files excluded from Docker build |
| `.gcloudignore` | Files excluded from Cloud Build |
| `env.yaml` | Environment variables (not in git) |
| `requirements.txt` | Python dependencies |
| `backend/app.py` | Flask web application |
| `backend/gcs_storage.py` | Google Cloud Storage helper module |
| `backend/data_loader.py` | Loads and validates input data files |
| `backend/algorithms/des_scheduler.py` | DES scheduling engine |
| `backend/exporters/` | Excel report generators |
| `backend/parsers/` | Input file parsers |
| `backend/templates/` | HTML templates (Jinja2) |
| `backend/static/` | CSS and JavaScript assets |
