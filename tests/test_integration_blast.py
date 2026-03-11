"""
Integration test for blast schedule correctness.

Uses Sean's annotated debug files (OSO060326.xlsx + SDR030626.XLSX) as fixtures.
Column AM in the OSO contains ground-truth annotations:
  - "Part Scheduled"      → WO must appear in blast schedule output
  - "Correctly omitted"   → WO must NOT appear in blast schedule output

To run only these tests:
    pytest tests/test_integration_blast.py -v

Requires the debug fixture files to be present in debugging-test-uploads/.
Tests are automatically skipped if the files are not found.
"""

import pytest
import sys
import os
import pandas as pd
from pathlib import Path

# ---------------------------------------------------------------------------
# Fixture paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent.parent
FIXTURES_DIR = REPO_ROOT / "debugging-test-uploads"

OSO_FILE = FIXTURES_DIR / "OSO060326.xlsx"
SDR_FILE = FIXTURES_DIR / "SDR030626.XLSX"
CORE_MAP_FILE = FIXTURES_DIR / "Core Mapping-test only.xlsx"

FIXTURES_AVAILABLE = OSO_FILE.exists() and SDR_FILE.exists() and CORE_MAP_FILE.exists()

# ---------------------------------------------------------------------------
# Ground truth loader
# ---------------------------------------------------------------------------

def load_ground_truth():
    """
    Read Sean's annotations from OSO column AM ('Notes').
    Returns (scheduled_wos, omitted_wos) — sets of WO number strings.
    """
    df = pd.read_excel(OSO_FILE, sheet_name='RawData', dtype=str)

    scheduled = set()
    omitted = set()

    notes_col = 'Notes'
    wo_col = 'Work Order'

    if notes_col not in df.columns or wo_col not in df.columns:
        return scheduled, omitted

    for _, row in df.iterrows():
        note = str(row.get(notes_col, '') or '').strip().lower()
        wo_raw = row.get(wo_col)
        if not wo_raw or str(wo_raw).strip().lower() == 'nan':
            continue
        try:
            wo = str(int(float(str(wo_raw).strip())))
        except (ValueError, TypeError):
            wo = str(wo_raw).strip()
        if not wo or wo == 'nan':
            continue

        if 'part scheduled' in note:
            scheduled.add(wo)
        elif 'correctly omitted' in note:
            omitted.add(wo)

    return scheduled, omitted


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def ground_truth():
    if not OSO_FILE.exists():
        pytest.skip("Debug fixture OSO060326.xlsx not found")
    scheduled, omitted = load_ground_truth()
    assert len(scheduled) > 0, "No 'Part Scheduled' annotations found — check column AM"
    assert len(omitted) > 0, "No 'Correctly omitted' annotations found — check column AM"
    return scheduled, omitted


@pytest.fixture(scope='module')
def parsed_and_filtered():
    """Parse + filter OSO only (no scheduler needed)."""
    if not OSO_FILE.exists():
        pytest.skip("Debug fixture OSO060326.xlsx not found")

    from parsers.sales_order_parser import parse_open_sales_order
    from parsers.order_filters import should_exclude_order

    raw = parse_open_sales_order(str(OSO_FILE), sheet_name='RawData')

    filtered = []
    excluded = {}
    for order in raw:
        reason = should_exclude_order(
            order.get('part_number'),
            order.get('description'),
            order.get('supply_source'),
            order.get('work_order_status'),
            order.get('oso_op_description'),
        )
        if reason:
            excluded[order['wo_number']] = reason
        else:
            filtered.append(order)

    return filtered, excluded


@pytest.fixture(scope='module')
def blast_schedule_wos():
    """
    Run the full pipeline (parse → filter → merge SDR → schedule)
    and return the set of WO numbers that appear in the blast schedule output.

    Skipped if any required fixture file is missing.
    """
    if not FIXTURES_AVAILABLE:
        pytest.skip("One or more debug fixture files not found in debugging-test-uploads/")

    from parsers.sales_order_parser import parse_open_sales_order
    from parsers.order_filters import should_exclude_order
    from parsers.core_mapping_parser import parse_core_mapping, parse_core_inventory
    from parsers.shop_dispatch_parser import parse_shop_dispatch
    from algorithms.des_scheduler import DESScheduler, WorkScheduleConfig

    # --- Parse OSO ---
    raw_orders = parse_open_sales_order(str(OSO_FILE), sheet_name='RawData')

    # --- Filter ---
    orders = []
    for order in raw_orders:
        reason = should_exclude_order(
            order.get('part_number'), order.get('description'),
            order.get('supply_source'), order.get('work_order_status'),
            order.get('oso_op_description'),
        )
        if not reason:
            orders.append(order)

    # --- Deduplicate by WO# ---
    seen = set()
    unique = []
    for o in orders:
        if o['wo_number'] not in seen:
            seen.add(o['wo_number'])
            unique.append(o)
    orders = unique

    # --- Load SDR ---
    sdr_orders, wip_in_process, on_blaster, _ = parse_shop_dispatch(str(SDR_FILE))

    # Merge SDR orders not already in OSO
    existing = {o['wo_number'] for o in orders}
    for o in sdr_orders:
        if o['wo_number'] not in existing:
            orders.append(o)
            existing.add(o['wo_number'])

    # Remove post-blast WIP (cores occupied)
    wip_wos = {o['wo_number'] for o in wip_in_process}
    orders = [o for o in orders if o.get('wo_number') not in wip_wos]

    # Mark on-blaster priority
    on_blaster_wos = {o['wo_number'] for o in on_blaster}
    for o in orders:
        if o['wo_number'] in on_blaster_wos:
            o['priority'] = 'On Blaster'

    # --- Stamp pre-blast delays ---
    PRE_BLAST_DELAY_BY_OP = {
        '900': 2.25, '940': 2.0, '1220': 1.0,
        '1240': 0.75, '1260': 0.25, '1280': 0.0,
    }
    for o in orders:
        if not o.get('is_rework'):
            op = str(o.get('oso_op_number') or '').strip()
            if op in PRE_BLAST_DELAY_BY_OP:
                o['pre_blast_delay_hours'] = PRE_BLAST_DELAY_BY_OP[op]

    # --- Core mapping ---
    core_mapping = parse_core_mapping(str(CORE_MAP_FILE))
    core_inventory = parse_core_inventory(str(CORE_MAP_FILE))

    # --- Run scheduler ---
    scheduler = DESScheduler(
        orders=orders,
        core_mapping=core_mapping,
        core_inventory=core_inventory,
        working_days=[0, 1, 2, 3, 4],
        shift_hours=12,
        wip_orders=wip_in_process,
    )
    scheduled = scheduler.run()

    blast_wos = {o.wo_number for o in scheduled if o.blast_date}
    all_scheduled_wos = {o.wo_number for o in scheduled}
    return blast_wos, all_scheduled_wos


# ---------------------------------------------------------------------------
# Filter-level tests (fast, no scheduler required)
# ---------------------------------------------------------------------------

class TestExclusionFilters:
    """Verify that orders annotated 'Correctly omitted' are caught at filter time."""

    def test_teco_orders_excluded(self, parsed_and_filtered):
        """All TECO-status WOs should be excluded before scheduling."""
        from parsers.sales_order_parser import parse_open_sales_order
        from parsers.order_filters import should_exclude_order

        raw = parse_open_sales_order(str(OSO_FILE), sheet_name='RawData')
        teco_orders = [o for o in raw if str(o.get('work_order_status', '')).upper().startswith('TECO')]

        assert len(teco_orders) > 0, "No TECO orders found in fixture — check OSO file"
        for o in teco_orders:
            reason = should_exclude_order(
                o.get('part_number'), o.get('description'),
                o.get('supply_source'), o.get('work_order_status'),
                o.get('oso_op_description'),
            )
            assert reason is not None, f"TECO order {o['wo_number']} was not excluded"

    def test_correctly_omitted_not_in_filtered_list(self, ground_truth, parsed_and_filtered):
        """WOs annotated 'Correctly omitted' should not pass through the exclusion filter."""
        _, expected_omitted = ground_truth
        filtered, excluded = parsed_and_filtered
        filtered_wos = {o['wo_number'] for o in filtered}

        leaked = [wo for wo in expected_omitted if wo in filtered_wos]
        assert leaked == [], (
            f"{len(leaked)} 'Correctly omitted' WOs passed through filter: {sorted(leaked)}"
        )

    def test_wo_number_format_consistent(self, parsed_and_filtered):
        """All WO numbers should be clean integer strings (no .0 suffix)."""
        filtered, excluded = parsed_and_filtered
        all_wos = [o['wo_number'] for o in filtered] + list(excluded.keys())
        bad = [wo for wo in all_wos if wo and '.' in str(wo)]
        assert bad == [], f"WO numbers with .0 suffix found (normalization bug): {bad[:10]}"


# ---------------------------------------------------------------------------
# Full-pipeline integration tests
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not FIXTURES_AVAILABLE, reason="Debug fixture files not available")
class TestBlastScheduleIntegration:
    """
    Full pipeline tests: parse → filter → merge → schedule → assert.

    These tests verify Sean's manual annotations against the scheduler output.
    A failing test here means a real scheduling bug was introduced or not yet fixed.
    """

    def test_annotated_scheduled_wos_appear_in_blast(self, blast_schedule_wos, ground_truth):
        """
        All WOs annotated 'Part Scheduled' must appear in the blast schedule output.
        Failures here indicate orders being silently dropped (core miss, filter bug, etc.).
        """
        expected_scheduled, _ = ground_truth
        blast_wos, _ = blast_schedule_wos

        missing = sorted(wo for wo in expected_scheduled if wo not in blast_wos)
        assert missing == [], (
            f"{len(missing)} expected-scheduled WOs are missing from blast output:\n"
            + "\n".join(f"  {wo}" for wo in missing[:20])
            + ("\n  ..." if len(missing) > 20 else "")
        )

    def test_annotated_omitted_wos_absent_from_blast(self, blast_schedule_wos, ground_truth):
        """
        All WOs annotated 'Correctly omitted' must NOT appear in the blast schedule.
        Failures here indicate exclusion filters are not working correctly.
        """
        _, expected_omitted = ground_truth
        blast_wos, _ = blast_schedule_wos

        wrongly_present = sorted(wo for wo in expected_omitted if wo in blast_wos)
        assert wrongly_present == [], (
            f"{len(wrongly_present)} 'Correctly omitted' WOs appeared in blast schedule:\n"
            + "\n".join(f"  {wo}" for wo in wrongly_present[:20])
        )

    def test_blast_schedule_not_empty(self, blast_schedule_wos):
        """Blast schedule must contain at least some orders."""
        blast_wos, _ = blast_schedule_wos
        assert len(blast_wos) > 0, "Blast schedule is empty — scheduler produced no output"
