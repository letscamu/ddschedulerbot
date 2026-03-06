"""
Shop Dispatch Parser
Parses the Shop Dispatch Excel file from SAP.
"""

import pandas as pd
from datetime import datetime
from typing import List, Dict, Any, Optional

from .order_filters import classify_product_type, should_exclude_order


def parse_shop_dispatch(filepath: str, sheet_name: str = 'Sheet1') -> tuple[List[Dict[str, Any]], List[tuple]]:
    """
    Parse the Shop Dispatch Excel file.

    Only includes orders with Operation < 1300 (pre-BLAST operations).
    Applies product type classification and exclusion filters.

    Args:
        filepath: Path to the Excel file
        sheet_name: Name of the sheet to read (default: 'Sheet1')

    Returns:
        Tuple of (list of order dictionaries, list of excluded orders with reasons)
    """
    try:
        # Read the Excel file
        df = pd.read_excel(filepath, sheet_name=sheet_name)

        print(f"Loaded {len(df)} rows from Shop Dispatch {sheet_name} sheet")
        print(f"Columns found: {list(df.columns)}")

        orders = []
        wip_in_process = []
        excluded = []
        errors = []
        skipped_operation = 0

        rework_count = 0

        for index, row in df.iterrows():
            try:
                # Extract work center info first for rework detection
                current_wc = str(row.get('Curr.WC', '')).strip().upper() if pd.notna(row.get('Curr.WC')) else ''
                remaining_wc = str(row.get('Remaining Work Centers', '')).strip().upper() if pd.notna(row.get('Remaining Work Centers')) else ''

                # Rework detection:
                # - If Curr.WC == "REMOV RB" -> is_rework=True, lead_time=36h
                # - If "REMOV RB" in Remaining Work Centers -> is_rework=True, lead_time=48h
                is_rework = False
                rework_lead_time_hours = 0

                if current_wc == 'REMOV RB':
                    is_rework = True
                    rework_lead_time_hours = 36  # Currently at rubber removal
                elif 'REMOV RB' in remaining_wc:
                    is_rework = True
                    rework_lead_time_hours = 48  # Will need to go through rubber removal

                # Get operation number and filter for < 1300 (pre-BLAST)
                # UNLESS it's a rework order - those should be included regardless of operation
                operation = row.get('Operation')
                op_num = 0
                if pd.notna(operation):
                    try:
                        op_num = int(operation)
                        # WIP in-process: already blasted — capture separately instead of discarding
                        if op_num >= 1300 and not is_rework:
                            skipped_operation += 1
                            wo_num = str(row.get('Order', '')).strip() if pd.notna(row.get('Order')) else None
                            pn = str(row.get('Material', '')).strip() if pd.notna(row.get('Material')) else None
                            if wo_num:
                                wip_order = {
                                    'wo_number': wo_num,
                                    'part_number': pn,
                                    'description': row.get('Description') if pd.notna(row.get('Description')) else None,
                                    'current_operation': op_num,
                                    'current_work_center': str(row.get('Curr.WC', '')).strip() if pd.notna(row.get('Curr.WC')) else None,
                                    'remaining_work_centers': str(row.get('Remaining Work Centers', '')).strip() if pd.notna(row.get('Remaining Work Centers')) else None,
                                    'days_idle': 0 if (pd.notna(row.get('Elapsed Days')) and row.get('Elapsed Days') == 9999)
                                                  else (int(row.get('Elapsed Days')) if pd.notna(row.get('Elapsed Days')) else None),
                                    'is_rework': False,
                                }
                                if pd.notna(row.get('Operation Start Date')):
                                    try:
                                        wip_order['operation_start_date'] = pd.to_datetime(row['Operation Start Date'])
                                    except Exception:
                                        pass
                                wip_in_process.append(wip_order)
                            continue
                    except (ValueError, TypeError):
                        pass

                # Extract fields
                wo_number = str(row.get('Order', '')).strip() if pd.notna(row.get('Order')) else None
                part_number = str(row.get('Material', '')).strip() if pd.notna(row.get('Material')) else None
                description = row.get('Description') if pd.notna(row.get('Description')) else None

                # Skip if missing essential data
                if not wo_number or not part_number:
                    errors.append(f"Row {index}: Missing Order# or Material")
                    continue

                # Check exclusion filters (no supply_source in Shop Dispatch)
                exclusion_reason = should_exclude_order(part_number, description, None)
                if exclusion_reason:
                    excluded.append(({
                        'wo_number': wo_number,
                        'part_number': part_number,
                        'description': description
                    }, exclusion_reason))
                    continue

                # Classify product type
                product_type = classify_product_type(part_number, description)

                # Create order dictionary
                order = {
                    'wo_number': wo_number,
                    'part_number': part_number,
                    'description': description,
                    'product_type': product_type,
                    'current_operation': operation,
                    'current_work_center': row.get('Curr.WC') if pd.notna(row.get('Curr.WC')) else None,
                    'remaining_work_centers': row.get('Remaining Work Centers') if pd.notna(row.get('Remaining Work Centers')) else None,
                    'operation_quantity': row.get('Operation Quantity') if pd.notna(row.get('Operation Quantity')) else None,
                    'priority': row.get('Priority') if pd.notna(row.get('Priority')) else None,
                    'days_idle': 0 if (pd.notna(row.get('Elapsed Days')) and row.get('Elapsed Days') == 9999)
                                  else (int(row.get('Elapsed Days')) if pd.notna(row.get('Elapsed Days')) else None),
                    'source': 'Shop Dispatch',
                    'is_rework': is_rework,
                    'rework_lead_time_hours': rework_lead_time_hours
                }

                # Parse operation start date if exists
                if pd.notna(row.get('Operation Start Date')):
                    try:
                        order['operation_start_date'] = pd.to_datetime(row['Operation Start Date'])
                    except:
                        pass

                if is_rework:
                    rework_count += 1

                orders.append(order)

            except Exception as e:
                errors.append(f"Row {index}: Error parsing - {str(e)}")
                continue

        # Print summary
        print(f"\nShop Dispatch Parsing complete:")
        print(f"  - WIP in-process (op >= 1300): {len(wip_in_process)} orders")
        print(f"  - Excluded by filters: {len(excluded)}")
        print(f"  - Successfully parsed: {len(orders)} orders")
        print(f"  - Rework orders detected: {rework_count}")
        print(f"  - Errors: {len(errors)}")

        if errors and len(errors) <= 10:
            print("\nErrors encountered:")
            for error in errors[:10]:
                print(f"  - {error}")

        return orders, wip_in_process, excluded

    except Exception as e:
        print(f"Error reading Shop Dispatch file: {str(e)}")
        raise


if __name__ == "__main__":
    import sys

    # Test the parser
    test_file = "../../Scheduler Bot Info/Shop Dispatch 02012026 0844.XLSX"

    print("Testing Shop Dispatch Parser")
    print("=" * 60)

    try:
        orders, excluded = parse_shop_dispatch(test_file)

        # Show exclusion summary
        from .order_filters import get_exclusion_summary
        exclusion_summary = get_exclusion_summary(excluded)
        print("\nExclusion Summary:")
        for reason, count in sorted(exclusion_summary.items(), key=lambda x: -x[1]):
            print(f"  - {reason}: {count}")

        # Show product type breakdown
        stator_count = sum(1 for o in orders if o.get('product_type') == 'Stator')
        reline_count = sum(1 for o in orders if o.get('product_type') == 'Reline')
        other_count = len(orders) - stator_count - reline_count

        print(f"\nProduct Type Breakdown:")
        print(f"  - Stator: {stator_count}")
        print(f"  - Reline: {reline_count}")
        print(f"  - Other/Unknown: {other_count}")

        # Show sample orders
        print("\nSample orders (first 3):")
        for i, order in enumerate(orders[:3]):
            print(f"\nOrder {i+1}:")
            for key, value in order.items():
                print(f"  {key}: {value}")

    except Exception as e:
        print(f"\nError: {str(e)}")
        sys.exit(1)
