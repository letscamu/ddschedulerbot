# DynaBot Production Audit — 2026-03-15

**Site:** https://dynabot.biz
**Version:** MVP 2.0.3
**Tested accounts:** CustomerService (CustSvc2026!), planner (Planner2026! — FAILED)
**Test method:** Automated Playwright (headless Chromium, desktop 1440x900 + mobile 375x812)

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 1     |
| HIGH     | 0     |
| MEDIUM   | 6     |
| LOW      | 3     |

**Security:** All routes and API endpoints properly require authentication. 404 page is custom. Bad login shows error feedback. No unprotected endpoints found.

**Performance:** All pages load in under 1s (networkidle). Download links all return 200.

---

## Findings

### F-1: `planner` account cannot log in [CRITICAL]

**Observed:** Logging in as `planner` / `Planner2026!` returns "Invalid username or password." on production.
**Impact:** The Planner role is the primary user for the scheduling workflow — /planner, /core-mapping, publish, reorder, and generate are all gated behind Planner/Admin. If this account is broken, the scheduling workflow is inaccessible.
**Likely cause:** Password was changed on prod and not communicated, or the account was not created/migrated to prod.
**Action:** Verify the `planner` account exists in the USERS env var on the production Cloud Run service. Reset or re-add if missing.

---

### F-2: Inconsistent page titles — "EstradaBot" and "DD Scheduler Bot" still present [MEDIUM]

**Observed:** Only 3 of 16 templates use the correct "DynaBot" branding in `<title>`. The rest use the old names:

| Template | Current Title | Should Be |
|----------|--------------|-----------|
| `index.html` | Dashboard - DD Scheduler Bot | Dashboard - DynaBot |
| `upload.html` | Upload Files - DD Scheduler Bot | Upload Files - DynaBot |
| `reports.html` | Reports - DD Scheduler Bot | Reports - DynaBot |
| `schedule.html` | Schedule - EstradaBot | Schedule - DynaBot |
| `simulation.html` | Simulation - EstradaBot | Simulation - DynaBot |
| `special_requests.html` | Special Requests - EstradaBot | Special Requests - DynaBot |
| `planner.html` | Planner Workflow - EstradaBot | Planner Workflow - DynaBot |
| `mfg_eng_review.html` | Mfg Eng Review - EstradaBot | Mfg Eng Review - DynaBot |
| `notifications.html` | Notifications - EstradaBot | Notifications - DynaBot |
| `alerts.html` | Alerts - EstradaBot | Alerts - DynaBot |
| `user_management.html` | User Management - EstradaBot | User Management - DynaBot |
| `core_mapping.html` | Core Mapping - EstradaBot | Core Mapping - DynaBot |

**Already correct:** `base.html`, `login.html`, `update_log.html` (Flies and Swatters), `404.html`, `500.html`

**Impact:** Looks unprofessional. Browser tabs show the old product name. SEO/bookmarks show stale branding.
**Fix:** Find-and-replace in each template's `{% block title %}` line. ~2 minutes of work.

---

### F-3: No favicon [MEDIUM]

**Observed:** No `<link rel="icon">` tag in `base.html`. Browser shows a generic tab icon.
**Impact:** Minor polish issue, but noticeable — especially when users have multiple tabs open.
**Fix:** Add a favicon to `backend/static/` and reference it in `base.html` `<head>`.

---

### F-4: Dashboard shows "No Schedule Generated" despite having schedule data [MEDIUM]

**Observed:** The dashboard displays stats (300 Total Orders, 202 On Time, 57 Late, 21.9 Avg Turnaround) and recent reports — but also shows a large "No Schedule Generated" card with an upload CTA below the stats.
**Root cause:** The `index.html` template at line 263 uses `{% else %}` to show this block when the schedule preview table is empty. The stats and reports sections are populated from a different data source (published schedule metadata) while the preview table requires a different condition.
**Impact:** Confusing UX — users see data proving a schedule exists, then a message saying no schedule has been generated.
**Fix:** Condition the "No Schedule Generated" block on whether *any* published schedule exists, not just whether the preview table has rows. Or hide it when stats are populated.

---

### F-5: Schedule page DataTables JS error [MEDIUM]

**Observed:** Console error on `/schedule`: `TypeError: Cannot read properties of undefined (reading 'cell')` from `jquery.dataTables.min.js`. The table still renders 300 rows, but the error fires during initialization.
**Impact:** The table appears to work, but the error may cause subtle issues with sorting, filtering, or pagination. Could also indicate a column mismatch between the DataTables config and the actual HTML columns.
**Fix:** Audit the DataTables column definitions in `schedule.html` JavaScript — likely a `columns` array referencing a field that doesn't exist in some rows, or a row with fewer cells than expected.

---

### F-6: Mobile responsive — tables overflow on 5 pages [MEDIUM]

**Observed:** On a 375px mobile viewport, the following pages have horizontal scroll overflow:

| Page | scrollWidth | Worst Element |
|------|-------------|---------------|
| `/schedule` | 1473px | scheduleTable (1433px wide) |
| `/reports` | 879px | reports DataTable (839px) |
| `/special-requests` | 440px | request queue table (866px) |
| `/upload` | 426px | supported file types table (386px) |
| `/simulation` | 400px | simulation canvas |

The sidebar has a hamburger toggle and collapses correctly. The issue is specifically tables and wide content areas.
**Impact:** Tables are unusable on mobile without side-scrolling. The scheduling table is nearly 4x wider than the viewport.
**Fix:** Wrap tables in `<div class="table-responsive">` containers. For the schedule table, consider a card-based mobile layout or horizontal scroll with a sticky first column.

---

### F-7: Mfg Eng Review page is a placeholder [LOW]

**Observed:** `/mfg-eng-review` shows "This page is under development." with a gear icon. It's in the nav for all roles.
**Impact:** Users can navigate to a dead-end page. Not a bug per se, but worth noting.
**Fix:** Either hide from nav until ready, or add a more informative coming-soon state with expected timeline.

---

### F-8: Hot List file shows warning icon on dashboard [LOW]

**Observed:** In the "Current Files" panel on the dashboard, the Hot List file (`HOT_LIST_STA-ROT.xlsx`) shows an orange/yellow warning icon (!) while Sales Order and Shop Dispatch show green checkmarks. The Hot List was uploaded on 03/05/2026 while others are from 03/13/2026.
**Impact:** Not necessarily a bug — may indicate the hot list is stale or has validation warnings. But there's no tooltip or explanation visible to the user about what the warning means.
**Fix:** Add a tooltip or popover explaining the warning state (e.g., "File is older than other inputs" or "Validation warnings found").

---

### F-9: Role-gated pages redirect to dashboard with flash message instead of 403 [LOW]

**Observed:** When CustomerService navigates to `/planner`, `/user-management`, or `/core-mapping`, they're redirected to the dashboard with a flash message like "Only Planner and Admin users can access the planner workflow." This is functional but could be cleaner.
**Impact:** Minor UX — the nav still shows these pages aren't in the CustomerService sidebar, so users are unlikely to reach them organically. Only matters if someone shares a direct link.
**Not a bug** — current behavior is acceptable. Could be improved by returning a styled 403 page instead.

---

## What's Working Well

- **Security:** All routes and APIs properly gated behind authentication
- **Login UX:** Clear error on bad credentials, "Please log in" flash on unauthenticated access
- **404 page:** Custom styled, matches the app design
- **Performance:** Sub-1s page loads across the board
- **Download links:** All 5 tested report downloads return 200
- **Notifications:** Working correctly with read/unread states
- **Flies and Swatters:** Extensive update log, well-organized by version
- **Simulation:** Interactive production flow visualization renders correctly
- **Special Requests:** Full workflow visible — submit, queue, status badges
- **Sidebar navigation:** Consistent across pages, hamburger toggle works on mobile
- **Dashboard:** Good data density — stats, alerts, files, and reports at a glance

---

## Execution Plan

### Phase 1: Quick Wins (30 min, single PR)

**Branch:** `fix/prod-audit-branding-polish`

1. **Fix all page titles** — replace "EstradaBot" and "DD Scheduler Bot" with "DynaBot" in all 12 template `{% block title %}` tags
2. **Add a favicon** — generate a simple DynaBot favicon and add `<link rel="icon">` to `base.html`

Files touched:
- `backend/templates/index.html` (line 3)
- `backend/templates/upload.html` (line 3)
- `backend/templates/reports.html` (line 3)
- `backend/templates/schedule.html` (line 3)
- `backend/templates/simulation.html` (line 3)
- `backend/templates/special_requests.html` (line 3)
- `backend/templates/planner.html` (line 3)
- `backend/templates/mfg_eng_review.html` (line 3)
- `backend/templates/notifications.html` (line 3)
- `backend/templates/alerts.html` (line 3)
- `backend/templates/user_management.html` (line 3)
- `backend/templates/core_mapping.html` (line 3)
- `backend/templates/base.html` (add favicon link)
- `backend/static/favicon.ico` (new file)

### Phase 2: Dashboard Fix (30 min, same or separate PR)

**Branch:** `fix/dashboard-no-schedule-message`

1. **Fix "No Schedule Generated" logic** — update `index.html` conditional to check for published schedule existence, not just preview table rows
2. **Add tooltip to Hot List warning icon** — explain the warning state to users

Files touched:
- `backend/templates/index.html` (~line 263)
- `backend/app.py` (dashboard route, pass a `has_published_schedule` flag)
- Dashboard JS or template where file status icons are rendered

### Phase 3: DataTables Bug (1 hr, separate PR)

**Branch:** `fix/schedule-datatables-error`

1. **Debug the DataTables column mismatch** — inspect the `columns` config in `schedule.html` JS, compare against the actual API response from `/api/schedule`
2. **Fix the root cause** — likely a missing or extra column definition, or rows with inconsistent cell counts
3. **Test with the current production dataset**

Files touched:
- `backend/templates/schedule.html` (JS section)
- Possibly `backend/app.py` (`/api/schedule` route)

### Phase 4: Mobile Responsive Tables (2 hrs, separate PR)

**Branch:** `fix/mobile-table-responsive`

1. **Wrap all data tables** in `<div class="table-responsive">` containers
2. **Add horizontal scroll indicators** for mobile users
3. **Test all table pages** at 375px viewport

Files touched:
- `backend/templates/schedule.html`
- `backend/templates/reports.html`
- `backend/templates/special_requests.html`
- `backend/templates/upload.html`
- `backend/templates/alerts.html`
- Possibly `backend/static/css/` for scroll indicator styles

### Phase 5: planner Account [REQUIRES SEAN]

This is an ops/config task, not a code change:
1. SSH into Cloud Run or check the `USERS` env var in the production service config
2. Verify `planner` account exists with correct credentials
3. If missing, add it; if wrong password, reset it
4. Test login on production

```bash
gcloud run services describe ddschedulerbot --region us-central1 --format='get(spec.template.spec.containers[0].env)'
```

---

## Priority Order

1. **F-1 (planner account)** — CRITICAL, blocks scheduling workflow, ops fix
2. **F-2 + F-3 (branding + favicon)** — Phase 1, fast PR, visual polish
3. **F-4 (dashboard message)** — Phase 2, confusing UX
4. **F-5 (DataTables error)** — Phase 3, JS bug that could cause subtle issues
5. **F-6 (mobile tables)** — Phase 4, affects mobile users
6. **F-7/F-8/F-9** — Low priority, address when convenient
