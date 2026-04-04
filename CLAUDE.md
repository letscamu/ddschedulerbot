# DynaBot - Claude Code Project Instructions

## Session Startup (MANDATORY)

**Before doing ANY work, always run these verification steps and report the results to the developer:**

1. Run `git fetch origin` to get the latest remote state
2. Run `git branch --show-current` to confirm the active branch
3. Run `git status` to check for uncommitted changes
4. Run `git log --oneline -1` to show the current local commit
5. Run `git log --oneline -1 origin/master` to show the latest remote master commit
6. Compare local vs remote — if the branch is behind, **warn the developer** before proceeding

**Report format:**
```
SESSION CHECK:
  Branch:          <current branch>
  Local commit:    <short hash + message>
  Remote master:   <short hash + message>
  Status:          UP TO DATE | BEHIND BY X COMMITS | UNCOMMITTED CHANGES
  Ready to work:   YES | NO — <reason>
```

If the branch is behind remote or has merge conflicts, do NOT begin work until the developer decides how to handle it.

---

## Protocols

### Melt Banana Protocol (MBP) — Batch Requirement Collection
**Full spec:** `protocols/mbp.md`
- **Start:** "Initiate MBP" → STOP all actions, enter collection mode. Acknowledge each prompt with a numbered receipt. Write to `memory.md`.
- **Go:** "Melt Banana" / "Cook the Cavendish" → Present consolidated briefing, offer to deglaze, then execute full speed.
- **Abort:** "Cancel MBP" / "Stand down" → Keep notes in memory.md, return to normal.
- **Critical rule:** Never build during collection. Never reorder Sean's items. MBP state survives context compression.

### Deglazing Protocol — Critical Review
**Full spec:** `protocols/deglazing.md`
- **Start:** "Deglaze" / "Deglaze the pan" / "Deglaze [target]" / "Let's deglaze what we just talked about"
- **Targets:** Documents, conversations, or MBP collections.
- **Report sections:** The Fond (still good), Burnt Bits (problems), Missing Ingredients (gaps), Open Questions (`DG-Q1`...), Recommendations.
- **Critical rule:** Never edit or execute before presenting the report. Be genuinely critical — don't rubber-stamp.

**When a protocol is triggered, read the full spec file before proceeding.**

---

## Infrastructure

- **MacBook Air** — Sean's primary dev machine
- **Mothership (Mac Studio)** — always-on machine at `192.168.86.30`, SSH via `ssh mothership` from MacBook Air
  - Repo present at `/Users/seanfilipow/CAMU/ddschedulerbot`
  - Hosts scheduled automation (feedback pipeline launchd job)
  - Homebrew, gh, gcloud all installed and authenticated

---

## Project Overview

**DynaBot** is a discrete event simulation (DES) based production scheduling web application for stator manufacturing. It is deployed on Google Cloud Run with persistent storage via Google Cloud Storage.

- **Repository:** https://github.com/letscamu/ddschedulerbot.git
- **Live site:** https://dynabot.biz
- **GCP Project:** ddschedulerbot
- **GCS Bucket:** gs://ddschedulerbot-files
- **Region:** us-central1

---

## Tech Stack

- **Backend:** Python 3.11, Flask 3.0+, gunicorn
- **Frontend:** Bootstrap 5, jQuery, DataTables, Jinja2 templates
- **Scheduler Engine:** Custom DES in `backend/algorithms/des_scheduler.py`
- **Storage:** Google Cloud Storage (uploads, outputs, state)
- **Deployment:** Docker container on Google Cloud Run
- **Auth:** Flask-Login with role-based access (Admin, Planner, MfgEng, CustomerService, Guest)

---

## Project Structure

```
DynaBot/
├── backend/
│   ├── app.py                  # Flask application entry point
│   ├── gcs_storage.py          # GCS helper module
│   ├── data_loader.py          # File parsing and validation
│   ├── validators.py           # Input validation
│   ├── algorithms/
│   │   ├── des_scheduler.py    # Main DES scheduling engine (core logic)
│   │   └── scheduler.py        # Scheduling utilities
│   ├── exporters/
│   │   ├── excel_exporter.py   # Excel report generation
│   │   └── impact_analysis_exporter.py
│   ├── parsers/                # Input file parsers (Sales Order, Hot List, etc.)
│   ├── templates/              # Jinja2 HTML templates
│   └── static/                 # CSS and JavaScript
├── deployment/                 # Server config examples
├── Dockerfile                  # Cloud Run container build
├── requirements.txt            # Python dependencies
├── .env.example                # Environment variable template
└── DEPLOY.md                   # Deployment guide and infrastructure details
```

---

## Key Conventions

### Git Workflow
- **Production branch:** `master` — auto-deploys to `ddschedulerbot` Cloud Run service
- **Development branch:** `dev` — auto-deploys to `ddschedulerbot-dev` Cloud Run service
- **Feature branches:** `feat/<description>` or `fix/<description>` — PR into `dev`
- **Claude agent branches:** `claude/<description>` — PR into `dev`
- **Pull requests:** All changes go through `dev` first, then `dev` merges into `master` for production
- **Owner direct deploy:** When the project owner explicitly requests it, Claude may merge directly to `master` and push
- **Commit messages:** Short, descriptive — explain the "why" not just the "what"
- Never force push to `master`
- Always pull the latest before creating a new branch

### Dev Environment (Cloud)
- **Dev Cloud Run service:** `ddschedulerbot-dev` (max 1 instance, scale-to-zero)
- **Dev GCS bucket:** `gs://ddschedulerbot-files-dev` (isolated from production data)
- **Dev deploys:** Automatic on push to `dev` branch (tests run first)
- **Production deploys:** Automatic on push to `master` (tests run first)

### Safe Update Workflow (MVP 2.0+)
1. Create a feature branch from `dev`: `git checkout -b feat/my-feature dev`
2. Develop and test locally: `pytest tests/ -v`
3. Push and PR into `dev` — CI runs tests, auto-deploys to `ddschedulerbot-dev`
4. Team verifies on the dev Cloud Run URL
5. When ready: merge `dev` into `master` — CI runs tests, auto-deploys to production

### Code Style
- Python code follows PEP 8
- Use descriptive variable and function names
- Add docstrings to new functions and classes
- Keep Flask routes in `backend/app.py`
- Keep scheduling logic in `backend/algorithms/`
- Keep file parsing in `backend/parsers/`
- Keep export logic in `backend/exporters/`

### File Handling
- All file I/O goes through GCS in production (`backend/gcs_storage.py`)
- Local file paths are only for development
- Input files are Excel (.xlsx) — use openpyxl/pandas for reading
- Output files are Excel (.xlsx) — use openpyxl for writing

### Environment Variables
- Never hardcode secrets — use environment variables
- Reference `.env.example` for the full list of required variables
- Production secrets are managed in GCP (env.yaml, not committed to git)

---

## Sensitive Files — DO NOT Commit

- `.env` — local environment variables with passwords
- `env.yaml` — production environment variables
- Any file containing passwords, API keys, or secrets
- `DEPLOY.md` contains credentials — it is currently committed but should be treated as sensitive reference material

---

## Testing Changes Locally

```bash
# Create/activate virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env with your local settings

# Run the development server
python run_production.py
```

The app will be available at http://localhost:5000

---

## Deploying to Production

Deployment is done via Google Cloud Run from the repo root:

```bash
gcloud run deploy ddschedulerbot --source . --region us-central1 --allow-unauthenticated
```

### Owner Direct Deploy (fast path)

When the project owner says "deploy", "merge and deploy", "push to production", or similar during a Claude Code session, follow this streamlined process:

1. Complete the **Versioning Protocol** below (version badge, update log, CLAUDE.md)
2. Commit changes on the feature branch and push
3. Switch to `master`, pull latest, merge the feature branch
4. Push `master` to origin
5. Report: "Merged to master and pushed. Ready for `gcloud run deploy`."

**Note:** The actual `gcloud run deploy` command must be run by the owner on their local machine (Claude Code does not have gcloud credentials). Claude's job is to get `master` ready.

### Standard Deploy (team members)

**Before deploying:**
1. Ensure all tests pass locally
2. Ensure your changes are committed and pushed
3. Create a PR and get it reviewed/approved
4. Merge via GitHub
5. Coordinate with the team — only one deploy at a time
6. Verify the live site after deployment: https://dynabot.biz

---

## Debugging Workflow

When the developer says "I am debugging" or "let's debug" or similar, **always remind them**:

> "Want me to pull bug reports from the site first? Run `python tools/feedback_pipeline.py fetch --category 'Bug Report'`"

This ensures real user-reported bugs inform the debugging session before diving into code.

---

## Common Tasks Reference

| Task | Where to look |
|------|---------------|
| Add a new input parser | `backend/parsers/` — follow existing parser patterns |
| Modify scheduling logic | `backend/algorithms/des_scheduler.py` |
| Add a new page/route | `backend/app.py` + `backend/templates/` |
| Change export format | `backend/exporters/` |
| Update frontend styles | `backend/static/` |
| Modify GCS integration | `backend/gcs_storage.py` |
| Update dependencies | `requirements.txt` + rebuild container |

---

## Versioning Protocol (MANDATORY for production releases)

**Current Version:** MVP 2.0.5

### Version Numbering: `X.Y.Z`

- **X** — Major release. Only bumped when the product owner declares a new major milestone.
- **Y** — Feature release. Bumped for new features or significant enhancements (set by the project stage last implemented, e.g., MVP 1.8 = the 8th feature release).
- **Z** — Patch/bugfix. Iterated for each bugfix or minor correction within the current feature release (e.g., 1.8.1, 1.8.2, ...). Resets to 0 on a new Y bump.

When merging changes to `master` that will be deployed to production, you MUST:

1. **Increment the version badge** in `backend/templates/base.html`
   - Find the `<span class="badge bg-info ...>MVP X.Y.Z</span>` in the navbar brand
   - Bump Z (1.8.1 → 1.8.2) for bugfixes and minor corrections
   - Bump Y (1.8 → 1.9) for feature additions, reset Z to 0
   - Bump X (1.x → 2.0) only when the product owner declares a new major release

2. **Update the Flies and Swatters page** in `backend/templates/update_log.html`
   - Add a new version section at the top of the "Version History" card (above the previous version)
   - Include the version badge, date, and a short release name
   - List each change as a `<li class="list-group-item">` with a description
   - Follow the existing format (see MVP 1.0 and MVP 1.1 entries as examples)

3. **Update this file** — change "Current Version" above to match the new version

**Do NOT deploy to production without completing all three steps.**

---

## Project Tracking — CAMU Master Tracker

**All task status lives in the [CAMU Master Tracker](https://github.com/orgs/letscamu/projects/2) GitHub Project.** Markdown planning docs (roadmap.md, state.md, etc.) carry context and decisions — not status. GitHub Project is the source of truth for what's in progress, blocked, or done.

### Session Startup — Check the Tracker
After the git checks above, also run:
```bash
gh project item-list 2 --owner letscamu --format json | python3 -c "
import json, sys
items = json.load(sys.stdin)['items']
dynabot = [i for i in items if i.get('subProject','') == 'DynaBot' or 'DynaBot' in i.get('title','') or 'DDScheduler' in i.get('title','')]
for i in dynabot:
    print(f\"  [{i.get('status','?'):12}] {i['title']}\")
" 2>/dev/null || echo "  (Could not reach GitHub Project — work from local planning docs)"
```

### When You Discover New Work
- **Bug found while coding?** Create an issue: `gh issue create --repo letscamu/ddschedulerbot --title "[Bug] ..." --body "..." --label bug,agent-discovered`
- **Then add to project:** `gh project item-add 2 --owner letscamu --url <issue_url>`
- **Do NOT fix it in the current PR** unless it directly blocks the task you're on. File it and move on.

### When You Complete Work
- Update the GitHub issue status via PR (linking `Closes #NN` in the PR body auto-closes the issue)
- The project board status updates automatically when issues close

---

## Team Coordination

- Before starting work on a feature, check the GitHub project board and open PRs
- If someone else is working on the same area, coordinate before making changes
- Use descriptive branch names: `feature/add-rework-tracking`, `fix/hot-list-parsing`
- Keep PRs focused — one feature or fix per PR
- Review teammates' PRs promptly
