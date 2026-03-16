# DynaBot Browser Test Plan — Playwright MCP

**Purpose:** Systematically test every page, feature, and workflow on dynabot.biz using Playwright MCP in Claude Code.

**Pre-requisites:**
- Playwright MCP configured in `.mcp.json`
- Test credentials for each role (Admin, Planner, MfgEng, CustomerService, Operator, Guest)
- Pre-loaded sample files from `Scheduler Bot Info/`

---

## Phase 1: Authentication & Access Control

### 1.1 Login/Logout
- [ ] Navigate to dynabot.biz — verify redirect to login page
- [ ] Test login with valid Admin credentials
- [ ] Test login with invalid credentials — verify error message
- [ ] Test logout — verify session ends, redirect to login
- [ ] Test accessing protected pages without login — verify 401/redirect

### 1.2 Role-Based Access
- [ ] Login as each role and verify navbar shows only permitted menu items
- [ ] As Guest: verify cannot access /api/generate, /api/planner/*, user management
- [ ] As Planner: verify can access planner and schedule generation, but not user management
- [ ] As MfgEng: verify can access core-mapping but not planner or schedule generation
- [ ] As Admin: verify full access to all pages and API endpoints

---

## Phase 2: Page Rendering & Navigation

### 2.1 All Pages Load Without Errors
- [ ] `/` — Dashboard loads, shows overview cards
- [ ] `/upload` — Upload page renders with file dropzone/input
- [ ] `/schedule` — Schedule page loads (empty or with data)
- [ ] `/reports` — Reports page renders
- [ ] `/simulation` — Simulation page loads
- [ ] `/planner` — Planner page loads (role-restricted content)
- [ ] `/special-requests` — Special requests page renders
- [ ] `/updates` — Update log / Flies & Swatters page loads
- [ ] `/mfg-eng-review` — MfgEng review page renders
- [ ] `/user-management` — User management page (Admin only)
- [ ] `/core-mapping` — Core mapping visualization loads
- [ ] `/notifications` — Notifications page renders
- [ ] `/alerts` — Alerts page renders

### 2.2 Navigation
- [ ] All navbar links work and navigate correctly
- [ ] Version badge displays current version
- [ ] Responsive layout — check mobile breakpoint behavior
- [ ] 404 page renders for invalid URLs
- [ ] Browser back/forward works correctly

---

## Phase 3: File Upload & Data Loading

### 3.1 File Upload
- [ ] Upload Sales Order file (Open_Sales_Order_Example.xlsx) — verify success
- [ ] Upload Shop Dispatch file — verify success
- [ ] Upload Core Mapping file — verify success
- [ ] Upload Process Map (Stators Process VSM) — verify success
- [ ] Upload Hot List file — verify success
- [ ] Upload DCP Report file — verify success (if available)
- [ ] Verify uploaded files appear in file list (`/api/files`)
- [ ] Test uploading invalid file type (e.g., .txt) — verify rejection
- [ ] Test uploading oversized file (>50MB) — verify rejection

### 3.2 File Processing
- [ ] Verify Sales Order scrubbing removes sensitive columns
- [ ] Verify file type auto-detection works for each file pattern
- [ ] Verify upload timestamps are correct

---

## Phase 4: Schedule Generation & Viewing

### 4.1 Generate Schedule
- [ ] With required files uploaded, trigger schedule generation
- [ ] Verify generation completes without errors
- [ ] Verify schedule data appears on `/schedule` page
- [ ] Verify schedule data available via `/api/schedule`
- [ ] Test generation with missing required files — verify clear error message

### 4.2 Schedule Display
- [ ] Schedule table renders with all expected columns
- [ ] DataTables features work (sort, search, pagination)
- [ ] Schedule reorder functionality works (drag-and-drop or UI controls)
- [ ] Clear reorder resets to original order

### 4.3 Reports
- [ ] Reports list populates after schedule generation
- [ ] Download each report type — verify valid Excel file
- [ ] Verify report content matches schedule data

---

## Phase 5: Planner Workflow

### 5.1 Scenario Simulation
- [ ] Run multi-scenario simulation — verify results render
- [ ] Compare scenarios side-by-side
- [ ] Set base schedule from a scenario
- [ ] Run custom scenario simulation
- [ ] Verify planner status tracking (`/api/planner/status`)

### 5.2 Special Requests Integration
- [ ] Create a special request from the special requests page
- [ ] Simulate schedule with requests (`/api/planner/simulate-with-requests`)
- [ ] Preview impact of special requests
- [ ] Approve/disapprove requests
- [ ] Verify hot list integration from file

### 5.3 Final Schedule
- [ ] Generate final schedule
- [ ] Publish schedule
- [ ] Verify published state persists

---

## Phase 6: Special Requests & Order Holds

### 6.1 Special Requests
- [ ] Create new special request with all fields
- [ ] View special requests list
- [ ] Impact preview — verify analysis displays correctly
- [ ] Test creating request for non-existent order — verify handling

### 6.2 Order Holds
- [ ] Place hold on an order
- [ ] Verify held orders appear in hold list
- [ ] Remove hold from order
- [ ] Verify hold affects schedule generation

---

## Phase 7: User Management (Admin Only)

### 7.1 User CRUD
- [ ] List all users
- [ ] Create new user — verify minimum requirements (3 char username, 6 char password)
- [ ] Update user role
- [ ] Disable user account — verify they cannot login
- [ ] Re-enable user account
- [ ] Reset user password
- [ ] Test creating duplicate username — verify rejection
- [ ] Test disabling last admin — verify prevention

### 7.2 Self-Service
- [ ] Change own password — verify requires current password
- [ ] Test incorrect current password — verify rejection

---

## Phase 8: Core Mapping

- [ ] View core mapping visualization
- [ ] Verify data loads from uploaded Core Mapping file
- [ ] Check role restrictions (admin/planner/mfgeng only)

---

## Phase 9: Alerts & Notifications

### 9.1 Alerts
- [ ] Generate alert report (after schedule exists)
- [ ] Verify alert categories: late orders, promise date risk, core shortage, utilization
- [ ] View alerts on alerts page

### 9.2 Notifications
- [ ] View notifications list
- [ ] Mark single notification as read
- [ ] Mark all notifications as read
- [ ] Verify notification count in navbar updates

---

## Phase 10: Feedback System

### 10.1 Submit Feedback
- [ ] Submit bug report with description
- [ ] Submit feature request
- [ ] Submit feedback with file attachment (image)
- [ ] Submit feedback with Excel attachment
- [ ] Submit example file
- [ ] View "My Feedback" list

### 10.2 Admin Feedback Management
- [ ] View all feedback (admin)
- [ ] Update feedback status (New → In Progress → Resolved)
- [ ] Update dev processing status
- [ ] Export all feedback
- [ ] Download feedback attachments

---

## Phase 11: Simulation Page

- [ ] Load simulation data visualization
- [ ] Verify charts/graphs render with schedule data
- [ ] Test simulation with no data — verify graceful handling

---

## Phase 12: Error Handling & Edge Cases

- [ ] Navigate to non-existent URL — verify 404 page
- [ ] Test API endpoints with missing parameters — verify error responses
- [ ] Test concurrent file uploads
- [ ] Test session timeout behavior
- [ ] Verify CSRF protection on forms
- [ ] Test XSS resistance in user input fields (feedback, special requests)

---

## Execution Notes

- **Screenshots:** Take screenshots of every page and any errors found
- **Role rotation:** Run Phase 2 for each role to verify access control
- **Data dependency:** Phases 4-6 require Phase 3 uploads to complete first
- **Document findings:** Record each issue with: page, steps to reproduce, expected vs actual, severity
