# DDSchedulerBot / DynaBot — Session Memory

**Last updated:** June 24, 2026
**Current deployed version:** MVP 2.0.5 (CLAUDE.md); engine investigation on branch `fix/scheduler-undersched-diag`

---

## Session: June 2026 — Scheduler under-scheduling / wrong-timing investigation

**Symptom:** today's run (5day/12h, OSO/SDR 06-22) put only ~40 blasts in 2 days (Sean expects 60–70),
456 orders Unscheduled, big late "clump." Built offline harness `tools/local_run.py` (no Flask/GCS;
point `--data-dir` at a folder of inputs) — reproduces live output exactly (422 sched / 456 unsched).

**Root-cause decomposition (was MOSTLY data/config, NOT engine bugs):**
- 174 parts not in core mapping (183/199 numeric; genuine absence, not format) → no core → unscheduled.
- 152 orders with rubber type no Desma runs (XP 121, 1A, NED1, blank). Only **HR/XE/XR/XD valid**;
  XP/1A/NED1 are obsolete-PN/bad data (Sean to validate — exceptions workbook delivered).
- 74 rotors (`R…/-SLD` descriptions, numeric PNs) leaking past the exclusion filter.
- Stale core mapping was a RED HERRING (524→529 cores w/ fresh). Takt + changeovers also red herrings
  (engine plans **0** changeovers; machine-selection already avoids them).

**Fixes landed (verified, tests 56 pass):** rotor exclusion via description (`order_filters.py`);
invalid-rubber orders routed to pending w/ reason (`des_scheduler._classify_orders`);
`injection_buffer_hours` knob (default 0.5 = no change; ≥2 clears a 33-order stall + 500-empty-slot stop).

**THE UNSOLVED CORE PROBLEM (next session — injection redesign):** near-term collapses to ~5/day and
CANNOT be tuned out via takt/buffer/changeovers. Proven: bottleneck-OFF → 96/2days, ON → 30; tuning
buffer/takt stays pinned at ~29. Cause = injection-admission ARCHITECTURE: blast admission gates on a
machine reservation using a 3.85h **working-time** lead (`_estimate_injection_arrival` via advance_time)
mixed with wall-clock machine bookings (`_reserve_injection_machine` uses raw timedelta) → day-1 arrivals
collapse into one window injection can't drain. Real capacity ≈ 50–60/day (both shifts, 25–30/shift;
3 machines/rubber ÷ 0.8–1.5h inj time). **Fix = model injection as a true capacity-limited station**
(likely in the event-loop sim, not the blast-admission heuristic). Key spots: `_check_injection_bottleneck`
/ `_reserve_injection_machine` / `_estimate_injection_arrival` (des_scheduler.py ~1036-1127),
blast loop `_schedule_blast_arrivals` (~1395-1620).

**Data actions for Sean:** validate 152 obsolete-PN list; add ~125 missing stators to mapping; upload
fresh Core Mapping to prod via app (prod reads GCS, not the repo copy). Local feedback test store
(`data/state/user_feedback.json`, not git-tracked) has old March test data → 1 local feedback test fails;
prod GCS unaffected.

---

---

## Product Owner

- **Sean** (GitHub: InnerLooper85)
- Runs Claude Code from Windows (`C:\Users\SeanFilipow\CAMU\ddschedulerbot`)
- Prefers fast iteration — owner direct deploy in CLAUDE.md
- Uses MBP + Deglazing protocols (full specs in CLAUDE.md)

---

## Current State of the App (MVP 2.0)

- Full DES scheduling engine with 6-tier priority: On Blaster > Hot-ASAP > Hot-Dated > Rework > Normal > CAVO
- Web app: Dashboard, Upload, Schedule, Reports, Simulation, Planner Workflow, Update Log
- 4/5-day schedule toggle, 3-scenario planner comparison (4d/10h, 4d/12h, 5d/12h)
- BLAST schedule, Master Schedule, Core Oven Schedule, Resource Utilization exports
- All outputs now include **Unscheduled Orders** tab (added Mar 2026)
- **BLAST schedule** includes Op# and Current Op Description columns from OSO
- WIP state tracking: op 1300 = On Blaster (priority 0), op 1340–1620 = core pre-marked as occupied
- Pre-blast lead times from Stators VSM applied at scheduling time
- Integration test suite: `tests/test_integration_blast.py` uses annotated OSO as ground truth
- Deployed on Cloud Run, files on GCS (`gs://ddschedulerbot-files`)
- Timezone: `America/Chicago` set in both GitHub Actions workflows

### Priority Tiers
0. **On Blaster** — currently on the blaster (op 1300 in SDR), blast immediately
1. **Hot-ASAP** — hot list, no date
2. **Hot-Dated** — hot list with need-by date
3. **Rework** — rubber removal required (op desc contains RUBBER REMOVAL / REMOV RB)
4. **Normal** — standard scheduling
5. **CAVO** — lowest priority

### WIP Core Pre-marking
- **Op 1300**: core is available → scheduled as priority 0
- **Op 1340 (Tube Prep)**: remaining ~3.5h + assembly + downstream
- **Op 1360 (Assembly)**: remaining ~0.2h + downstream
- **Op 1380/1600/1610 (Injection/Cure/Quench)**: elapsed-time subtraction applied
- **Op 1620+**: core returned soon (~1.25h post-cure)

### Pre-blast Delays (from Stators Process VSM)
- Op 900 (Receive Tube): 2.25h before blast-ready
- Op 940 (Counterbore): 2.0h
- Op 1220 (Induction Coil): 1.0h
- Op 1240 (Stamp & Inspect): 0.75h
- Op 1260 (Transfer to Supermarket): 0.25h
- Op 1280 (Supermarket): 0h (ready)

---

## Active Debugging Session (Mar 2026)

### Confirmed Fixed
- TECO orders correctly excluded
- OSP Canada correctly excluded
- Rotor/bearing filters working
- Timezone set to America/Chicago
- Scheduler start date advances to next working day when run after shift start
- Op 1300 on-blaster orders schedule as priority 0
- WO number normalization (`normalize_wo_number()`) — fixes silent SDR/OSO mismatch
- Pre-blast delays applied for ops 900/940/1220/1240/1260/1280

### Known Open Bugs (from OSO060326 annotation session)
- **Some op 1300 orders missing from blast schedule** — only 5 of ~12 shown; WO normalization fix may resolve this, needs retest
- **Some rework orders (op 1000/1100 RUBBER REMOVAL) not scheduling** — likely core availability or rework detection gap
- **Some op 1240/1260/1280 orders missing** — cores 74, 510, 450, 501 may not be in core mapping
- **Op 1240 scheduling timing** — some scheduled too early (pre-blast delay now added), some too late (priority ordering issue)

### Debug Fixture Files
Located in `debugging-test-uploads/`:
- `OSO060326.xlsx` — annotated OSO, col AM has "Part Scheduled" / "Correctly omitted" ground truth
- `SDR030626.XLSX` — Shop Dispatch used for the debug run
- `Core Mapping-test only.xlsx`
- `DCPReport (36).xlsx`

---

## Key Files

| What | Where |
|------|-------|
| Flask app + routes | `backend/app.py` |
| DES engine | `backend/algorithms/des_scheduler.py` |
| ScheduledOrder / ScheduledOperation | `backend/algorithms/scheduler.py` |
| Data loader (all file parsing + enrichment) | `backend/data_loader.py` |
| Exclusion filters + normalize_wo_number | `backend/parsers/order_filters.py` |
| OSO parser | `backend/parsers/sales_order_parser.py` |
| Shop Dispatch parser | `backend/parsers/shop_dispatch_parser.py` |
| Excel exporter (all reports) | `backend/exporters/excel_exporter.py` |
| GCS storage | `backend/gcs_storage.py` |
| Integration test (ground truth) | `tests/test_integration_blast.py` |
| Project instructions | `CLAUDE.md` |

---

## Deployment

- **Production Cloud Run:** `ddschedulerbot`, auto-deploys from `master`
- **Dev Cloud Run:** `ddschedulerbot-dev`, auto-deploys from `dev`
- **GCP Project:** `ddschedulerbot` (account: `sean@consultantbot.bar`)
- **GCS Buckets:** `gs://ddschedulerbot-files` (prod), `gs://ddschedulerbot-files-dev` (dev)
- **Domain:** dynabot.biz
- **Timezone:** `TZ=America/Chicago` in both workflow env blocks

---

## Key Conventions (quick ref)

- OSO sheet name: `RawData` (not "OSO") — `sheet_name='RawData'` in parser calls
- WO numbers: always normalized via `normalize_wo_number()` — produces clean integer strings
- SDR + OSO merge: SDR adds orders not in OSO; priority/on_blaster stamp happens after merge
- `oso_op_number` / `oso_op_description` = from OSO "Operation Number" / "Current Operation Description"
- `current_operation` in SDR = the SAP op number at time of dispatch (1300, 1340, etc.)
- Unscheduled orders = `loader.orders` minus `scheduled_orders` — exported as tab in both schedules
