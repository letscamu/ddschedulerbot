"""
Production Scheduler
Core scheduling algorithm for stator production.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
import copy
import pandas as pd


@dataclass
class WorkSchedule:
    """Work schedule configuration."""
    days_per_week: int = 5  # 4, 5, or 6
    shift_length: float = 10  # 10 or 12 hours
    num_shifts: int = 2  # 1 or 2
    shift1_start: int = 5  # 5 AM
    shift2_start: int = 17  # 5 PM (17:00)
    holidays: List[datetime] = field(default_factory=list)

    def get_working_days(self) -> List[int]:
        """Return list of working weekdays (0=Monday, 6=Sunday)."""
        if self.days_per_week == 4:
            return [0, 1, 2, 3]  # Mon-Thu
        elif self.days_per_week == 5:
            return [0, 1, 2, 3, 4]  # Mon-Fri
        else:  # 6 days
            return [0, 1, 2, 3, 4, 5]  # Mon-Sat

    def _is_holiday(self, date) -> bool:
        """Check if a date is a holiday."""
        return date in [h.date() for h in self.holidays]

    def _get_shift_info(self, dt: datetime) -> Optional[Tuple[datetime, datetime, int]]:
        """
        Get shift info for a datetime.
        Returns (shift_start, shift_end, shift_number) or None if not in a shift.

        Handles overnight shifts properly by checking if we're in the
        continuation of yesterday's shift 2.
        """
        hour = dt.hour + dt.minute / 60.0
        date = dt.date()

        shift1_end = self.shift1_start + self.shift_length
        shift2_end_hour = self.shift2_start + self.shift_length  # May be > 24

        # Check if we're in shift 1 (same day)
        if self.shift1_start <= hour < shift1_end:
            if date.weekday() in self.get_working_days() and not self._is_holiday(date):
                shift_start = dt.replace(hour=self.shift1_start, minute=0, second=0, microsecond=0)
                shift_end = dt.replace(hour=int(shift1_end), minute=int((shift1_end % 1) * 60), second=0, microsecond=0)
                return (shift_start, shift_end, 1)

        if self.num_shifts == 1:
            return None

        # Check if we're in shift 2 (same day, before midnight)
        if self.shift2_start <= hour < 24:
            if date.weekday() in self.get_working_days() and not self._is_holiday(date):
                shift_start = dt.replace(hour=self.shift2_start, minute=0, second=0, microsecond=0)
                if shift2_end_hour >= 24:
                    # Shift ends after midnight
                    shift_end = (dt + timedelta(days=1)).replace(
                        hour=int(shift2_end_hour - 24),
                        minute=int(((shift2_end_hour - 24) % 1) * 60),
                        second=0, microsecond=0
                    )
                else:
                    shift_end = dt.replace(hour=int(shift2_end_hour), minute=0, second=0, microsecond=0)
                return (shift_start, shift_end, 2)

        # Check if we're in overnight portion of shift 2 (after midnight, from previous day's shift)
        if shift2_end_hour > 24:
            overnight_end = shift2_end_hour - 24
            if 0 <= hour < overnight_end:
                # Check if YESTERDAY was a working day
                yesterday = date - timedelta(days=1)
                if yesterday.weekday() in self.get_working_days() and not self._is_holiday(yesterday):
                    shift_start = (dt - timedelta(days=1)).replace(
                        hour=self.shift2_start, minute=0, second=0, microsecond=0
                    )
                    shift_end = dt.replace(
                        hour=int(overnight_end),
                        minute=int((overnight_end % 1) * 60),
                        second=0, microsecond=0
                    )
                    return (shift_start, shift_end, 2)

        return None

    def is_working_time(self, dt: datetime) -> bool:
        """Check if datetime is during working hours."""
        return self._get_shift_info(dt) is not None

    def next_working_time(self, dt: datetime) -> datetime:
        """Find the next working time from given datetime."""
        # If already in working time, return as-is
        if self.is_working_time(dt):
            return dt

        current = dt
        max_days = 30

        for _ in range(max_days):
            date = current.date()

            # Skip holidays
            if self._is_holiday(date):
                current = (current + timedelta(days=1)).replace(
                    hour=self.shift1_start, minute=0, second=0, microsecond=0
                )
                continue

            # Skip non-working days
            if date.weekday() not in self.get_working_days():
                current = (current + timedelta(days=1)).replace(
                    hour=self.shift1_start, minute=0, second=0, microsecond=0
                )
                continue

            hour = current.hour + current.minute / 60.0
            shift1_end = self.shift1_start + self.shift_length

            # Before shift 1 starts
            if hour < self.shift1_start:
                return current.replace(hour=self.shift1_start, minute=0, second=0, microsecond=0)

            # During shift 1
            if hour < shift1_end:
                return current

            # Between shifts (gap)
            if self.num_shifts == 2 and hour < self.shift2_start:
                return current.replace(hour=self.shift2_start, minute=0, second=0, microsecond=0)

            # During shift 2
            if self.num_shifts == 2 and hour < 24:
                return current

            # After all shifts, go to next day
            current = (current + timedelta(days=1)).replace(
                hour=self.shift1_start, minute=0, second=0, microsecond=0
            )

        return current  # Fallback

    def get_shift_end(self, dt: datetime) -> datetime:
        """Get the end time of the current shift."""
        shift_info = self._get_shift_info(dt)
        if shift_info:
            return shift_info[1]
        # Not in a shift, find next shift and return its end
        next_start = self.next_working_time(dt)
        shift_info = self._get_shift_info(next_start)
        if shift_info:
            return shift_info[1]
        # Fallback
        return dt + timedelta(hours=self.shift_length)

    def advance_time(self, start: datetime, hours: float) -> datetime:
        """
        Advance time by hours, only counting working time.
        Returns the end datetime.
        """
        if hours <= 0:
            return start

        current = self.next_working_time(start)
        remaining_minutes = hours * 60  # Work in minutes for precision

        while remaining_minutes > 0.01:  # Small epsilon for floating point
            if not self.is_working_time(current):
                current = self.next_working_time(current)
                continue

            # Get end of current shift
            shift_end = self.get_shift_end(current)

            # Calculate minutes until shift end
            minutes_to_shift_end = (shift_end - current).total_seconds() / 60.0

            if minutes_to_shift_end >= remaining_minutes:
                # Can finish in this shift
                current += timedelta(minutes=remaining_minutes)
                remaining_minutes = 0
            else:
                # Use rest of shift and continue to next
                remaining_minutes -= minutes_to_shift_end
                current = shift_end
                current = self.next_working_time(current)

        return current


@dataclass
class ScheduledOperation:
    """A scheduled operation for an order."""
    operation_name: str
    start_time: datetime
    end_time: datetime
    resource_id: str = None
    cycle_time: float = 0
    setup_time: float = 0


@dataclass
class ScheduledOrder:
    """A fully scheduled order."""
    wo_number: str
    part_number: str
    description: str
    customer: str
    is_reline: bool
    serial_number: str = None  # MVP 1.1: From Open Sales Order
    assigned_core: str = None  # e.g., "427-A"
    rubber_type: str = None
    operations: List[ScheduledOperation] = field(default_factory=list)
    blast_date: datetime = None
    completion_date: datetime = None
    turnaround_days: float = None
    basic_finish_date: datetime = None  # From SAP - used for On-Time calculation
    promise_date: datetime = None
    on_time: bool = True
    creation_date: datetime = None
    planned_desma: str = None  # Which Desma machine is assigned
    priority: str = 'Normal'  # Hot-ASAP, Hot-Dated, Rework, Normal, CAVO
    serial_number: str = None  # From Sales Order report
    special_instructions: str = None  # From redline requests
    supermarket_location: str = None  # From DCP report
    days_idle: int = None  # From Shop Dispatch "Elapsed Days" (9999→0)
    oso_op_number: str = None  # From OSO "Operation Number" column
    oso_op_description: str = None  # From OSO "Current Operation Description" column


@dataclass
class Resource:
    """A production resource (machine, station, etc.)."""
    resource_id: str
    resource_type: str  # e.g., "injection_machine", "blast", etc.
    capacity: int = 1
    schedule: List[Tuple[datetime, datetime, str]] = field(default_factory=list)  # (start, end, wo_number)
    current_rubber: str = None  # For injection machines

    def next_available_time(self, after: datetime, takt_time: float = None) -> datetime:
        """
        Find next available time slot after given datetime.

        If takt_time is provided, use it instead of waiting for full operation to complete.
        This allows starting new parts at regular intervals.

        Args:
            after: The earliest time we're looking for availability
            takt_time: Hours between part starts (e.g., 0.33 = 20 minutes)
        """
        if not self.schedule:
            return after

        if takt_time is not None and takt_time > 0:
            # Use takt time: find the last START time and add takt
            last_start = max(start for start, end, _ in self.schedule)
            takt_available = last_start + timedelta(hours=takt_time)
            return max(after, takt_available)
        else:
            # Use full cycle time: wait for last operation to END
            latest_end = after
            for start, end, _ in self.schedule:
                if end > latest_end:
                    latest_end = end
            return max(after, latest_end)

    def book(self, start: datetime, end: datetime, wo_number: str):
        """Book this resource for the given time period."""
        self.schedule.append((start, end, wo_number))
        self.schedule.sort(key=lambda x: x[0])


class ProductionScheduler:
    """Main production scheduler."""

    # Takt times (hours) - how often a new part can START an operation
    # None means use actual cycle time (for bottleneck operations)
    # This controls resource availability, not operation duration
    TAKT_TIMES = {
        'BLAST': 0.33,           # 20 minutes
        'TUBE PREP': 0.33,       # 20 minutes
        'CORE OVEN': 0.33,       # 20 minutes (loading rate)
        'ASSEMBLY': 0.33,        # 20 minutes
        'INJECTION': None,       # Use actual cycle time (bottleneck)
        'CURE': None,            # Use concurrent capacity
        'QUENCH': None,          # Use concurrent capacity
        'DISASSEMBLY': 0.5,      # 30 minutes
        'BLD END CUTBACK': 0.25, # 15 minutes
        'INJ END CUTBACK': 0.25, # 15 minutes
        'CUT THREADS': 0.33,     # 20 minutes
    }

    def __init__(self, orders: List[Dict], core_mapping: Dict,
                 core_inventory: Dict, operations: Dict,
                 work_schedule: WorkSchedule = None):
        self.orders = orders
        self.core_mapping = core_mapping
        self.core_inventory = self._init_core_inventory(core_inventory)
        self.operations = operations
        self.work_schedule = work_schedule or WorkSchedule()

        # Initialize resources
        self.resources = self._init_resources()

        # Results
        self.scheduled_orders: List[ScheduledOrder] = []
        self.unscheduled_orders: List[Dict] = []
        self.pending_core_orders: List[Dict] = []  # Orders with no core in inventory
        self.core_shortages: List[Dict] = []

    def _get_takt_time(self, op_name: str, cycle_time: float) -> float:
        """
        Get the takt time for an operation.

        Takt time determines when a resource can accept the NEXT part.
        This is different from cycle time (how long the operation takes).

        Returns takt time in hours.
        """
        takt = self.TAKT_TIMES.get(op_name)

        if takt is not None:
            return takt

        # For operations without defined takt time, use cycle time
        # This applies to bottleneck operations like INJECTION
        return cycle_time

    def _init_core_inventory(self, inventory: Dict) -> Dict:
        """
        Initialize core inventory with simple datetime tracking.

        Each core tracks:
        - available_at: None means available now, datetime means when it becomes free
        - assigned_to: WO number currently using the core, or None
        """
        result = {}
        for core_num, cores in inventory.items():
            result[core_num] = []
            for core in cores:
                result[core_num].append({
                    **core,
                    'available_at': None,  # None = available now
                    'assigned_to': None
                })
        return result

    def _init_resources(self) -> Dict[str, List[Resource]]:
        """Initialize production resources from operations."""
        resources = {}

        for op_name, op_data in self.operations.items():
            machines = op_data.get('machines_available', 1)
            capacity = op_data.get('concurrent_capacity', 1)

            resources[op_name] = []
            for i in range(machines):
                resource = Resource(
                    resource_id=f"{op_name}_{i+1}",
                    resource_type=op_name,
                    capacity=capacity
                )
                resources[op_name].append(resource)

        return resources

    def _get_part_data(self, part_number: str) -> Optional[Dict]:
        """Get core mapping data for a part number."""
        return self.core_mapping.get(part_number)

    def _calculate_core_return_time(self, blast_start: datetime, part_data: Dict) -> datetime:
        """
        Calculate when a core returns after full lifecycle.

        Core lifecycle from BLAST start:
        - OVEN (2.5h) - already started before BLAST
        - ASSEMBLY (takt time ~20 min)
        - INJECTION (variable)
        - CURE (variable)
        - QUENCH (variable)
        - DISASSEMBLY (takt time ~30 min)
        - CLEANING (45 min)

        Args:
            blast_start: When BLAST operation starts
            part_data: Part-specific timing data

        Returns:
            Datetime when core becomes available again
        """
        # Get variable times from part data
        injection_time = part_data.get('injection_time', 0.5) if part_data else 0.5
        cure_time = part_data.get('cure_time', 1.5) if part_data else 1.5
        quench_time = part_data.get('quench_time', 0.75) if part_data else 0.75

        # Fixed times (in hours)
        oven_time = 2.5
        assembly_takt = 0.33  # 20 minutes
        disassembly_takt = 0.5  # 30 minutes
        cleaning_time = 0.75  # 45 minutes

        # Total time from blast start until core is available again
        # Note: OVEN happens before BLAST, so we start counting from blast
        total_hours = (
            assembly_takt +      # Assembly after BLAST/TUBE PREP
            injection_time +     # Injection
            cure_time +          # Cure
            quench_time +        # Quench
            disassembly_takt +   # Disassembly
            cleaning_time        # Cleaning
        )

        # Use work schedule to advance time properly
        return self.work_schedule.advance_time(blast_start, total_hours)

    def _find_core_available_at(self, core_number: int, needed_at: datetime) -> Optional[Dict]:
        """
        Find a core that is available by the needed time.

        Args:
            core_number: The core number needed
            needed_at: When the core is needed (typically BLAST start)

        Returns:
            Core dict if one is available, None otherwise
        """
        if core_number not in self.core_inventory:
            return None

        for core in self.core_inventory[core_number]:
            # available_at is None means available now
            if core['available_at'] is None:
                return core
            # Or available_at is before/at needed time
            if core['available_at'] <= needed_at:
                return core

        return None

    def _get_earliest_core_availability(self, core_number: int) -> Optional[datetime]:
        """
        Get the earliest time any core of this number becomes available.

        Args:
            core_number: The core number to check

        Returns:
            Earliest availability datetime, or None if core doesn't exist in inventory
        """
        if core_number not in self.core_inventory:
            return None

        earliest = None
        for core in self.core_inventory[core_number]:
            avail = core['available_at']
            if avail is None:
                # Available now - return immediately
                return None  # None means available now
            if earliest is None or avail < earliest:
                earliest = avail

        return earliest

    def _find_available_core(self, core_number: int,
                             needed_at: datetime) -> Optional[Dict]:
        """
        Find an available core with the given number.

        Args:
            core_number: The core number needed
            needed_at: When the core is needed

        Returns:
            Core dict if available, None otherwise
        """
        if core_number not in self.core_inventory:
            return None

        for core in self.core_inventory[core_number]:
            # available_at is None means available now
            if core['available_at'] is None:
                return core
            # Or available before/at needed time
            if core['available_at'] <= needed_at:
                return core

        return None

    def _assign_core(self, core_number: int, suffix: str,
                     wo_number: str, blast_start: datetime,
                     part_data: Dict) -> bool:
        """
        Assign a core to an order and calculate when it becomes available again.

        Args:
            core_number: The core number to assign
            suffix: The core suffix (e.g., 'A', 'B')
            wo_number: Work order being assigned
            blast_start: When BLAST operation starts
            part_data: Part-specific timing data

        Returns:
            True if assignment successful, False otherwise
        """
        if core_number not in self.core_inventory:
            return False

        for core in self.core_inventory[core_number]:
            if core['suffix'] == suffix:
                # Calculate when this core will be available again
                core['available_at'] = self._calculate_core_return_time(blast_start, part_data)
                core['assigned_to'] = wo_number
                return True

        return False

    def _get_routing(self, is_reline: bool) -> List[str]:
        """Get operation sequence for product type."""
        routing = []
        flag_field = 'reline_stator' if is_reline else 'new_stator'

        for op_name, op_data in self.operations.items():
            if op_data.get(flag_field) == 'Yes':
                routing.append(op_name)

        return routing

    def _get_cycle_time(self, op_name: str, part_data: Dict) -> float:
        """Get cycle time for an operation."""
        op = self.operations.get(op_name, {})
        cycle_time = op.get('cycle_time', 0)

        # Handle variable times
        if cycle_time == 'VARIABLE' or op_name in ['INJECTION', 'CURE', 'QUENCH']:
            if op_name == 'INJECTION':
                return part_data.get('injection_time', 0.5) if part_data else 0.5
            elif op_name == 'CURE':
                return part_data.get('cure_time', 1.5) if part_data else 1.5
            elif op_name == 'QUENCH':
                return part_data.get('quench_time', 0.75) if part_data else 0.75
            else:
                return 0.5  # Default

        return float(cycle_time) if cycle_time else 0

    def _find_resource(self, op_name: str, after: datetime) -> Tuple[Resource, datetime]:
        """Find the next available resource for an operation."""
        if op_name not in self.resources:
            return Resource(resource_id=f"{op_name}_1", resource_type=op_name), after

        resources = self.resources[op_name]

        # Get takt time for this operation (if defined)
        takt_time = self.TAKT_TIMES.get(op_name)

        # Find resource with earliest availability
        best_resource = None
        best_time = None

        for resource in resources:
            avail_time = resource.next_available_time(after, takt_time)
            avail_time = self.work_schedule.next_working_time(avail_time)

            if best_time is None or avail_time < best_time:
                best_time = avail_time
                best_resource = resource

        return best_resource, best_time

    def schedule_orders(self, start_date: datetime = None,
                        hot_list: List[str] = None) -> List[ScheduledOrder]:
        """
        Schedule all orders using core-aware FIFO algorithm.

        Algorithm:
        1. Separate orders into schedulable (core exists in inventory) vs pending (no core)
        2. Sort by FIFO (Created On date), hot list first
        3. Iterate through time slots (takt time intervals)
        4. For each slot, find first order whose core is available
        5. Schedule it, update core availability, remove from queue
        6. Continue until all schedulable orders done

        Args:
            start_date: Start date for scheduling (default: today)
            hot_list: List of WO numbers to prioritize

        Returns:
            List of scheduled orders
        """
        start_date = start_date or datetime.now().replace(
            hour=self.work_schedule.shift1_start, minute=0, second=0, microsecond=0
        )

        print(f"\n{'='*70}")
        print(f"CORE-AWARE SCHEDULING: {len(self.orders)} ORDERS")
        print(f"Start date: {start_date}")
        print(f"{'='*70}")

        # Sort orders: hot list first, then by creation date (FIFO)
        sorted_orders = self._sort_orders(hot_list)

        # Separate orders: schedulable (core in inventory) vs pending (no core)
        schedulable_orders = []
        for order in sorted_orders:
            part_number = order.get('part_number')
            part_data = self._get_part_data(part_number)

            # Get core number for this part
            core_number = None
            if part_data:
                core_num = part_data.get('core_number')
                if core_num:
                    try:
                        core_number = int(float(core_num))
                    except:
                        pass

            # Check if core exists in inventory
            if core_number is None:
                # No core mapping - add to pending
                self.pending_core_orders.append({
                    **order,
                    'reason': 'No core mapping for part number',
                    'core_number_needed': None
                })
            elif core_number not in self.core_inventory:
                # Core doesn't exist in inventory
                self.pending_core_orders.append({
                    **order,
                    'reason': f'Core {core_number} not in inventory',
                    'core_number_needed': core_number
                })
            else:
                # Core exists - order can be scheduled
                schedulable_orders.append({
                    'order': order,
                    'core_number': core_number,
                    'part_data': part_data
                })

        print(f"   Schedulable orders: {len(schedulable_orders)}")
        print(f"   Pending core orders: {len(self.pending_core_orders)}")

        # Helper function to get Created On date for sorting
        def get_created_on(o):
            order = o['order']
            created_on = order.get('created_on')
            if created_on and hasattr(created_on, 'timestamp'):
                return created_on.timestamp()
            wo_creation = order.get('wo_creation_date')
            if wo_creation and hasattr(wo_creation, 'timestamp'):
                return wo_creation.timestamp()
            return float('inf')

        # Apply hot list priority and deprioritize CAVO orders
        hot_list = hot_list or []
        hot_orders = []
        normal_orders = []
        cavo_orders = []  # Lowest priority - inventory/no firm demand

        for o in schedulable_orders:
            wo_number = o['order'].get('wo_number')
            customer = o['order'].get('customer', '') or ''

            if wo_number in hot_list:
                hot_orders.append(o)
            elif 'CAVO DRILLING MOTORS' in customer.upper():
                cavo_orders.append(o)
            else:
                normal_orders.append(o)

        hot_orders.sort(key=get_created_on)
        normal_orders.sort(key=get_created_on)
        cavo_orders.sort(key=get_created_on)

        # Combined queue: hot list first, then normal FIFO, then CAVO last
        order_queue = hot_orders + normal_orders + cavo_orders

        print(f"   Priority breakdown: {len(hot_orders)} hot, {len(normal_orders)} normal, {len(cavo_orders)} CAVO (low priority)")

        # Track current time slot
        current_slot = start_date
        takt_interval = timedelta(minutes=20)  # 20-minute intervals

        # Process schedulable orders
        remaining_orders = order_queue.copy()
        max_iterations = len(remaining_orders) * 100  # Safety limit
        iteration = 0

        while remaining_orders and iteration < max_iterations:
            iteration += 1
            scheduled_this_slot = False

            # Try to find an order whose core is available at current_slot
            for i, order_info in enumerate(remaining_orders):
                order = order_info['order']
                core_number = order_info['core_number']
                part_data = order_info['part_data']

                # Find a core available at this time
                core = self._find_core_available_at(core_number, current_slot)

                if core:
                    # Schedule this order
                    try:
                        scheduled = self._schedule_single_order_with_core(
                            order=order,
                            start_time=current_slot,
                            core_number=core_number,
                            core_suffix=core['suffix'],
                            part_data=part_data
                        )

                        if scheduled:
                            self.scheduled_orders.append(scheduled)
                            remaining_orders.pop(i)
                            scheduled_this_slot = True
                            break
                        else:
                            self.unscheduled_orders.append(order)
                            remaining_orders.pop(i)
                            break
                    except Exception as e:
                        print(f"Error scheduling {order.get('wo_number')}: {e}")
                        self.unscheduled_orders.append(order)
                        remaining_orders.pop(i)
                        break

            # If we scheduled something, advance to next slot
            # If nothing could be scheduled, also advance (cores may become available later)
            if scheduled_this_slot:
                current_slot = self.work_schedule.advance_time(current_slot, takt_interval.total_seconds() / 3600)
            else:
                # No order could be scheduled in this slot
                # Find the earliest time any remaining order's core becomes available
                earliest_availability = None
                for order_info in remaining_orders:
                    core_number = order_info['core_number']
                    avail = self._get_earliest_core_availability(core_number)
                    if avail is None:
                        # Core is available now - try next iteration
                        earliest_availability = current_slot
                        break
                    if earliest_availability is None or avail < earliest_availability:
                        earliest_availability = avail

                if earliest_availability is None:
                    # No cores will ever be available - shouldn't happen
                    break

                # Jump to earliest availability (or at least advance one slot)
                next_slot = max(
                    self.work_schedule.advance_time(current_slot, takt_interval.total_seconds() / 3600),
                    earliest_availability
                )
                current_slot = self.work_schedule.next_working_time(next_slot)

        # Any remaining orders couldn't be scheduled
        for order_info in remaining_orders:
            self.unscheduled_orders.append(order_info['order'])

        print(f"\n[OK] Scheduled: {len(self.scheduled_orders)} orders")
        print(f"[!!] Pending core: {len(self.pending_core_orders)} orders")
        print(f"[!!] Unscheduled: {len(self.unscheduled_orders)} orders")

        return self.scheduled_orders

    def _sort_orders(self, hot_list: List[str] = None) -> List[Dict]:
        """Sort orders by priority (hot list first, then FIFO by Created On date)."""
        hot_list = hot_list or []

        hot_orders = []
        normal_orders = []

        for order in self.orders:
            if order.get('wo_number') in hot_list:
                hot_orders.append(order)
            else:
                normal_orders.append(order)

        # Sort by "Created On" date (FIFO - oldest first)
        def get_sort_key(o):
            # Primary: Created On date from sales order
            created_on = o.get('created_on')
            if created_on and hasattr(created_on, 'timestamp'):
                return created_on.timestamp()

            # Fallback: Work Order Creation Date
            wo_creation = o.get('wo_creation_date')
            if wo_creation and hasattr(wo_creation, 'timestamp'):
                return wo_creation.timestamp()

            # Last resort: return max timestamp so unknowns go to end
            return float('inf')

        hot_orders.sort(key=get_sort_key)
        normal_orders.sort(key=get_sort_key)

        return hot_orders + normal_orders

    def _schedule_single_order_with_core(self, order: Dict, start_time: datetime,
                                         core_number: int, core_suffix: str,
                                         part_data: Dict) -> Optional[ScheduledOrder]:
        """
        Schedule a single order with a pre-assigned core.

        This method schedules operations and assigns the core in one atomic operation.

        Args:
            order: The order dict
            start_time: When to start scheduling (BLAST time slot)
            core_number: The core number to use
            core_suffix: The core suffix (e.g., 'A', 'B')
            part_data: Part-specific data from core mapping

        Returns:
            ScheduledOrder if successful, None otherwise
        """
        wo_number = order.get('wo_number')
        part_number = order.get('part_number')

        if not wo_number or not part_number:
            return None

        # Determine if reline
        is_reline = part_number.startswith('XN')

        # Get routing
        routing = self._get_routing(is_reline)

        # Schedule each operation
        scheduled_ops = []
        current_time = start_time
        blast_date = None

        for op_name in routing:
            # Get operation parameters
            cycle_time = self._get_cycle_time(op_name, part_data)
            setup_time = self.operations.get(op_name, {}).get('setup_time', 0)
            total_time = cycle_time + setup_time

            # Get takt time for resource booking
            takt_time = self._get_takt_time(op_name, cycle_time)

            # Find resource and next available time
            resource, avail_time = self._find_resource(op_name, current_time)

            # Schedule operation
            op_start = avail_time
            op_end = self.work_schedule.advance_time(op_start, total_time)

            scheduled_op = ScheduledOperation(
                operation_name=op_name,
                start_time=op_start,
                end_time=op_end,
                resource_id=resource.resource_id if resource else None,
                cycle_time=cycle_time,
                setup_time=setup_time
            )
            scheduled_ops.append(scheduled_op)

            # Book resource using TAKT TIME
            if resource:
                takt_end = self.work_schedule.advance_time(op_start, takt_time)
                resource.book(op_start, takt_end, wo_number)

            # Track BLAST date
            if op_name == 'BLAST':
                blast_date = op_start

            # Update current time
            current_time = op_end

        # Now assign the core with blast_date
        assigned_core = f"{core_number}-{core_suffix}"
        self._assign_core(core_number, core_suffix, wo_number, blast_date, part_data)

        # Calculate completion
        completion_date = scheduled_ops[-1].end_time if scheduled_ops else None

        # Calculate turnaround
        turnaround_days = None
        creation_date = order.get('creation_date')
        if creation_date and completion_date:
            try:
                turnaround_days = (completion_date - creation_date).days
            except:
                pass

        # Check on-time status
        promise_date = order.get('promise_date')
        on_time = True
        if promise_date and completion_date:
            try:
                on_time = completion_date <= promise_date
            except:
                pass

        return ScheduledOrder(
            wo_number=wo_number,
            part_number=part_number,
            description=order.get('description', ''),
            customer=order.get('customer', ''),
            is_reline=is_reline,
            assigned_core=assigned_core,
            rubber_type=part_data.get('rubber_type') if part_data else None,
            operations=scheduled_ops,
            blast_date=blast_date,
            completion_date=completion_date,
            turnaround_days=turnaround_days,
            promise_date=promise_date,
            on_time=on_time,
            creation_date=creation_date
        )

    def get_summary(self) -> Dict:
        """Get scheduling summary."""
        if not self.scheduled_orders:
            return {}

        total = len(self.scheduled_orders)
        on_time = sum(1 for o in self.scheduled_orders if o.on_time)
        reline = sum(1 for o in self.scheduled_orders if o.is_reline)

        turnarounds = [o.turnaround_days for o in self.scheduled_orders
                      if o.turnaround_days is not None]
        avg_turnaround = sum(turnarounds) / len(turnarounds) if turnarounds else None

        completion_dates = [o.completion_date for o in self.scheduled_orders
                           if o.completion_date]

        return {
            'total_scheduled': total,
            'on_time': on_time,
            'on_time_pct': (on_time / total * 100) if total else 0,
            'reline_count': reline,
            'reline_pct': (reline / total * 100) if total else 0,
            'avg_turnaround_days': avg_turnaround,
            'earliest_completion': min(completion_dates) if completion_dates else None,
            'latest_completion': max(completion_dates) if completion_dates else None,
            'pending_core': len(self.pending_core_orders),
            'unscheduled': len(self.unscheduled_orders)
        }

    def print_summary(self):
        """Print scheduling summary."""
        summary = self.get_summary()

        print(f"\n{'='*70}")
        print("SCHEDULING SUMMARY")
        print(f"{'='*70}")

        print(f"\nORDERS:")
        print(f"   Total scheduled: {summary.get('total_scheduled', 0)}")
        print(f"   On-time: {summary.get('on_time', 0)} ({summary.get('on_time_pct', 0):.1f}%)")
        print(f"   Reline: {summary.get('reline_count', 0)} ({summary.get('reline_pct', 0):.1f}%)")
        print(f"   Pending core: {summary.get('pending_core', 0)}")
        print(f"   Unscheduled: {summary.get('unscheduled', 0)}")

        if summary.get('avg_turnaround_days'):
            print(f"\nTURNAROUND:")
            print(f"   Average: {summary['avg_turnaround_days']:.1f} days")

        if summary.get('earliest_completion'):
            print(f"\nCOMPLETION RANGE:")
            print(f"   Earliest: {summary['earliest_completion']}")
            print(f"   Latest: {summary['latest_completion']}")

        if summary.get('pending_core'):
            print(f"\n[WARN] PENDING CORE: {summary['pending_core']} orders need cores not in inventory")


if __name__ == "__main__":
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from data_loader import DataLoader

    print("Testing Production Scheduler")
    print()

    # Load data
    loader = DataLoader()
    if not loader.load_all():
        print("Failed to load data")
        sys.exit(1)

    # Create scheduler
    work_schedule = WorkSchedule(
        days_per_week=5,
        shift_length=10,
        num_shifts=2,
        shift1_start=5,
        shift2_start=17
    )

    scheduler = ProductionScheduler(
        orders=loader.orders,
        core_mapping=loader.core_mapping,
        core_inventory=loader.core_inventory,
        operations=loader.operations,
        work_schedule=work_schedule
    )

    # Run scheduling
    start_date = datetime(2026, 2, 1, 5, 0)  # Feb 1, 2026, 5:00 AM
    scheduled = scheduler.schedule_orders(start_date=start_date)

    # Print summary
    scheduler.print_summary()

    # Show sample scheduled orders
    print(f"\n{'='*70}")
    print("SAMPLE SCHEDULED ORDERS (first 3):")
    print(f"{'='*70}")

    for order in scheduled[:3]:
        print(f"\nWO#: {order.wo_number}")
        print(f"  Part: {order.part_number}")
        print(f"  Core: {order.assigned_core}")
        print(f"  Rubber: {order.rubber_type}")
        print(f"  BLAST: {order.blast_date}")
        print(f"  Completion: {order.completion_date}")
        print(f"  On-time: {'Yes' if order.on_time else 'No'}")
        print(f"  Operations: {len(order.operations)}")
