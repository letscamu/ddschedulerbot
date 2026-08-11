#!/usr/bin/env python3
"""
Local offline diagnostic harness for the DES scheduler.

Runs DataLoader + DESScheduler entirely offline (no Flask, no GCS) against a
directory of input files, mirroring how app._run_schedule_mode builds and runs
the scheduler. Prints diagnostic metrics: order counts, unscheduled breakdown,
blasts-per-day histogram, core-inventory stats, and parts with no mapping hit.

Usage:
    python tools/local_run.py --data-dir /path/to/inputs [--mode 5day_12h] [--no-hot-list]

The data dir should contain one of each input type (most-recent of each pattern
is used): OSO*/Open Sales Order*, SDR*/Shop Dispatch*, Core Mapping*/Core_Mapping*,
HOT LIST*, DCPReport*.
"""
import argparse
import os
import sys
from collections import Counter
from datetime import datetime

# Wire backend onto sys.path (same as des_scheduler.__main__)
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(REPO_ROOT, 'backend')
sys.path.insert(0, BACKEND)

from data_loader import DataLoader                       # noqa: E402
from algorithms.des_scheduler import DESScheduler        # noqa: E402

MODES = {
    '4day_10h': ([0, 1, 2, 3], 10),
    '4day_12h': ([0, 1, 2, 3], 12),
    '5day_12h': ([0, 1, 2, 3, 4], 12),
    '6day_12h': ([0, 1, 2, 3, 4, 5], 12),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data-dir', required=True, help='Directory of input files')
    ap.add_argument('--mode', default='5day_12h', choices=MODES.keys())
    ap.add_argument('--no-hot-list', action='store_true', help='Skip hot list (baseline only)')
    ap.add_argument('--takt', type=int, default=30, help='Takt time in minutes (default 30)')
    ap.add_argument('--inj-buffer', type=float, default=0.5, help='Injection queue buffer hours (default 0.5)')
    ap.add_argument('--start', default=None, help='Start date YYYY-MM-DD (default: engine decides)')
    ap.add_argument('--sample-unsched', type=int, default=0, help='Print N sample unscheduled orders')
    args = ap.parse_args()

    working_days, shift_hours = MODES[args.mode]
    start_date = datetime.strptime(args.start, '%Y-%m-%d').replace(hour=5, minute=30) if args.start else None

    print(f"\n{'#'*72}\n# LOCAL RUN  dir={args.data_dir}  mode={args.mode}\n{'#'*72}")

    loader = DataLoader(data_dir=args.data_dir)
    if not loader.load_all():
        print("[FATAL] loader.load_all() returned False")
        sys.exit(1)

    # --- Core mapping / inventory stats (the suspected lever) ---
    total_cores = sum(len(c) for c in loader.core_inventory.values())
    multi = sum(1 for c in loader.core_inventory.values() if len(c) > 1)
    print(f"\n[CORE DATA] part->core mappings: {len(loader.core_mapping)}")
    print(f"[CORE DATA] unique core numbers: {len(loader.core_inventory)}  "
          f"| total physical cores (suffixes): {total_cores}  | numbers w/ >1 core: {multi}")

    # Parts in orders with no mapping hit
    no_map = [o for o in loader.orders
              if o.get('part_number') and o.get('part_number') not in loader.core_mapping]
    print(f"[CORE DATA] parsed orders with NO core-mapping hit: {len(no_map)} / {len(loader.orders)}")

    # --- Build + run scheduler (mirror app._run_schedule_mode) ---
    def build():
        return DESScheduler(
            orders=loader.orders,
            core_mapping=loader.core_mapping,
            core_inventory=loader.core_inventory,
            working_days=working_days,
            shift_hours=shift_hours,
            wip_orders=loader.wip_in_process_orders,
            takt_time_minutes=args.takt,
            injection_buffer_hours=args.inj_buffer,
        )

    scheduler = build()
    if args.no_hot_list or not loader.hot_list_entries:
        scheduled = scheduler.schedule_orders(start_date=start_date)
        active = scheduler
    else:
        scheduled = scheduler.schedule_orders(start_date=start_date)  # baseline (discarded)
        active = build()
        scheduled = active.schedule_orders(start_date=start_date, hot_list_entries=loader.hot_list_entries)

    # --- Metrics ---
    sched_wo = {o.wo_number for o in scheduled}
    unscheduled = [o for o in loader.orders if o.get('wo_number') not in sched_wo]
    with_blast = [o for o in scheduled if o.blast_date]

    print(f"\n{'='*72}\nRESULTS ({args.mode})\n{'='*72}")
    print(f"  parsed orders      : {len(loader.orders)}")
    print(f"  WIP in-process     : {len(loader.wip_in_process_orders)}")
    print(f"  scheduled          : {len(scheduled)}")
    print(f"  with blast date    : {len(with_blast)}")
    print(f"  UNSCHEDULED        : {len(unscheduled)}")
    print(f"  pending core       : {len(getattr(active, 'pending_core_orders', []))}")

    # Blasts-per-day histogram + near-term fill
    by_day = Counter(o.blast_date.date() for o in with_blast)
    days = sorted(by_day)
    print(f"\n  blast span: {days[0] if days else '-'} .. {days[-1] if days else '-'}  "
          f"({len(days)} distinct days)")
    if days:
        first2 = sum(by_day[d] for d in days[:2])
        print(f"  >>> first 2 working days fill: {first2}  (target ~60-70)")
        print("  per-day histogram:")
        for d in days:
            bar = '#' * min(by_day[d], 60)
            print(f"     {d}  {by_day[d]:3d}  {bar}")

    if args.sample_unsched and unscheduled:
        print(f"\n  sample unscheduled (first {args.sample_unsched}):")
        for o in unscheduled[:args.sample_unsched]:
            print(f"     WO {o.get('wo_number')} | {o.get('part_number')} | "
                  f"op {o.get('current_operation')} | mapped={o.get('part_number') in loader.core_mapping}")


if __name__ == '__main__':
    main()
