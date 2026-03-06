"""
Sales Order Parser
Parses the Open Sales Order Excel file from SAP.
"""

import pandas as pd
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
import re

from .order_filters import classify_product_type, should_exclude_order


def extract_part_number_from_description(description: str) -> Optional[str]:
    """
    Extract part number from ITEM DESC field.
    Part numbers typically appear at the beginning of the description.
    Examples:
    - "S700788.5-HR-0.5OS-DISCUT-RELINE"
    - "S675783.0-SLOW-NBR-HR-1OS-RELINE"
    """
    if pd.isna(description):
        return None

    # Try to extract part number pattern (starts with S or XN followed by numbers/letters)
    match = re.match(r'^(S\d+[\d\.]*[A-Za-z0-9\-]*|XN\d+[A-Za-z0-9\-]*)', str(description))
    if match:
        return match.group(1)

    # If no match, return the first word
    parts = str(description).split()
    return parts[0] if parts else None


def parse_open_sales_order(filepath: str, sheet_name: str = 'OSO') -> List[Dict[str, Any]]:
    """
    Parse the Open Sales Order Excel file.

    Args:
        filepath: Path to the Excel file
        sheet_name: Name of the sheet to read (default: 'OSO')

    Returns:
        List of order dictionaries
    """
    try:
        # Read the Excel file
        df = pd.read_excel(filepath, sheet_name=sheet_name)

        print(f"Loaded {len(df)} rows from {sheet_name} sheet")
        print(f"Columns found: {list(df.columns)}")

        orders = []
        errors = []

        for index, row in df.iterrows():
            try:
                # Get part number from Material column, or extract from description
                part_number = row.get('Material')
                if pd.isna(part_number):
                    part_number = extract_part_number_from_description(row.get('Material Description'))
                else:
                    part_number = str(part_number)

                # Get description and supply source
                description = row.get('Material Description')
                supply_source = row.get('Supply Source') if pd.notna(row.get('Supply Source')) else None

                # Normalize WO number (remove .0 suffix from float conversion)
                wo_number = None
                if pd.notna(row.get('Work Order')):
                    wo_raw = row['Work Order']
                    if isinstance(wo_raw, float):
                        wo_number = str(int(wo_raw))
                    else:
                        wo_number = str(wo_raw).replace('.0', '')

                # Create order dictionary using actual column names from SAP export
                order = {
                    'wo_number': wo_number,
                    'part_number': part_number,
                    'description': description,
                    'supply_source': supply_source,
                    'product_type': classify_product_type(part_number, description),
                    'customer': row.get('Customer Name'),
                    'customer_number': row.get('Customer Number'),
                    'core_number': row.get('Core (Work Center)'),
                    'serial_number': row.get('Serial Number'),
                    'quantity': row.get('Ordered Quantity', 1),
                    'work_order_status': row.get('Work Order Status'),
                    'oso_op_number': str(int(float(row.get('Operation Number')))) if pd.notna(row.get('Operation Number')) else None,
                    'oso_op_description': row.get('Current Operation Description') if pd.notna(row.get('Current Operation Description')) else None,
                    'source': 'Sales Order'
                }

                # Parse dates if they exist
                if pd.notna(row.get('Created On')):
                    order['created_on'] = pd.to_datetime(row['Created On'])
                if pd.notna(row.get('Work Order Creation Date')):
                    order['wo_creation_date'] = pd.to_datetime(row['Work Order Creation Date'])

                # Set creation_date for scheduler (prefer WO Creation Date, fallback to Created On)
                order['creation_date'] = order.get('wo_creation_date') or order.get('created_on')
                if pd.notna(row.get('Promise Date')):
                    order['promise_date'] = pd.to_datetime(row['Promise Date'])
                if pd.notna(row.get('Basic Start Date')):
                    order['basic_start_date'] = pd.to_datetime(row['Basic Start Date'])
                if pd.notna(row.get('Scheduled start')):
                    order['scheduled_start'] = pd.to_datetime(row['Scheduled start'])
                if pd.notna(row.get('Requested deliv.date')):
                    order['requested_delivery_date'] = pd.to_datetime(row['Requested deliv.date'])
                if pd.notna(row.get('Basic finish date')):
                    order['basic_finish_date'] = pd.to_datetime(row['Basic finish date'])

                # Skip orders without essential data
                if not order['wo_number'] or not order['part_number']:
                    errors.append(f"Row {index}: Missing WO# or Part Number")
                    continue

                # Rework detection: check for rubber removal operations
                # If operation >= 1300 and current operation contains "RUBBER REMOVAL"
                is_rework = False
                rework_lead_time_hours = 0
                current_op = order.get('oso_op_description')
                if current_op and pd.notna(current_op):
                    current_op_upper = str(current_op).upper()
                    if 'RUBBER REMOVAL' in current_op_upper or 'REMOV RB' in current_op_upper:
                        is_rework = True
                        rework_lead_time_hours = 36  # 36 working hours for rework

                order['is_rework'] = is_rework
                order['rework_lead_time_hours'] = rework_lead_time_hours

                orders.append(order)

            except Exception as e:
                errors.append(f"Row {index}: Error parsing - {str(e)}")
                continue

        # Print summary
        print(f"\nParsing complete:")
        print(f"  - Successfully parsed: {len(orders)} orders")
        print(f"  - Errors: {len(errors)}")

        if errors:
            print("\nErrors encountered:")
            for error in errors[:10]:  # Show first 10 errors
                print(f"  - {error}")

        return orders

    except Exception as e:
        print(f"Error reading Excel file: {str(e)}")
        raise


def validate_orders(orders: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Validate parsed orders for completeness and correctness.

    Note: Missing WO# and part_number checks are handled during parsing
    (rows without these fields are skipped), so we don't re-check here
    to avoid duplicate error reports.

    Returns:
        Dictionary with validation results
    """
    validation = {
        'is_valid': True,
        'errors': [],
        'warnings': []
    }

    # Check for duplicate WO numbers
    wo_numbers = [o['wo_number'] for o in orders]
    duplicates = [wo for wo in set(wo_numbers) if wo_numbers.count(wo) > 1]
    if duplicates:
        validation['warnings'].append(f"Duplicate WO numbers found: {duplicates[:5]}")

    # Check part number format
    new_count = sum(1 for o in orders if o.get('part_number') and o['part_number'][0].isdigit())
    reline_count = sum(1 for o in orders if o.get('part_number') and o['part_number'].startswith('XN'))
    other_count = len(orders) - new_count - reline_count

    print(f"\nOrder breakdown:")
    print(f"  - New stators (starts with digit): {new_count}")
    print(f"  - Reline stators (starts with XN): {reline_count}")
    print(f"  - Other/Unknown: {other_count}")

    if other_count > 0:
        validation['warnings'].append(f"{other_count} orders have unexpected part number format")

    return validation


if __name__ == "__main__":
    # Test the parser with your actual file
    import sys

    # Adjust the path to your actual file location
    test_file = "../../Scheduler Bot Info/Open_Sales_Order_Example.xlsx"

    print("Testing Open Sales Order Parser")
    print("=" * 60)

    try:
        orders = parse_open_sales_order(test_file, sheet_name='OSO')

        # Validate
        validation = validate_orders(orders)

        print("\nValidation Results:")
        print(f"  Valid: {validation['is_valid']}")
        if validation['errors']:
            print(f"  Errors: {len(validation['errors'])}")
            for error in validation['errors'][:5]:
                print(f"    - {error}")
        if validation['warnings']:
            print(f"  Warnings: {len(validation['warnings'])}")
            for warning in validation['warnings'][:5]:
                print(f"    - {warning}")

        # Show sample orders
        print("\nSample orders (first 3):")
        for i, order in enumerate(orders[:3]):
            print(f"\nOrder {i+1}:")
            for key, value in order.items():
                print(f"  {key}: {value}")

    except Exception as e:
        print(f"\nError: {str(e)}")
        sys.exit(1)
