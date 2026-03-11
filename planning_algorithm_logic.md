# EstradaBot — Planning Algorithm Logic

**Document Version:** 1.0
**Date:** February 4, 2026
**Product Version:** MVP 1.0 (with MVP 1.1 planned changes noted)

---

## Purpose

This document describes the scheduling algorithm's logic, rules, and constraints as implemented in `backend/algorithms/des_scheduler.py`. Rules that are **flagged for future review** are marked with a ⚠️ flag icon.

---

## 1. Scheduling Approach

The scheduler uses a **Discrete Event Simulation (DES)** with **pipeline-based flow**. Orders flow through production stations sequentially, with multiple orders in-process simultaneously at different stations. The simulation processes events in chronological order and tracks resource availability in real time.

---

## 2. Work Schedule Rules

### 2.1 Shift Configuration

| Parameter | Value | Notes |
|-----------|-------|-------|
| Work days | Monday - Thursday (4-day week) | MVP 1.1: Adding 5-day option |
| Day shift | 5:00 AM - 5:00 PM (12 hours) | |
| Night shift | 5:00 PM - 5:00 AM (12 hours) | |
| Handover | 30 minutes per shift start | **MVP 1.1 change**: Was 20 min, now 30 min |
| First BLAST (day) | 5:30 AM | **MVP 1.1 change**: Was 5:20 AM |
| First BLAST (night) | 5:30 PM | **MVP 1.1 change**: Was 5:20 PM |

### 2.2 Break Schedule

**Day Shift:**
- 9:00 AM — 15-minute break
- 11:00 AM — 45-minute lunch
- 3:00 PM — 15-minute break

**Night Shift:**
- 9:00 PM — 15-minute break
- 11:00 PM — 45-minute lunch
- 3:00 AM — 15-minute break

### 2.3 Time Advancement Rules

- Most operations pause during breaks and non-working hours
- **Exception:** CURE and QUENCH operations continue during breaks (they are thermal processes that cannot be interrupted)
- All operations pause during non-working days (weekends/holidays)

---

## 3. Priority System

### 3.1 Five-Tier Priority Order

Orders are sorted into these tiers and scheduled in this exact order:

| Tier | Name | Description | Sort Within Tier |
|------|------|-------------|-----------------|
| 1 | Hot-ASAP | Hot list orders marked "ASAP" | By date request made (ascending), then row position |
| 2 | Hot-Dated | Hot list orders with a specific need-by date | By need-by date (ascending), then date request made, then row position |
| 3 | Rework | Orders requiring re-BLAST (REMOV RB) | By creation date (FIFO) |
| 4 | Normal | All standard orders | By creation date (FIFO) |
| 5 | CAVO | Orders for customer "CAVO DRILLING MOTORS" | By creation date (FIFO) |

### 3.2 Priority Rules

- Priority tiers are **absolute**: a Hot-ASAP order always schedules before a Normal order, regardless of creation date
- Within a tier, FIFO (First-In-First-Out) by creation date is the default
- Hot list entries can override the rubber type via "REDLINE FOR [type] INJECTION" comments

---

## 4. BLAST Arrival Scheduling

### 4.1 Takt Time

- BLAST arrivals are spaced at **30-minute intervals** (takt time)
- Each takt slot, the scheduler scans the priority-sorted queue and selects the first order whose core is available

### 4.2 Core Availability Check

- Before assigning an order to a BLAST slot, the scheduler verifies a physical core is available
- If no core is available for any remaining order, the scheduler jumps forward to the earliest core return time
- Hot list orders with no core available ever are tracked as "core shortages" in the Impact Analysis report

### 4.3 Rework Delay

- Rework orders have a lead time delay before BLAST:
  - Currently at REMOV RB work center: **36 hours** delay
  - REMOV RB still upcoming in routing: **48 hours** delay

### 4.4 Rubber Type Alternation ⚠️ FLAGGED RULE

> **Flag Reason:** This rule was requested by the planning team to encourage user uptake. However, the product owner notes it may not ultimately matter and could be detrimental to the planning system's optimization. It is implemented but subject to future review and possible removal.

**Rule (MVP 1.1):**
- When multiple orders in the same priority tier are available for the next BLAST slot, prefer an order with a **different rubber type** than the previously scheduled order
- Target sequence: XE → HR → XE → HR (alternating)
- This is a **tiebreaker within priority tiers** — it never overrides priority ordering
- XD and XR orders should be planned for Desma 5 and grouped on the same day, but spaced with HR/XE orders between them
- If only one rubber type is available, schedule it regardless (do not leave slots empty)

**Rationale from planning team:** Alternating rubber types is believed to improve production flow at the injection stations by distributing work more evenly across Desma machines.

**Concern:** If rubber type alternation conflicts with core availability optimization, it may increase overall turnaround time. Monitor after implementation.

---

## 5. Production Stations

### 5.1 Station Pipeline

Orders flow through these stations in sequence:

```
BLAST → TUBE PREP ─┐
                    ├→ ASSEMBLY → INJECTION → CURE → QUENCH → DISASSEMBLY
       CORE OVEN ──┘     → BLD END CUTBACK → INJ END CUTBACK → [CUT THREADS*] → INSPECT
```

*CUT THREADS is skipped for reline orders (part number starts with "XN")

### 5.2 Station Configuration

| Station | Cycle Time (hrs) | Machines/Capacity | Special Behavior |
|---------|-------------------|-------------------|------------------|
| BLAST | 0.15 | 1 machine | Entry point; 30-min takt between arrivals |
| TUBE PREP | 3.5 | 18 capacity (batch) | Concurrent with CORE OVEN |
| CORE OVEN | 2.5 | 12 capacity (batch) | Concurrent with TUBE PREP |
| ASSEMBLY | 0.2 | 1 machine | Waits for both TUBE PREP + CORE OVEN |
| INJECTION | Variable | 5 machines (Desma 1-5) | Bottleneck; machine selection by rubber type |
| CURE | Variable | 16 capacity (batch) | Continues during breaks |
| QUENCH | Variable | 16 capacity (batch) | Continues during breaks |
| DISASSEMBLY | Variable | 1 machine | |
| BLD END CUTBACK | 0.25 | 2 machines | |
| INJ END CUTBACK | 0.25 | 2 machines | |
| CUT THREADS | 1.0 | 1 machine | New stators only |
| INSPECT | 0.25 | 1 machine | Final station |

Variable times (INJECTION, CURE, QUENCH, DISASSEMBLY) come from Core Mapping file, keyed by part number.

### 5.3 Concurrent Operations

- TUBE PREP and CORE OVEN start simultaneously after BLAST completion
- ASSEMBLY cannot begin until BOTH are complete
- The scheduler uses max(TUBE PREP time, CORE OVEN time) to determine when ASSEMBLY can start

---

## 6. Injection Machine Assignment

### 6.1 Machine Rubber Type Mapping

| Machine | Primary Rubber Types |
|---------|---------------------|
| Desma 1 | HR |
| Desma 2 | HR |
| Desma 3 | XE |
| Desma 4 | XE |
| Desma 5 | XR, XD, XE, HR (flex) |

### 6.2 Machine Selection Priority

1. Primary machine already set up for the order's rubber type (no changeover needed)
2. Primary machine available (changeover may be needed)
3. Flex machine (Desma 5)
4. Any primary machine with earliest availability

### 6.3 Changeover Time

- **1 hour** penalty when switching rubber types on any machine
- Minimizing changeovers is a scheduling goal

### 6.4 XD/XR Handling (MVP 1.1)

- XD and XR orders should be assigned to Desma 5
- Group XD/XR orders on the same production day when possible
- Space them with HR/XE orders between for machine balance

---

## 7. Core Management

### 7.1 Core Lifecycle

```
Available → CORE OVEN (2.5 hrs) → ASSEMBLY → INJECTION → CURE → QUENCH
→ DISASSEMBLY → CLEANING (45 min) → Available
```

### 7.2 Core Assignment Rules

- Each part number requires a specific core number (from Core Mapping)
- Multiple physical cores may exist for the same core number (identified by suffix: A, B, C, etc.)
- A core can only be used for one order at a time
- Core return time = sum of all operations from TUBE PREP through CLEANING
- If no core is available, the order is queued until one returns

---

## 8. Order Classification and Filtering

### 8.1 Product Type Classification

- Part number starts with "XN" → **Reline** (80%+ of volume)
- Part number starts with "S" + digit → **New Stator**
- Other → **Unknown** (excluded)

### 8.2 Order Exclusion Rules

Orders are excluded from scheduling if any of these conditions match:

| Rule | Condition |
|------|-----------|
| Inventory | Supply source contains "INVENTORY" |
| Repair | Part number or description contains "REPAIR" |
| Customer Owned | Description contains "CUSTOMER OWNED" or starts with "STATOR, CUSTOMER" |
| Analysis | Description contains "ANALYSIS" |
| Rotors | Part number starts with R or C followed by a digit |
| Housings/Blanks | Part number or description contains HSG, HOUSING, BLNK, or BLANK |

### 8.3 Rework Detection

- `current_operation` contains "RUBBER REMOVAL" or "REMOV RB" → rework order
- Currently at REMOV RB → 36 hours lead time
- REMOV RB in remaining work centers → 48 hours lead time

---

## 9. Calculations

### 9.1 Turnaround Time

- **All orders (MVP 1.1):** `Completion Date - Creation Date` (in days)
- Creation date = `wo_creation_date` from Open Sales Order (falls back to `created_on`)
- **Note:** Previously, new stators used `actual_start_date` from Pegging Report. This was removed in MVP 1.1.

### 9.2 On-Time Status

- **On Time:** Completion Date ≤ Basic Finish Date
- **At Risk:** (Basic Finish Date - Completion Date) ≤ 2 days
- **Late:** Completion Date > Basic Finish Date
- Note: Uses SAP Basic Finish Date, not Promise Date, for on-time determination

---

## 10. Flagged Rules Registry

| Rule | Section | Flag Reason | Added |
|------|---------|-------------|-------|
| Rubber Type Alternation in BLAST Sequence | 4.4 | May not ultimately matter; could be detrimental to optimization. Implementing to encourage user uptake. | MVP 1.1 |

---

**Document End**
