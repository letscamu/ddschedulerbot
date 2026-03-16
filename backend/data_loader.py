"""
Data Loader
Loads and validates all input data files.
"""

import os
import glob
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional

from parsers import (
    parse_open_sales_order,
    parse_core_mapping,
    parse_core_inventory,
    parse_process_map,
    validate_orders,
    validate_core_mapping,
    should_exclude_order,
    get_exclusion_summary,
    parse_shop_dispatch,
    parse_hot_list,
    sort_hot_list_entries,
    parse_dcp_report
)


class DataLoader:
    """Manages loading and validation of all data files."""

    def __init__(self, data_dir: str = "../Scheduler Bot Info"):
        self.data_dir = Path(data_dir)
        self.orders = []
        self.shop_dispatch_orders = []
        self.wip_in_process_orders = []
        self.on_blaster_orders = []
        self.excluded_orders = []
        self.core_mapping = {}
        self.core_inventory = {}
        self.operations = {}
        self.hot_list_entries = []  # From Hot List file
        self.supermarket_locations = {}  # From DCP report: WO# -> location
        self.validation_results = {}

    def _find_most_recent_file(self, pattern: str) -> Optional[Path]:
        """
        Find the most recently modified file matching a glob pattern.

        Args:
            pattern: Glob pattern to match (e.g., "Open Sales Order*.xlsx")
                     Also tries underscore variant (e.g., "Open_Sales_Order*.xlsx")

        Returns:
            Path to most recent matching file, or None if no matches
        """
        # Try both space and underscore variants
        patterns_to_try = [pattern]
        if ' ' in pattern:
            patterns_to_try.append(pattern.replace(' ', '_'))
        elif '_' in pattern:
            patterns_to_try.append(pattern.replace('_', ' '))

        matches = []
        for p in patterns_to_try:
            search_path = self.data_dir / p
            matches.extend(glob.glob(str(search_path)))

        if not matches:
            return None

        # Sort by modification time, newest first
        matches.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        return Path(matches[0])

    def _filter_orders(self, orders: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Tuple]]:
        """
        Apply exclusion filters to orders.

        Args:
            orders: List of order dictionaries

        Returns:
            Tuple of (filtered orders, excluded orders with reasons)
        """
        filtered = []
        excluded = []

        for order in orders:
            exclusion_reason = should_exclude_order(
                order.get('part_number'),
                order.get('description'),
                order.get('supply_source'),
                order.get('work_order_status'),
                order.get('oso_op_description'),
                order.get('oso_op_number')
            )

            if exclusion_reason:
                excluded.append((order, exclusion_reason))
            else:
                filtered.append(order)

        return filtered, excluded

    def load_shop_dispatch(self, filepath: Optional[str] = None) -> bool:
        """
        Load Shop Dispatch data.

        Args:
            filepath: Optional explicit filepath. If None, finds most recent file.

        Returns:
            True if loaded successfully, False otherwise
        """
        if filepath:
            dispatch_file = Path(filepath)
        else:
            dispatch_file = self._find_most_recent_file("Shop Dispatch*.XLSX")
            if not dispatch_file:
                dispatch_file = self._find_most_recent_file("Shop Dispatch*.xlsx")
            if not dispatch_file:
                dispatch_file = self._find_most_recent_file("SDR*.XLSX")
            if not dispatch_file:
                dispatch_file = self._find_most_recent_file("SDR*.xlsx")

        if not dispatch_file or not dispatch_file.exists():
            print("  No Shop Dispatch file found (optional)")
            return False

        print(f"  Loading: {dispatch_file.name}")
        self.shop_dispatch_orders, self.wip_in_process_orders, self.on_blaster_orders, dispatch_excluded = parse_shop_dispatch(str(dispatch_file))
        self.excluded_orders.extend(dispatch_excluded)

        print(f"  [OK] Loaded {len(self.shop_dispatch_orders)} orders from Shop Dispatch")
        return True

    # Pegging Report loading removed in MVP 1.1 — turnaround now uses creation_date for all orders

    def load_hot_list(self, filepath: Optional[str] = None) -> bool:
        """
        Load Hot List data for priority scheduling.

        Args:
            filepath: Optional explicit filepath. If None, finds most recent file.

        Returns:
            True if loaded successfully, False otherwise
        """
        if filepath:
            hot_list_file = Path(filepath)
        else:
            # Try multiple patterns for hot list files
            hot_list_file = self._find_most_recent_file("HOT LIST*.xlsx")
            if not hot_list_file:
                hot_list_file = self._find_most_recent_file("HOT_LIST*.xlsx")
            if not hot_list_file:
                hot_list_file = self._find_most_recent_file("Hot List*.xlsx")

        if not hot_list_file or not hot_list_file.exists():
            print("  No Hot List file found (optional)")
            return False

        print(f"  Loading: {hot_list_file.name}")
        raw_entries = parse_hot_list(str(hot_list_file))

        # Sort entries by priority
        self.hot_list_entries = sort_hot_list_entries(raw_entries)

        # Print priority breakdown
        asap_count = sum(1 for e in self.hot_list_entries if e.get('is_asap'))
        dated_count = sum(1 for e in self.hot_list_entries if not e.get('is_asap') and e.get('need_by_date'))
        override_count = sum(1 for e in self.hot_list_entries if e.get('rubber_override'))

        print(f"  [OK] Loaded {len(self.hot_list_entries)} hot list entries")
        print(f"      ASAP: {asap_count}")
        print(f"      Dated: {dated_count}")
        print(f"      With rubber override: {override_count}")

        return True

    def load_dcp_report(self, filepath: Optional[str] = None) -> bool:
        """
        Load DCP report to extract supermarket locations.

        Args:
            filepath: Optional explicit filepath. If None, finds most recent file.

        Returns:
            True if loaded successfully, False otherwise
        """
        if filepath:
            dcp_file = Path(filepath)
        else:
            dcp_file = self._find_most_recent_file("DCPReport*.xlsx")
            if not dcp_file:
                dcp_file = self._find_most_recent_file("DCP Report*.xlsx")
            if not dcp_file:
                dcp_file = self._find_most_recent_file("DCP_Report*.xlsx")

        if not dcp_file or not dcp_file.exists():
            print("  No DCP Report file found (optional)")
            return False

        print(f"  Loading: {dcp_file.name}")
        self.supermarket_locations = parse_dcp_report(str(dcp_file))

        if self.supermarket_locations:
            # Stamp supermarket locations onto matching orders
            matched = 0
            for order in self.orders:
                wo = order.get('wo_number')
                if wo and wo in self.supermarket_locations:
                    order['supermarket_location'] = self.supermarket_locations[wo]
                    matched += 1
            print(f"  [OK] Matched {matched} orders with supermarket locations")

        return True

    def load_all(self) -> bool:
        """
        Load all data files.

        Returns:
            True if successful, False if errors
        """
        print("=" * 70)
        print("LOADING ALL DATA FILES")
        print("=" * 70)

        try:
            # 1. Load Sales Orders (find most recent file)
            print("\n[1/6] Loading Open Sales Order...")
            sales_order_file = self._find_most_recent_file("Open Sales Order*.xlsx")
            if not sales_order_file:
                sales_order_file = self._find_most_recent_file("OSO*.xlsx")
            if not sales_order_file:
                sales_order_file = self._find_most_recent_file("OSO*.XLSX")
            if not sales_order_file:
                print("[ERROR] No Open Sales Order file found!")
                return False

            print(f"  Loading: {sales_order_file.name}")
            raw_orders = parse_open_sales_order(str(sales_order_file), sheet_name='RawData')

            # Apply filters to sales orders
            print("\n[2/6] Filtering Sales Orders...")
            self.orders, sales_excluded = self._filter_orders(raw_orders)
            self.excluded_orders.extend(sales_excluded)

            print(f"  Raw orders: {len(raw_orders)}")
            print(f"  After filtering: {len(self.orders)}")
            print(f"  Excluded: {len(sales_excluded)}")

            # Deduplicate by WO# (SAP exports can have multiple rows per WO)
            seen_wo = set()
            unique_orders = []
            for order in self.orders:
                wo = order.get('wo_number')
                if wo and wo not in seen_wo:
                    seen_wo.add(wo)
                    unique_orders.append(order)
            if len(unique_orders) < len(self.orders):
                print(f"  Deduplicated: {len(self.orders)} -> {len(unique_orders)} (removed {len(self.orders) - len(unique_orders)} duplicate WO#s)")
            self.orders = unique_orders

            order_validation = validate_orders(self.orders)
            self.validation_results['orders'] = order_validation

            if not order_validation['is_valid']:
                print("[ERROR] CRITICAL: Sales order validation failed")
                return False

            # 3. Load Shop Dispatch (optional)
            print("\n[3/6] Loading Shop Dispatch...")
            self.load_shop_dispatch()

            # Merge Shop Dispatch orders (avoid duplicates by WO#)
            if self.shop_dispatch_orders:
                existing_wo_numbers = {o['wo_number'] for o in self.orders}
                new_from_dispatch = 0

                for dispatch_order in self.shop_dispatch_orders:
                    if dispatch_order['wo_number'] not in existing_wo_numbers:
                        self.orders.append(dispatch_order)
                        existing_wo_numbers.add(dispatch_order['wo_number'])
                        new_from_dispatch += 1

                print(f"  Added {new_from_dispatch} orders from Shop Dispatch (not in Sales Orders)")

            print(f"\n[OK] Total orders after merge: {len(self.orders)}")

            # 3b. Pegging Report — REMOVED in MVP 1.1
            # Turnaround now uses creation_date for all orders (relines and new stators)

            # Remove post-blast WIP orders (op > 1300) from the blast queue.
            # These are in the injection/cure/quench pipeline — cores are occupied.
            if self.wip_in_process_orders:
                wip_wo_numbers = {o['wo_number'] for o in self.wip_in_process_orders}
                before = len(self.orders)
                self.orders = [o for o in self.orders if o.get('wo_number') not in wip_wo_numbers]
                removed = before - len(self.orders)
                if removed > 0:
                    print(f"  Removed {removed} post-blast WIP orders from blast queue (cores occupied)")

            # Mark on-blaster orders (op == 1300) as priority 0.
            # These are physically on the blaster right now — cores are available.
            # They stay in the blast queue but sort before everything else.
            if self.on_blaster_orders:
                on_blaster_wos = {o['wo_number'] for o in self.on_blaster_orders}
                marked = 0
                for order in self.orders:
                    if order.get('wo_number') in on_blaster_wos:
                        order['priority'] = 'On Blaster'
                        marked += 1
                print(f"  Marked {marked} on-blaster orders as priority 0")

            # Stamp pre-blast delay hours based on current OSO operation.
            # Derived from Stators Process VSM standard cycle + setup times.
            # Represents remaining pipeline time until the part is blast-ready.
            PRE_BLAST_DELAY_BY_OP = {
                '900':  2.25,  # RECEIVE TUBE: 0.25 + 1.0 + 0.25 + 0.5 + 0.25
                '940':  38.0,  # COUNTERBORE: 1.0 + 0.25 + 0.5 + 0.25 + 36.0 queue at MoriSeiki 603 lathe
                '1220': 1.0,   # INDUCTION COIL: 0.25 + 0.5 + 0.25
                '1240': 0.75,  # STAMPING & INSPECTION: 0.5 + 0.25
                '1260': 0.25,  # TRANSFER TO SUPERMARKET
                '1280': 0.0,   # SUPERMARKET (ready to blast)
            }
            pre_blast_stamped = 0
            for order in self.orders:
                if order.get('is_rework'):
                    continue  # Rework has its own lead time
                op_num = str(order.get('oso_op_number') or '').strip()
                if op_num in PRE_BLAST_DELAY_BY_OP:
                    order['pre_blast_delay_hours'] = PRE_BLAST_DELAY_BY_OP[op_num]
                    pre_blast_stamped += 1
            if pre_blast_stamped > 0:
                print(f"  Stamped pre-blast delays on {pre_blast_stamped} orders")

            # 3c. Load Hot List for priority scheduling
            print("\n[3b/5] Loading Hot List...")
            self.load_hot_list()

            # 3c. Load DCP Report for supermarket locations (optional)
            print("\n[3c/6] Loading DCP Report...")
            self.load_dcp_report()

            # 4. Load Core Mapping
            print("\n[4/6] Loading Core Mapping...")
            core_mapping_file = self._find_most_recent_file("Core Mapping*.xlsx")
            if not core_mapping_file:
                core_mapping_file = self._find_most_recent_file("Core_Mapping*.xlsx")
            if not core_mapping_file:
                print("[ERROR] No Core Mapping file found!")
                return False
            print(f"  Loading: {core_mapping_file.name}")
            self.core_mapping = parse_core_mapping(str(core_mapping_file))
            self.core_inventory = parse_core_inventory(str(core_mapping_file))

            mapping_validation = validate_core_mapping(self.core_mapping, self.core_inventory)
            self.validation_results['core_mapping'] = mapping_validation

            print(f"[OK] Loaded {len(self.core_mapping)} part mappings")
            print(f"[OK] Loaded {len(self.core_inventory)} unique cores")

            # 5. Load Process Map
            print("\n[5/6] Loading Process Map...")
            process_map_file = self._find_most_recent_file("Stators Process VSM*.xlsx")
            if not process_map_file:
                process_map_file = self._find_most_recent_file("Stators_Process_VSM*.xlsx")
            if not process_map_file:
                print("[ERROR] No Process Map file found!")
                return False
            print(f"  Loading: {process_map_file.name}")
            self.operations = parse_process_map(str(process_map_file))

            print(f"[OK] Loaded {len(self.operations)} operations")

            # Cross-validate
            print("\nCross-validating data...")
            self._cross_validate()

            # Print exclusion summary
            self._print_exclusion_summary()

            return True

        except Exception as e:
            print(f"\n[ERROR] ERROR loading data: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

    def _cross_validate(self):
        """Cross-validate data between different files."""

        # Check if order part numbers exist in core mapping
        unmapped_parts = []
        for order in self.orders:
            part = order.get('part_number')
            if part and part not in self.core_mapping:
                unmapped_parts.append(part)

        unique_unmapped = list(set(unmapped_parts))

        if unique_unmapped:
            print(f"\n[WARN]  WARNING: {len(unique_unmapped)} part numbers in orders not found in core mapping")
            print(f"   Examples: {unique_unmapped[:5]}")

            # This is expected for some parts, just inform user
            self.validation_results['unmapped_parts'] = unique_unmapped
        else:
            print("\n[OK] All order part numbers found in core mapping")

    def _print_exclusion_summary(self):
        """Print summary of excluded orders."""
        if not self.excluded_orders:
            return

        print("\n" + "-" * 50)
        print("EXCLUSION SUMMARY")
        print("-" * 50)

        summary = get_exclusion_summary(self.excluded_orders)
        total_excluded = len(self.excluded_orders)

        print(f"Total excluded: {total_excluded}")
        for reason, count in sorted(summary.items(), key=lambda x: -x[1]):
            print(f"  - {reason}: {count}")

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of loaded data."""

        # Analyze orders by product type
        stator_count = sum(1 for o in self.orders if o.get('product_type') == 'Stator')
        reline_count = sum(1 for o in self.orders if o.get('product_type') == 'Reline')
        other_count = len(self.orders) - stator_count - reline_count

        # Analyze orders by source
        sales_order_count = sum(1 for o in self.orders if o.get('source') == 'Sales Order')
        shop_dispatch_count = sum(1 for o in self.orders if o.get('source') == 'Shop Dispatch')

        # Analyze cores
        total_cores = sum(len(cores) for cores in self.core_inventory.values())
        multi_core_numbers = sum(1 for cores in self.core_inventory.values() if len(cores) > 1)

        # Analyze operations
        sim_ops = [op for op, data in self.operations.items()
                  if data.get('include_in_simulation') == 'Yes']

        return {
            'orders': {
                'total': len(self.orders),
                'stator': stator_count,
                'reline': reline_count,
                'other': other_count,
                'from_sales_order': sales_order_count,
                'from_shop_dispatch': shop_dispatch_count,
                'excluded': len(self.excluded_orders),
                'reline_percentage': (reline_count / len(self.orders) * 100) if self.orders else 0
            },
            'parts': {
                'total_mapped': len(self.core_mapping),
                'unmapped_in_orders': len(self.validation_results.get('unmapped_parts', []))
            },
            'cores': {
                'unique_numbers': len(self.core_inventory),
                'total_physical_cores': total_cores,
                'numbers_with_multiple_units': multi_core_numbers
            },
            'operations': {
                'total': len(self.operations),
                'in_simulation': len(sim_ops)
            }
        }

    def print_summary(self):
        """Print a formatted summary."""
        summary = self.get_summary()

        print("\n" + "=" * 70)
        print("DATA LOADING SUMMARY")
        print("=" * 70)

        print(f"\n[ORDERS] ORDERS:")
        print(f"   Total: {summary['orders']['total']}")
        print(f"   Stators: {summary['orders']['stator']}")
        print(f"   Relines: {summary['orders']['reline']} ({summary['orders']['reline_percentage']:.1f}%)")
        print(f"   Other/Unknown: {summary['orders']['other']}")
        print(f"   From Sales Order: {summary['orders']['from_sales_order']}")
        print(f"   From Shop Dispatch: {summary['orders']['from_shop_dispatch']}")
        print(f"   Excluded: {summary['orders']['excluded']}")

        print(f"\n[PARTS] PARTS & CORES:")
        print(f"   Parts mapped: {summary['parts']['total_mapped']}")
        print(f"   Unmapped parts: {summary['parts']['unmapped_in_orders']}")
        print(f"   Unique core numbers: {summary['cores']['unique_numbers']}")
        print(f"   Total physical cores: {summary['cores']['total_physical_cores']}")
        print(f"   Core numbers with multiple units: {summary['cores']['numbers_with_multiple_units']}")

        print(f"\n[OPS]  OPERATIONS:")
        print(f"   Total operations: {summary['operations']['total']}")
        print(f"   In simulation: {summary['operations']['in_simulation']}")

        print("\n" + "=" * 70)


if __name__ == "__main__":
    import sys

    print("Testing Data Loader")
    print()

    loader = DataLoader()

    success = loader.load_all()

    if success:
        loader.print_summary()
        print("\n[OK] All data loaded successfully!")
        sys.exit(0)
    else:
        print("\n[ERROR] Data loading failed")
        sys.exit(1)
