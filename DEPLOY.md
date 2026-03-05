# DynaBot - Deployment Guide

## Live URLs

| URL | Status |
|-----|--------|
| https://dynabot.biz | Production (custom domain) |
| https://www.dynabot.biz | Production (www redirect) |

## Google Cloud Project

- **Project ID:** ddschedulerbot
- **Project Number:** 969733401480
- **Region:** us-central1
- **GCP Account:** sean@figsocap.com (consultantbot.bar org)
- **GCS Bucket (prod):** `gs://ddschedulerbot-files`
- **GCS Bucket (dev):** `gs://ddschedulerbot-files-dev`
- **CI/CD Service Account:** `github-actions-sa@ddschedulerbot.iam.gserviceaccount.com`
- **Runtime Service Account:** `969733401480-compute@developer.gserviceaccount.com`
- **WIF Provider:** `projects/969733401480/locations/global/workloadIdentityPools/github-pool/providers/github-provider`

## Cloud Run Services

| Service | Purpose | Triggered by |
|---------|---------|-------------|
| `ddschedulerbot` | Production | Push to `master` |
| `ddschedulerbot-dev` | Development | Push to `dev` |

## Architecture

```
User Browser
    |
    v
dynabot.biz (Cloud Run domain mapping)
    |
    v
Google Cloud Run (ddschedulerbot)
    |-- Flask web app (gunicorn, 1 worker, 8 threads)
    |-- Reads/writes files to GCS bucket
    |
    v
Google Cloud Storage (ddschedulerbot-files)
    |-- uploads/       <-- Uploaded input files (Core Mapping, Sales Order, etc.)
    |-- outputs/       <-- Generated reports (Master Schedule, BLAST, etc.)
    |-- state/         <-- Persisted schedule state (current_schedule.json)
```

Files persist in GCS across container restarts, deployments, and scaling events. The last generated schedule is automatically restored when the container starts.

## Deployment

Deployment is fully automated via GitHub Actions (`.github/workflows/`). Do NOT deploy manually.

- Push to `dev` → tests run → auto-deploy to `ddschedulerbot-dev`
- Push to `master` → tests run → auto-deploy to `ddschedulerbot`

**Before pushing to master:** Complete the versioning protocol (version badge, Flies and Swatters entry, CLAUDE.md version). See CLAUDE.md for details.

## Useful Commands

### View Logs

```bash
gcloud run logs read ddschedulerbot --region us-central1 --project=ddschedulerbot --limit=50
gcloud run logs read ddschedulerbot-dev --region us-central1 --project=ddschedulerbot --limit=50
```

### Check Domain Mapping Status

```bash
gcloud beta run domain-mappings describe --domain dynabot.biz --region us-central1 --project=ddschedulerbot
```

### View GCS Bucket Contents

```bash
gcloud storage ls gs://ddschedulerbot-files/uploads/
gcloud storage ls gs://ddschedulerbot-files/outputs/
gcloud storage ls gs://ddschedulerbot-files/state/
```

### Update Domain Mapping (if service is renamed)

```bash
# Delete old mapping
gcloud beta run domain-mappings delete --domain dynabot.biz --region us-central1 --project=ddschedulerbot
# Create new mapping
gcloud beta run domain-mappings create --service ddschedulerbot --domain dynabot.biz --region us-central1 --project=ddschedulerbot
```

## DNS Configuration (Namecheap — dynabot.biz)

### Root Domain

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

## GitHub Secrets

These secrets are required in the `letscamu/ddschedulerbot` repo for CI/CD:

| Secret | Description |
|--------|-------------|
| `GCP_PROJECT_ID` | `ddschedulerbot` |
| `WIF_PROVIDER` | Full WIF provider resource name |
| `WIF_SERVICE_ACCOUNT` | `github-actions-sa@ddschedulerbot.iam.gserviceaccount.com` |
| `SECRET_KEY` | Flask session secret (prod) |
| `ADMIN_USERNAME` | Admin login (prod) |
| `ADMIN_PASSWORD` | Admin password (prod) |
| `USERS` | Additional users in `user:pass:role` format (prod) |
| `DEV_SECRET_KEY` | Flask session secret (dev) |
| `DEV_ADMIN_USERNAME` | Admin login (dev) |
| `DEV_ADMIN_PASSWORD` | Admin password (dev) |
| `DEV_USERS` | Additional users (dev) |

> Note: Production secrets will change when real users are onboarded. Dev secrets are stable test credentials.

## IAM / Permissions

Two service accounts are involved:

**CI/CD SA** (`github-actions-sa`) — deploys via GitHub Actions:
- `roles/run.admin` on the project
- `roles/storage.admin` on GCS buckets
- `roles/iam.serviceAccountUser` on the project

**Runtime SA** (`969733401480-compute@developer.gserviceaccount.com`) — runs the Flask app:
- `roles/storage.objectAdmin` on `gs://ddschedulerbot-files`
- `roles/storage.objectAdmin` on `gs://ddschedulerbot-files-dev`

**Org Policy Note:** `iam.allowedPolicyMemberDomains` is overridden at the project level to allow `allUsers` (required for public Cloud Run access).

## Cost Estimate

- **Cloud Run:** Free tier covers 2 million requests/month. Expected cost for a small team: $0-5/month
- **GCS Storage:** $0.020/GB/month for Standard storage. A few MB of Excel files costs essentially nothing
- **Cloud Build:** Free tier covers 120 build-minutes/day

## Files Overview

| File | Purpose |
|------|---------|
| `Dockerfile` | Container build configuration (Python 3.11, gunicorn) |
| `.dockerignore` | Files excluded from Docker build |
| `.gcloudignore` | Files excluded from Cloud Build |
| `requirements.txt` | Python dependencies |
| `backend/app.py` | Flask web application |
| `backend/gcs_storage.py` | Google Cloud Storage helper module |
| `backend/data_loader.py` | Loads and validates input data files |
| `backend/algorithms/des_scheduler.py` | DES scheduling engine |
| `backend/exporters/` | Excel report generators |
| `backend/parsers/` | Input file parsers |
| `backend/templates/` | HTML templates (Jinja2) |
| `backend/static/` | CSS and JavaScript assets |
