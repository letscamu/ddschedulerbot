"""
Discrete Event Simulation (DES) Scheduler
Pipeline-based scheduling for stator production using event-driven simulation.

This scheduler models parts flowing through production as a pipeline where
multiple parts can be in-process simultaneously at different stations,
rather than the queue model where each order waits at each station.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import heapq


# =============================================================================
# WORK SCHEDULE CONFIGURATION
# =============================================================================

@dataclass
class DayShiftConfig:
    """
    Per-day shift configuration for advanced scheduling.

    Defines how a specific day of the week operates:
    - shift_mode: 'full' (normal staffing) or 'skeleton' (reduced staff, longer takt)
    - active_shifts: 'day', 'night', or 'both'
    - takt_time_minutes: Takt time for this day (1-120 minutes)
    """
    shift_mode: str = 'full'        # 'full' or 'skeleton'
    active_shifts: str = 'both'     # 'day', 'night', or 'both'
    takt_time_minutes: int = 30     # Per-day takt override


@dataclass
class WorkScheduleConfig:
    """
    Work schedule configuration with configurable shift hours.

    Supports:
    - 10-hour shifts: Day only (5:00 AM - 3:00 PM), no night shift
    - 12-hour shifts: Day (5:00 AM - 5:00 PM), Night (5:00 PM - 5:00 AM)
    - Configurable working days (e.g., Mon-Thu or Mon-Fri)
    - Per-day configurations (full/skeleton, day/night/both, takt override)
    - Handover: 30 minutes at shift start
    - Breaks: 15 min at 9:00/15:00 (day), 21:00/3:00 (night)
    - Lunch: 45 min at 11:00-11:45 (day), 23:00-23:45 (night)
    """
    working_days: List[int] = field(default_factory=lambda: [0, 1, 2, 3])  # Mon-Thu (4-day default)
    shift_hours: int = 12  # 10 or 12 hour shifts
    shift1_start: int = 5   # 5 AM
    shift1_end: int = 17    # 5 PM (computed from shift_hours if using factory)
    shift2_start: int = 17  # 5 PM
    shift2_end: int = 5     # 5 AM (next day)
    has_night_shift: bool = True
    handover_minutes: int = 30
    takt_time_minutes: int = 30

    # Per-day shift configurations (keyed by weekday int 0=Mon..5=Sat)
    # If empty, all working days use the same config (backward compatible)
    day_configs: Dict[int, DayShiftConfig] = field(default_factory=dict)

    # Break times (hour, minute, duration_minutes)
    day_breaks: List[Tuple[int, int, int]] = field(default_factory=lambda: [
        (9, 0, 15),    # 9:00 AM - 15 min break
        (11, 0, 45),   # 11:00 AM - 45 min lunch
        (15, 0, 15),   # 3:00 PM - 15 min break
    ])
    night_breaks: List[Tuple[int, int, int]] = field(default_factory=lambda: [
        (21, 0, 15),   # 9:00 PM - 15 min break
        (23, 0, 45),   # 11:00 PM - 45 min lunch
        (3, 0, 15),    # 3:00 AM - 15 min break
    ])

    @classmethod
    def create(cls, working_days: List[int] = None, shift_hours: int = 12,
               day_configs: Dict[int, 'DayShiftConfig'] = None,
               takt_time_minutes: int = 30) -> 'WorkScheduleConfig':
        """
        Factory method to create a properly configured WorkScheduleConfig.

        Args:
            working_days: List of weekday integers (0=Mon). Defaults to Mon-Thu.
            shift_hours: 10 or 12 hour shifts. Defaults to 12.
            day_configs: Optional per-day shift configurations for advanced mode.
            takt_time_minutes: Default takt time in minutes (1-120). Defaults to 30.

        Returns:
            Configured WorkScheduleConfig instance.
        """
        if working_days is None:
            working_days = [0, 1, 2, 3]

        if shift_hours == 10:
            # 10-hour shift: 5 AM to 3 PM, no night shift
            return cls(
                working_days=working_days,
                shift_hours=10,
                shift1_start=5,
                shift1_end=15,     # 3 PM
                shift2_start=15,   # Not used (no night shift)
                shift2_end=5,      # Not used
                has_night_shift=False,
                takt_time_minutes=takt_time_minutes,
                day_configs=day_configs or {},
                day_breaks=[
                    (9, 0, 15),    # 9:00 AM - 15 min break
                    (11, 0, 45),   # 11:00 AM - 45 min lunch
                ],
                night_breaks=[],   # No night shift
            )
        else:
            # 12-hour shift: 5 AM to 5 PM + night shift 5 PM to 5 AM
            return cls(
                working_days=working_days,
                shift_hours=12,
                shift1_start=5,
                shift1_end=17,     # 5 PM
                shift2_start=17,   # 5 PM
                shift2_end=5,      # 5 AM
                has_night_shift=True,
                takt_time_minutes=takt_time_minutes,
                day_configs=day_configs or {},
                day_breaks=[
                    (9, 0, 15),    # 9:00 AM - 15 min break
                    (11, 0, 45),   # 11:00 AM - 45 min lunch
                    (15, 0, 15),   # 3:00 PM - 15 min break
                ],
                night_breaks=[
                    (21, 0, 15),   # 9:00 PM - 15 min break
                    (23, 0, 45),   # 11:00 PM - 45 min lunch
                    (3, 0, 15),    # 3:00 AM - 15 min break
                ],
            )

    def get_day_config(self, weekday: int) -> Optional[DayShiftConfig]:
        """Get per-day config for a weekday, or None if using defaults."""
        return self.day_configs.get(weekday)

    def get_takt_for_day(self, weekday: int) -> int:
        """Get takt time in minutes for a specific weekday."""
        dc = self.get_day_config(weekday)
        if dc:
            return dc.takt_time_minutes
        return self.takt_time_minutes

    def has_night_shift_on_day(self, weekday: int) -> bool:
        """Check if night shift is active on a specific weekday."""
        dc = self.get_day_config(weekday)
        if dc:
            return dc.active_shifts in ('night', 'both')
        return self.has_night_shift

    def has_day_shift_on_day(self, weekday: int) -> bool:
        """Check if day shift is active on a specific weekday."""
        dc = self.get_day_config(weekday)
        if dc:
            return dc.active_shifts in ('day', 'both')
        return True  # Day shift always on in non-advanced mode

    def is_working_day(self, dt: datetime) -> bool:
        """Check if the date is a working day."""
        return dt.weekday() in self.working_days

    def get_blocked_periods(self, dt: datetime) -> List[Tuple[datetime, datetime]]:
        """
        Get all blocked periods (breaks, lunch, handover) for a given day.
        Returns list of (start, end) tuples.

        Per-day shift awareness: on days with active_shifts='night' only,
        the day shift hours are blocked. On days with active_shifts='day' only,
        the night shift hours are blocked.
        """
        periods = []
        date = dt.date()
        weekday = date.weekday()

        # Check if this is a working day
        if not self.is_working_day(dt):
            day_start = datetime.combine(date, datetime.min.time())
            day_end = day_start + timedelta(days=1)

            # If previous day had a night shift, early morning hours (00:00-05:00)
            # belong to that shift and should NOT be blocked
            if self.has_night_shift:
                yesterday = date - timedelta(days=1)
                if (yesterday.weekday() in self.working_days and
                        self.has_night_shift_on_day(yesterday.weekday())):
                    # Previous night shift runs until shift2_end (5 AM)
                    shift2_end_time = datetime.combine(
                        date, datetime.min.time().replace(hour=self.shift2_end))
                    periods = []
                    # Include night breaks that fall in early morning
                    for hour, minute, duration in self.night_breaks:
                        if hour < self.shift2_end:
                            break_start = datetime.combine(
                                date, datetime.min.time().replace(hour=hour, minute=minute))
                            periods.append((break_start, break_start + timedelta(minutes=duration)))
                    # Block from shift2_end (5 AM) to end of day
                    periods.append((shift2_end_time, day_end))
                    return sorted(periods, key=lambda x: x[0])

            # No previous night shift — entire day is blocked
            return [(day_start, day_end)]

        day_start = datetime.combine(date, datetime.min.time())
        # Day shift handover (5:00-5:30)
        shift1_start = datetime.combine(date, datetime.min.time().replace(hour=self.shift1_start))

        # Per-day shift awareness
        day_shift_active = self.has_day_shift_on_day(weekday)
        night_shift_active = self.has_night_shift_on_day(weekday) and self.has_night_shift

        if not night_shift_active:
            # Block time before day shift starts (midnight to shift1_start)
            periods.append((day_start, shift1_start))

        if day_shift_active:
            # Day shift handover (5:00-5:30)
            periods.append((shift1_start, shift1_start + timedelta(minutes=self.handover_minutes)))

            # Day shift breaks
            for hour, minute, duration in self.day_breaks:
                break_start = datetime.combine(date, datetime.min.time().replace(hour=hour, minute=minute))
                periods.append((break_start, break_start + timedelta(minutes=duration)))
        else:
            # Day shift not active — block entire day shift window
            shift1_end_dt = datetime.combine(date, datetime.min.time().replace(hour=self.shift1_end))
            periods.append((shift1_start, shift1_end_dt))

        if night_shift_active:
            # Night shift handover (5:00 PM - 5:30 PM)
            shift2_start = datetime.combine(date, datetime.min.time().replace(hour=self.shift2_start))
            periods.append((shift2_start, shift2_start + timedelta(minutes=self.handover_minutes)))

            # Night shift breaks
            for hour, minute, duration in self.night_breaks:
                if hour >= self.shift2_start:
                    # Same day
                    break_start = datetime.combine(date, datetime.min.time().replace(hour=hour, minute=minute))
                else:
                    # Next day (after midnight)
                    break_start = datetime.combine(date + timedelta(days=1),
                                                  datetime.min.time().replace(hour=hour, minute=minute))
                periods.append((break_start, break_start + timedelta(minutes=duration)))
        else:
            # No night shift on this day: block from shift1_end to end of day
            shift1_end_dt = datetime.combine(date, datetime.min.time().replace(hour=self.shift1_end
                                             if day_shift_active else self.shift1_start))
            next_day = datetime.combine(date + timedelta(days=1), datetime.min.time())
            if day_shift_active:
                shift1_end_dt = datetime.combine(date, datetime.min.time().replace(hour=self.shift1_end))
            periods.append((shift1_end_dt, next_day))

        return sorted(periods, key=lambda x: x[0])

    def is_blocked_time(self, dt: datetime, include_nights: bool = True) -> bool:
        """
        Check if a datetime is blocked (break, lunch, handover, or non-working).

        Args:
            dt: Datetime to check
            include_nights: If False, assumes 24-hour operations for CURE/QUENCH
        """
        date = dt.date()
        hour = dt.hour
        weekday = date.weekday()

        # Check if night shift was active on the relevant day
        if self.has_night_shift:
            if hour < self.shift2_end:
                # We're in the early morning — this is yesterday's night shift
                yesterday = date - timedelta(days=1)
                if yesterday.weekday() not in self.working_days:
                    return True
                # Check if yesterday had night shift active
                if not self.has_night_shift_on_day(yesterday.weekday()):
                    return True
            else:
                if weekday not in self.working_days:
                    return True
                # During day shift hours, check if day shift is active
                if hour >= self.shift1_start and hour < self.shift1_end:
                    if not self.has_day_shift_on_day(weekday):
                        return True
                # During night shift hours, check if night shift is active
                if hour >= self.shift2_start:
                    if not self.has_night_shift_on_day(weekday):
                        return True
        else:
            # No night shift: early morning and after shift end are blocked
            if weekday not in self.working_days:
                return True
            if hour < self.shift1_start or hour >= self.shift1_end:
                return True

        # Check breaks and handover
        for period_start, period_end in self.get_blocked_periods(dt):
            if period_start <= dt < period_end:
                return True

        return False

    def next_unblocked_time(self, dt: datetime, continue_during_breaks: bool = False) -> datetime:
        """
        Find the next unblocked time from given datetime.

        Args:
            dt: Starting datetime
            continue_during_breaks: If True (for CURE/QUENCH), only skip non-working days
        """
        current = dt
        max_iterations = 1000

        for _ in range(max_iterations):
            if continue_during_breaks:
                # Only check working days (and shift boundaries for no-night-shift)
                date = current.date()
                hour = current.hour

                if self.has_night_shift:
                    # Handle overnight - check if we're in valid working time
                    if hour < self.shift2_end:
                        yesterday = date - timedelta(days=1)
                        if yesterday.weekday() in self.working_days:
                            return current
                    else:
                        if date.weekday() in self.working_days:
                            return current
                else:
                    # No night shift: valid during shift hours on working days
                    if (date.weekday() in self.working_days and
                            self.shift1_start <= hour < self.shift1_end):
                        return current

                # Move to next working day
                current = self._next_working_day_start(current)
            else:
                if not self.is_blocked_time(current):
                    return current

                # Find end of current blocked period
                current = self._skip_blocked_period(current)

        return current

    def _skip_blocked_period(self, dt: datetime) -> datetime:
        """Skip past the current blocked period."""
        date = dt.date()
        hour = dt.hour

        # Non-working day check
        if date.weekday() not in self.working_days:
            return self._next_working_day_start(dt)

        if self.has_night_shift:
            # If non-working day, go to next working day
            if hour >= self.shift2_end:
                if date.weekday() not in self.working_days:
                    return self._next_working_day_start(dt)
            else:
                yesterday = date - timedelta(days=1)
                if yesterday.weekday() not in self.working_days:
                    # We're in early morning of a day after non-working day
                    if date.weekday() in self.working_days:
                        # Jump to day shift start with handover
                        return datetime.combine(date, datetime.min.time().replace(
                            hour=self.shift1_start, minute=self.handover_minutes))
                    else:
                        return self._next_working_day_start(dt)
        else:
            # No night shift: if outside shift hours, jump to next shift start
            if hour < self.shift1_start:
                return datetime.combine(date, datetime.min.time().replace(
                    hour=self.shift1_start, minute=self.handover_minutes))
            if hour >= self.shift1_end:
                return self._next_working_day_start(dt)

        # Check blocked periods and skip past them
        blocked_periods = self.get_blocked_periods(dt)
        for period_start, period_end in blocked_periods:
            if period_start <= dt < period_end:
                return period_end

        # If we're before shift start, jump to first working time
        if hour < self.shift1_start:
            return datetime.combine(date, datetime.min.time().replace(
                hour=self.shift1_start, minute=self.handover_minutes))

        return dt + timedelta(minutes=1)

    def _next_working_day_start(self, dt: datetime) -> datetime:
        """Find the start of the next working day (after handover)."""
        current_date = dt.date() + timedelta(days=1)

        for _ in range(10):
            if current_date.weekday() in self.working_days:
                return datetime.combine(current_date, datetime.min.time().replace(
                    hour=self.shift1_start, minute=self.handover_minutes))
            current_date += timedelta(days=1)

        return datetime.combine(current_date, datetime.min.time().replace(
            hour=self.shift1_start, minute=self.handover_minutes))

    def advance_time(self, start: datetime, hours: float,
                     continue_during_breaks: bool = False) -> datetime:
        """
        Advance time by hours, accounting for blocked periods.

        Args:
            start: Starting datetime
            hours: Hours to advance
            continue_during_breaks: If True, only pause for non-working days
        """
        if hours <= 0:
            return start

        current = self.next_unblocked_time(start, continue_during_breaks)
        remaining_minutes = hours * 60

        while remaining_minutes > 0.01:
            # Check if current time is blocked
            if continue_during_breaks:
                # Only blocked by non-working days
                date = current.date()
                hour = current.hour

                if hour < self.shift2_end:
                    yesterday = date - timedelta(days=1)
                    if yesterday.weekday() not in self.working_days:
                        current = self._next_working_day_start(current)
                        continue
                else:
                    if date.weekday() not in self.working_days:
                        current = self._next_working_day_start(current)
                        continue
            else:
                if self.is_blocked_time(current):
                    current = self.next_unblocked_time(current, continue_during_breaks)
                    continue

            # Calculate time until next blocked period
            if continue_during_breaks:
                # Calculate time until end of shift or non-working day
                date = current.date()
                hour = current.hour

                if self.has_night_shift:
                    if hour >= self.shift2_start or hour < self.shift2_end:
                        # Night shift - goes until 5 AM next day
                        if hour >= self.shift2_start:
                            next_block = datetime.combine(date + timedelta(days=1),
                                                         datetime.min.time().replace(hour=self.shift2_end))
                        else:
                            next_block = datetime.combine(date,
                                                         datetime.min.time().replace(hour=self.shift2_end))
                    else:
                        # Day shift - goes until night shift start
                        next_block = datetime.combine(date,
                                                     datetime.min.time().replace(hour=self.shift2_start))
                else:
                    # No night shift: continuous processes run until shift1_end
                    # then pause until next working day
                    next_block = datetime.combine(date,
                                                 datetime.min.time().replace(hour=self.shift1_end))

                minutes_until_block = (next_block - current).total_seconds() / 60
            else:
                minutes_until_block = self._minutes_until_next_block(current)

            if minutes_until_block >= remaining_minutes:
                current += timedelta(minutes=remaining_minutes)
                remaining_minutes = 0
            else:
                remaining_minutes -= minutes_until_block
                current += timedelta(minutes=minutes_until_block)
                current = self.next_unblocked_time(current, continue_during_breaks)

        return current

    def _minutes_until_next_block(self, dt: datetime) -> float:
        """Calculate minutes until the next blocked period."""
        blocked_periods = self.get_blocked_periods(dt)

        for period_start, period_end in blocked_periods:
            if period_start > dt:
                return (period_start - dt).total_seconds() / 60

        # Check next day's blocks
        next_day_periods = self.get_blocked_periods(dt + timedelta(days=1))
        if next_day_periods:
            return (next_day_periods[0][0] - dt).total_seconds() / 60

        return 24 * 60  # Default to 24 hours


# =============================================================================
# INJECTION MACHINE
# =============================================================================

@dataclass
class InjectionMachine:
    """
    Desma injection machine with rubber type assignments.

    Machines:
    - Desma 1, 2: HR (primary)
    - Desma 3, 4: XE (primary)
    - Desma 5: XR, XD, XE, HR (flex machine)
    """
    machine_id: str
    primary_rubber_types: List[str]
    current_rubber: Optional[str] = None
    available_at: datetime = None
    changeover_time_hours: float = 1.0

    def can_run(self, rubber_type: str) -> bool:
        """Check if this machine can run the given rubber type."""
        return rubber_type in self.primary_rubber_types

    def needs_changeover(self, rubber_type: str) -> bool:
        """Check if changeover is needed for this rubber type."""
        if self.current_rubber is None:
            return False
        return self.current_rubber != rubber_type

    def get_changeover_time(self, rubber_type: str) -> float:
        """Get changeover time in hours (0 if no changeover needed)."""
        if self.needs_changeover(rubber_type):
            return self.changeover_time_hours
        return 0


def create_injection_machines() -> List[InjectionMachine]:
    """Create the 5 Desma injection machines with their rubber type assignments."""
    return [
        InjectionMachine("Desma 1", ["HR"]),
        InjectionMachine("Desma 2", ["HR"]),
        InjectionMachine("Desma 3", ["XE"]),
        InjectionMachine("Desma 4", ["XE"]),
        InjectionMachine("Desma 5", ["XR", "XD", "XE", "HR"]),  # Flex machine
    ]


# =============================================================================
# STATION
# =============================================================================

@dataclass
class Station:
    """
    Production station/operation.

    Each station has:
    - cycle_time: How long the operation takes
    - num_machines: Number of parallel machines/resources
    - capacity: Concurrent processing capacity (for batch operations)
    - continues_during_breaks: True for CURE/QUENCH which don't pause
    """
    name: str
    cycle_time_hours: float
    num_machines: int = 1
    capacity: int = 1
    continues_during_breaks: bool = False
    is_concurrent_with: Optional[str] = None  # For TUBE PREP / CORE OVEN

    # Tracking state
    queue: List[str] = field(default_factory=list)  # Part IDs waiting
    in_process: Dict[str, datetime] = field(default_factory=dict)  # part_id -> completion_time
    machine_available_at: List[datetime] = field(default_factory=list)


def create_stations() -> Dict[str, Station]:
    """Create all production stations with their parameters."""
    return {
        'BLAST': Station('BLAST', cycle_time_hours=0.15, num_machines=1),
        'TUBE PREP': Station('TUBE PREP', cycle_time_hours=3.5, capacity=18,
                            is_concurrent_with='CORE OVEN'),
        'CORE OVEN': Station('CORE OVEN', cycle_time_hours=2.5, capacity=12,
                            is_concurrent_with='TUBE PREP'),
        'ASSEMBLY': Station('ASSEMBLY', cycle_time_hours=0.2, num_machines=1),
        'INJECTION': Station('INJECTION', cycle_time_hours=0.5, num_machines=5),  # Variable time
        'CURE': Station('CURE', cycle_time_hours=1.5, capacity=16, continues_during_breaks=True),
        'QUENCH': Station('QUENCH', cycle_time_hours=0.75, capacity=16, continues_during_breaks=True),
        'DISASSEMBLY': Station('DISASSEMBLY', cycle_time_hours=0.5, num_machines=1),  # Variable
        'BLD END CUTBACK': Station('BLD END CUTBACK', cycle_time_hours=0.25, num_machines=2),
        'INJ END CUTBACK': Station('INJ END CUTBACK', cycle_time_hours=0.25, num_machines=2),
        'CUT THREADS': Station('CUT THREADS', cycle_time_hours=1.0, num_machines=1),
        'INSPECT': Station('INSPECT', cycle_time_hours=0.25, num_machines=1),
    }


# =============================================================================
# EVENT SYSTEM
# =============================================================================

class EventType(Enum):
    """Types of simulation events."""
    BLAST_ARRIVAL = "blast_arrival"
    STATION_ENTRY = "station_entry"
    STATION_COMPLETE = "station_complete"
    CONCURRENT_READY = "concurrent_ready"  # Both TUBE PREP and CORE OVEN done


@dataclass
class SimEvent:
    """A simulation event."""
    time: datetime
    event_type: EventType
    part_id: str
    station: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)

    def __lt__(self, other):
        """For heap comparison - earlier events have higher priority."""
        return self.time < other.time


# =============================================================================
# PART STATE
# =============================================================================

@dataclass
class PartState:
    """
    State tracking for each part through the simulation.
    """
    part_id: str
    wo_number: str
    part_number: str
    description: str
    customer: str
    is_reline: bool
    serial_number: Optional[str] = None  # MVP 1.1
    rubber_type: Optional[str] = None
    core_number: Optional[int] = None
    core_suffix: Optional[str] = None

    # Part-specific times
    injection_time: float = 0.5
    cure_time: float = 1.5
    quench_time: float = 0.75
    disassembly_time: float = 0.5

    # Tracking
    blast_time: Optional[datetime] = None
    completion_time: Optional[datetime] = None
    current_station: Optional[str] = None

    # For concurrent operations
    tube_prep_complete: Optional[datetime] = None
    core_oven_complete: Optional[datetime] = None
    assembly_scheduled: bool = False  # Prevent duplicate ASSEMBLY entry

    # Operation history
    operation_history: List[Dict] = field(default_factory=list)

    # Original order data
    promise_date: Optional[datetime] = None
    creation_date: Optional[datetime] = None
    basic_finish_date: Optional[datetime] = None  # From SAP - used for On-Time calculation
    serial_number: Optional[str] = None  # From Sales Order report
    special_instructions: Optional[str] = None  # From redline requests
    supermarket_location: Optional[str] = None  # From DCP report

    # Planned resources
    planned_desma: Optional[str] = None  # Which Desma machine is assigned

    # Days idle (from Shop Dispatch "Elapsed Days")
    days_idle: Optional[int] = None

    # Priority tier
    priority: str = 'Normal'  # Hot-ASAP, Hot-Dated, Rework, Normal, CAVO


# =============================================================================
# DES SCHEDULER
# =============================================================================

class DESScheduler:
    """
    Discrete Event Simulation scheduler for pipeline production.

    This scheduler models parts flowing through production as a pipeline,
    allowing multiple parts to be in-process simultaneously at different stations.
    """

    # Routing for new stators
    NEW_STATOR_ROUTING = [
        'BLAST', 'TUBE PREP', 'CORE OVEN', 'ASSEMBLY', 'INJECTION',
        'CURE', 'QUENCH', 'DISASSEMBLY', 'BLD END CUTBACK', 'INJ END CUTBACK',
        'CUT THREADS', 'INSPECT'
    ]

    # Routing for relines (skip CUT THREADS)
    RELINE_ROUTING = [
        'BLAST', 'TUBE PREP', 'CORE OVEN', 'ASSEMBLY', 'INJECTION',
        'CURE', 'QUENCH', 'DISASSEMBLY', 'BLD END CUTBACK', 'INJ END CUTBACK',
        'INSPECT'
    ]

    def __init__(self, orders: List[Dict], core_mapping: Dict,
                 core_inventory: Dict, operations: Dict = None,
                 work_schedule: Any = None, working_days: List[int] = None,
                 shift_hours: int = 12, day_configs: Dict = None,
                 takt_time_minutes: int = 30, wip_orders: List[Dict] = None):
        """
        Initialize the DES scheduler.

        Args:
            orders: List of order dictionaries
            core_mapping: Part number to core mapping
            core_inventory: Available cores by number
            operations: Operation definitions (optional, uses defaults)
            work_schedule: Legacy parameter, ignored (uses WorkScheduleConfig)
            working_days: Override working days (e.g., [0,1,2,3] for 4-day, [0,1,2,3,4] for 5-day)
            shift_hours: Shift length in hours (10 or 12). Defaults to 12.
            day_configs: Optional per-day shift configs (Dict[int, DayShiftConfig]).
            takt_time_minutes: Default takt time (1-120 min). Defaults to 30.
            wip_orders: Orders currently in-process (already blasted, op >= 1300) used to
                        pre-mark cores as in-use so the scheduler reflects real pipeline state.
        """
        self.orders = orders
        self.wip_orders = wip_orders or []
        self.core_mapping = core_mapping
        self.core_inventory = self._init_core_inventory(core_inventory)
        self.operations = operations or {}

        # Create work schedule config using factory method
        self.work_config = WorkScheduleConfig.create(
            working_days=working_days,
            shift_hours=shift_hours,
            day_configs=day_configs,
            takt_time_minutes=takt_time_minutes
        )

        # Create stations and machines
        self.stations = create_stations()
        self.injection_machines = create_injection_machines()

        # Event queue (heap)
        self.event_queue: List[SimEvent] = []

        # Part states
        self.parts: Dict[str, PartState] = {}

        # Results
        self.scheduled_orders: List = []  # Will be ScheduledOrder objects
        self.pending_core_orders: List[Dict] = []
        self.unscheduled_orders: List[Dict] = []

        # Tracking
        self.current_time: datetime = None
        self._part_counter = 0

        # Injection machine scheduling tracker (for bottleneck detection during blast scheduling)
        # Maps machine_id -> estimated available_at time
        self._injection_schedule: Dict[str, Optional[datetime]] = {
            m.machine_id: None for m in self.injection_machines
        }
        # Track current rubber type per machine for changeover estimation
        self._injection_rubber: Dict[str, Optional[str]] = {
            m.machine_id: None for m in self.injection_machines
        }

    def _init_core_inventory(self, inventory: Dict) -> Dict:
        """Initialize core inventory with availability tracking."""
        result = {}
        for core_num, cores in inventory.items():
            result[core_num] = []
            for core in cores:
                result[core_num].append({
                    **core,
                    'available_at': None,
                    'assigned_to': None
                })
        return result

    def _get_part_data(self, part_number: str) -> Optional[Dict]:
        """Get core mapping data for a part number."""
        return self.core_mapping.get(part_number)

    def _initialize_wip_state(self, now: datetime):
        """
        Pre-mark cores for WIP orders currently in the production pipeline.

        Orders in Shop Dispatch with op >= 1300 have already been blasted and are
        flowing through injection/cure/quench. Their cores are physically in use and
        must not be treated as available until the part returns from the pipeline.
        """
        marked = 0
        for wip in self.wip_orders:
            part_number = wip.get('part_number')
            part_data = self._get_part_data(part_number)
            if not part_data:
                continue

            core_num = part_data.get('core_number')
            if not core_num:
                continue
            try:
                core_number = int(float(core_num))
            except (TypeError, ValueError):
                continue

            if core_number not in self.core_inventory:
                continue

            remaining_hours = self._estimate_remaining_hours(wip, part_data, now)
            return_time = self.work_config.advance_time(
                now, remaining_hours, continue_during_breaks=False
            )

            # Claim the first unclaimed core of this number
            for core in self.core_inventory[core_number]:
                if core['available_at'] is None:
                    core['available_at'] = return_time
                    core['assigned_to'] = wip.get('wo_number', 'WIP')
                    marked += 1
                    break

        print(f"   WIP-aware init: pre-marked {marked} cores as in-use")

    def _estimate_remaining_hours(self, wip: Dict, part_data: Dict, now: datetime) -> float:
        """
        Estimate how many more hours a WIP order will hold its core, based on
        the current SAP operation number.

        SAP operation map:
          1300       = BLAST
          1340-1360  = TUBE PREP / CORE OVEN / ASSEMBLY
          1380       = INJECTION
          1600       = CURE
          1610       = QUENCH
          1620+      = DISASSEMBLY, CUTBACK, INSPECT (core returned)
        """
        injection_time = float(part_data.get('injection_time') or 0.5)
        cure_time = float(part_data.get('cure_time') or 1.5)
        quench_time = float(part_data.get('quench_time') or 0.75)
        post_cure = 1.25  # disassembly + cleanup before core is free

        op_start = wip.get('operation_start_date')

        def elapsed_hours() -> float:
            if op_start and hasattr(op_start, 'timestamp'):
                return max(0.0, (now - op_start).total_seconds() / 3600)
            return 0.0

        try:
            op_num = int(float(wip.get('current_operation', 0)))
        except (TypeError, ValueError):
            op_num = 0

        if op_num == 1380:
            # Currently at INJECTION — estimate remaining injection time
            remaining_inj = max(0.0, injection_time - elapsed_hours())
            return remaining_inj + cure_time + quench_time + post_cure

        elif op_num == 1600:
            # Currently at CURE
            remaining_cure = max(0.0, cure_time - elapsed_hours())
            return remaining_cure + quench_time + post_cure

        elif op_num == 1610:
            # Currently at QUENCH
            remaining_quench = max(0.0, quench_time - elapsed_hours())
            return remaining_quench + post_cure

        elif op_num >= 1620:
            # DISASSEMBLY or later — core returned very soon
            return post_cure

        else:
            # Op 1300-1360: just blasted, needs full downstream processing
            return injection_time + cure_time + quench_time + post_cure

    def _generate_part_id(self) -> str:
        """Generate a unique part ID."""
        self._part_counter += 1
        return f"PART_{self._part_counter:06d}"

    def _get_routing(self, is_reline: bool) -> List[str]:
        """Get operation sequence for part type."""
        return self.RELINE_ROUTING if is_reline else self.NEW_STATOR_ROUTING

    def _find_available_core(self, core_number: int, needed_at: datetime) -> Optional[Dict]:
        """Find a core available at the given time."""
        if core_number not in self.core_inventory:
            return None

        for core in self.core_inventory[core_number]:
            if core['available_at'] is None:
                return core
            if core['available_at'] <= needed_at:
                return core

        return None

    def _get_earliest_core_availability(self, core_number: int) -> Optional[datetime]:
        """Get earliest time any core of this number becomes available."""
        if core_number not in self.core_inventory:
            return None

        earliest = None
        for core in self.core_inventory[core_number]:
            avail = core['available_at']
            if avail is None:
                return None  # Available now
            if earliest is None or avail < earliest:
                earliest = avail

        return earliest

    def _assign_core(self, core_number: int, core_suffix: str,
                     wo_number: str, blast_time: datetime,
                     part_data: Dict) -> datetime:
        """
        Assign a core and calculate when it returns.

        Estimates core return time using phased calculation that matches
        how the simulation actually processes each station:
        - Most stations pause for breaks/handovers (break-sensitive)
        - CURE and QUENCH continue during breaks (break-insensitive)

        Returns the datetime when the core becomes available again.
        """
        # Calculate core lifecycle time (handle None values)
        injection_time = (part_data.get('injection_time') if part_data else None) or 0.5
        cure_time = (part_data.get('cure_time') if part_data else None) or 1.5
        quench_time = (part_data.get('quench_time') if part_data else None) or 0.75

        # Phase 1: Break-sensitive operations (pause for breaks/handovers)
        # TUBE PREP/CORE OVEN (concurrent, ~3.5h) -> ASSEMBLY (0.2h) -> INJECTION
        pre_cure_hours = (
            3.5 +           # Max of TUBE PREP/CORE OVEN
            0.2 +           # Assembly
            injection_time +
            0.5             # Buffer for avg injection machine wait/changeover
        )

        # Phase 2: Break-insensitive operations (CURE + QUENCH continue during breaks)
        cure_quench_hours = cure_time + quench_time

        # Phase 3: Break-sensitive again (DISASSEMBLY + cleanup)
        post_cure_hours = (
            0.5 +           # Disassembly
            0.75            # Cleaning (BLD/INJ cutback, etc.)
        )

        # Calculate return time in phases matching simulation behavior
        after_injection = self.work_config.advance_time(
            blast_time, pre_cure_hours, continue_during_breaks=False
        )
        after_cure_quench = self.work_config.advance_time(
            after_injection, cure_quench_hours, continue_during_breaks=True
        )
        return_time = self.work_config.advance_time(
            after_cure_quench, post_cure_hours, continue_during_breaks=False
        )

        # Update core status
        for core in self.core_inventory[core_number]:
            if core['suffix'] == core_suffix:
                core['available_at'] = return_time
                core['assigned_to'] = wo_number
                break

        return return_time

    def _select_injection_machine(self, rubber_type: str,
                                   needed_at: datetime) -> Tuple[InjectionMachine, datetime]:
        """
        Select the best injection machine for a rubber type.

        Priority:
        1. Primary machine for rubber type that's available and already set up
        2. Primary machine for rubber type that's available
        3. Flex machine (Desma 5) if available
        4. Any primary machine with earliest availability
        """
        best_machine = None
        best_time = None

        # First pass: find primary machines that can run this rubber
        candidates = []
        for machine in self.injection_machines:
            if machine.can_run(rubber_type):
                avail_time = machine.available_at or needed_at
                avail_time = max(avail_time, needed_at)

                # Add changeover time if needed
                changeover = machine.get_changeover_time(rubber_type)
                if changeover > 0:
                    avail_time = self.work_config.advance_time(avail_time, changeover)

                candidates.append((machine, avail_time))

        if candidates:
            # Sort by availability time
            candidates.sort(key=lambda x: x[1])
            best_machine, best_time = candidates[0]
        else:
            # Fallback: use flex machine
            flex = self.injection_machines[4]  # Desma 5
            best_machine = flex
            best_time = max(flex.available_at or needed_at, needed_at)

        return best_machine, best_time

    def _estimate_injection_arrival(self, blast_time: datetime) -> datetime:
        """Estimate when a part blasted at blast_time will reach injection.
        Uses a cache since all parts at the same blast_time have the same estimate."""
        if not hasattr(self, '_inj_arrival_cache'):
            self._inj_arrival_cache = {}
        if blast_time in self._inj_arrival_cache:
            return self._inj_arrival_cache[blast_time]
        # BLAST (0.15h) + max(TUBE PREP 3.5h, CORE OVEN 2.5h) + ASSEMBLY (0.2h)
        pre_injection_hours = 0.15 + 3.5 + 0.2
        result = self.work_config.advance_time(
            blast_time, pre_injection_hours, continue_during_breaks=False
        )
        self._inj_arrival_cache[blast_time] = result
        return result

    def _check_injection_bottleneck(self, rubber_type: str, blast_time: datetime,
                                     injection_time: float = 0.5) -> Tuple[bool, Optional[str]]:
        """
        Check if scheduling a part at blast_time would cause a downstream
        injection bottleneck.

        Returns:
            (is_bottleneck, best_machine_id) — if not bottleneck, best_machine_id
            is the machine to reserve. If bottleneck, best_machine_id is None.
        """
        if not rubber_type:
            # Unknown rubber type — can't assess bottleneck, assume OK
            return False, None

        est_arrival = self._estimate_injection_arrival(blast_time)

        # Find the best available machine for this rubber type
        best_machine_id = None
        best_available = None

        for machine in self.injection_machines:
            if not machine.can_run(rubber_type):
                continue

            machine_avail = self._injection_schedule.get(machine.machine_id)
            avail_time = max(machine_avail, est_arrival) if machine_avail else est_arrival

            # Add changeover time if rubber type is different
            current_rubber = self._injection_rubber.get(machine.machine_id)
            if current_rubber and current_rubber != rubber_type:
                # Simple 1h offset for changeover estimate (avoids expensive advance_time)
                avail_time = avail_time + timedelta(hours=machine.changeover_time_hours)

            if best_available is None or avail_time < best_available:
                best_available = avail_time
                best_machine_id = machine.machine_id

        if best_machine_id is None:
            # No machine can run this rubber type at all
            return True, None

        # A machine is available — check if it would cause significant delay
        # Bottleneck = the part would have to wait more than 1 takt period (30 min)
        # for injection after arriving at the injection station
        wait_time = (best_available - est_arrival).total_seconds() / 3600
        if wait_time > 0.5:  # More than 30 min wait = bottleneck
            return True, None

        return False, best_machine_id

    def _reserve_injection_machine(self, machine_id: str, rubber_type: str,
                                    blast_time: datetime, injection_time: float = 0.5):
        """Reserve an injection machine slot during blast scheduling."""
        est_arrival = self._estimate_injection_arrival(blast_time)

        machine_avail = self._injection_schedule.get(machine_id)
        start_time = max(machine_avail, est_arrival) if machine_avail else est_arrival

        # Add changeover if needed (simple offset for scheduling estimate)
        current_rubber = self._injection_rubber.get(machine_id)
        if current_rubber and current_rubber != rubber_type:
            start_time = start_time + timedelta(hours=1.0)  # 1h changeover

        # Machine busy for injection_time hours (simple offset for estimate)
        end_time = start_time + timedelta(hours=injection_time)
        self._injection_schedule[machine_id] = end_time
        self._injection_rubber[machine_id] = rubber_type

    def schedule_orders(self, start_date: datetime = None,
                        hot_list_entries: List[Dict] = None) -> List:
        """
        Schedule all orders using discrete event simulation.

        Args:
            start_date: Start date for scheduling
            hot_list_entries: List of hot list entry dicts with priority info

        Returns:
            List of ScheduledOrder objects
        """
        # Import here to avoid circular dependency
        from algorithms.scheduler import ScheduledOrder, ScheduledOperation

        if start_date is None:
            now = datetime.now()
            today_shift_start = now.replace(hour=5, minute=30, second=0, microsecond=0)
            if now <= today_shift_start:
                # Before today's shift start — begin today
                start_date = today_shift_start
            else:
                # After today's shift has started — begin at the next working day
                start_date = self.work_config._next_working_day_start(now)

        self.current_time = start_date
        self.hot_list_entries = hot_list_entries or []
        self.hot_list_lookup = {e['wo_number']: e for e in self.hot_list_entries}
        self.hot_list_core_shortages = []  # Track hot list orders that can't be scheduled

        print(f"\n{'='*70}")
        print(f"DES SCHEDULER: {len(self.orders)} ORDERS")
        print(f"Start date: {start_date}")
        if self.hot_list_entries:
            print(f"Hot list entries: {len(self.hot_list_entries)}")
        print(f"{'='*70}")

        # Pre-mark cores for WIP orders currently in the production pipeline
        if self.wip_orders:
            self._initialize_wip_state(datetime.now())

        # Step 1: Classify orders
        schedulable, pending = self._classify_orders()
        self.pending_core_orders = pending

        print(f"   Schedulable orders: {len(schedulable)}")
        print(f"   Pending core orders: {len(pending)}")

        # Step 2: Sort orders (5-tier priority: hot list ASAP, hot list dated, rework, normal, CAVO)
        sorted_orders = self._sort_orders(schedulable, hot_list_entries)

        # Step 3: Schedule BLAST arrivals at takt intervals
        self._schedule_blast_arrivals(sorted_orders, start_date)

        # Step 4: Run event loop
        self._run_simulation()

        # Step 5: Collect results
        self._collect_results(ScheduledOrder, ScheduledOperation)

        print(f"\n[OK] Scheduled: {len(self.scheduled_orders)} orders")
        print(f"[!!] Pending core: {len(self.pending_core_orders)} orders")

        # Print completion time stats
        if self.scheduled_orders:
            completion_times = [(o.completion_date - o.blast_date).total_seconds() / 3600
                               for o in self.scheduled_orders if o.completion_date and o.blast_date]
            if completion_times:
                avg_hours = sum(completion_times) / len(completion_times)
                print(f"\nPipeline Statistics:")
                print(f"   Average completion time: {avg_hours:.1f} hours")
                print(f"   Min completion time: {min(completion_times):.1f} hours")
                print(f"   Max completion time: {max(completion_times):.1f} hours")

        return self.scheduled_orders

    def _classify_orders(self) -> Tuple[List[Dict], List[Dict]]:
        """Classify orders into schedulable (core exists) vs pending (no core)."""
        schedulable = []
        pending = []

        for order in self.orders:
            part_number = order.get('part_number')
            part_data = self._get_part_data(part_number)

            # Get core number
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
                pending.append({
                    **order,
                    'reason': 'No core mapping for part number',
                    'core_number_needed': None
                })
            elif core_number not in self.core_inventory:
                pending.append({
                    **order,
                    'reason': f'Core {core_number} not in inventory',
                    'core_number_needed': core_number
                })
            else:
                schedulable.append({
                    'order': order,
                    'core_number': core_number,
                    'part_data': part_data
                })

        return schedulable, pending

    def _sort_orders(self, orders: List[Dict], hot_list_entries: List[Dict] = None) -> List[Dict]:
        """
        Sort orders with 5-tier priority system:

        1. Hot List - ASAP (sorted by DATE REQ MADE, then row position)
        2. Hot List - Dated (sorted by NEED BY DATE, then DATE REQ MADE, then row position)
        3. Rework (sorted by Created On - FIFO)
        4. Normal (sorted by Created On - FIFO)
        5. CAVO (sorted by Created On - FIFO, lowest priority)

        Args:
            orders: List of order info dicts with 'order', 'core_number', 'part_data'
            hot_list_entries: List of hot list entry dicts (already sorted by priority)

        Returns:
            Sorted list of orders
        """
        hot_list_entries = hot_list_entries or []

        # Create lookup from WO# to hot list entry
        hot_list_lookup = {e['wo_number']: e for e in hot_list_entries}

        def get_created_on(o):
            order = o['order']
            created_on = order.get('created_on')
            if created_on and hasattr(created_on, 'timestamp'):
                return created_on.timestamp()
            wo_creation = order.get('wo_creation_date')
            if wo_creation and hasattr(wo_creation, 'timestamp'):
                return wo_creation.timestamp()
            return float('inf')

        def get_hot_list_sort_key(o):
            """Get sort key for hot list orders based on hot list entry."""
            wo_number = o['order'].get('wo_number')
            entry = hot_list_lookup.get(wo_number, {})

            is_asap = entry.get('is_asap', False)
            need_by_date = entry.get('need_by_date')
            date_req_made = entry.get('date_req_made')
            row_position = entry.get('row_position', 0)

            # Get timestamps for sorting (lower = higher priority)
            date_req_ts = date_req_made.timestamp() if date_req_made and hasattr(date_req_made, 'timestamp') else float('inf')
            need_by_ts = need_by_date.timestamp() if need_by_date and hasattr(need_by_date, 'timestamp') else float('inf')

            if is_asap:
                # ASAP: priority 0, sort by date_req_made, then row_position
                return (0, date_req_ts, row_position)
            else:
                # Dated: priority 1, sort by need_by_date, then date_req_made, then row_position
                return (1, need_by_ts, date_req_ts, row_position)

        # Categorize orders
        hot_list_asap = []
        hot_list_dated = []
        rework_orders = []
        normal_orders = []
        cavo_orders = []

        for o in orders:
            wo_number = o['order'].get('wo_number')
            customer = o['order'].get('customer', '') or ''
            is_rework = o['order'].get('is_rework', False)

            if wo_number in hot_list_lookup:
                entry = hot_list_lookup[wo_number]
                # Propagate special_instructions from hot list/app requests
                if entry.get('special_instructions'):
                    o['order']['special_instructions'] = entry['special_instructions']
                if entry.get('is_asap'):
                    o['order']['priority'] = 'Hot-ASAP'
                    hot_list_asap.append(o)
                else:
                    o['order']['priority'] = 'Hot-Dated'
                    hot_list_dated.append(o)
            elif is_rework:
                o['order']['priority'] = 'Rework'
                rework_orders.append(o)
            elif 'CAVO DRILLING MOTORS' in customer.upper():
                o['order']['priority'] = 'CAVO'
                cavo_orders.append(o)
            else:
                o['order']['priority'] = 'Normal'
                normal_orders.append(o)

        # Sort each category
        hot_list_asap.sort(key=get_hot_list_sort_key)
        hot_list_dated.sort(key=get_hot_list_sort_key)
        rework_orders.sort(key=get_created_on)
        normal_orders.sort(key=get_created_on)
        cavo_orders.sort(key=get_created_on)

        print(f"   Priority breakdown:")
        print(f"      Hot List ASAP: {len(hot_list_asap)}")
        print(f"      Hot List Dated: {len(hot_list_dated)}")
        print(f"      Rework: {len(rework_orders)}")
        print(f"      Normal: {len(normal_orders)}")
        print(f"      CAVO (low priority): {len(cavo_orders)}")

        return hot_list_asap + hot_list_dated + rework_orders + normal_orders + cavo_orders

    def _get_rubber_type_for_order(self, order_info: Dict) -> Optional[str]:
        """Get the effective rubber type for an order (including hot list override)."""
        order = order_info['order']
        part_data = order_info['part_data']
        wo_number = order.get('wo_number')

        rubber_type = part_data.get('rubber_type') if part_data else None
        if wo_number in self.hot_list_lookup:
            hot_list_entry = self.hot_list_lookup[wo_number]
            rubber_override = hot_list_entry.get('rubber_override')
            if rubber_override:
                rubber_type = rubber_override
        return rubber_type

    def _schedule_blast_arrivals(self, orders: List[Dict], start_date: datetime):
        """
        Schedule BLAST arrivals at takt intervals.

        For each takt slot, scans the entire prioritized order pool:
        1. Is there a core available for this order?
        2. Will scheduling it cause a downstream injection bottleneck?
        3. If both pass -> schedule. Otherwise try the next order.

        A slot is only skipped if ALL remaining orders either have no
        available core or would cause an injection bottleneck.

        Uses per-day takt times when day_configs are set (advanced mode).
        """
        # Ensure we start at a valid (unblocked) working time
        current_slot = self.work_config.next_unblocked_time(start_date)
        last_rubber_type = None  # Track for rubber type alternation

        remaining_orders = orders.copy()
        max_empty_slots = 500  # Safety: max consecutive empty takt slots before giving up
        consecutive_empty = 0

        while remaining_orders:
            scheduled_this_slot = False
            all_blocked_by_bottleneck = False

            # Scan the entire pool by priority to find a schedulable order.
            # Within the top priority tier, collect all candidates (for rubber
            # alternation). If the top tier has no viable candidate, fall through
            # to lower tiers one order at a time.
            first_priority = remaining_orders[0]['order'].get('priority', 'Normal')

            # Phase 1: Collect candidates from the top priority tier
            tier_candidates = []  # (index, order_info, core, rubber_type, machine_id)
            tier_had_core_but_bottleneck = False
            for i, order_info in enumerate(remaining_orders):
                if order_info['order'].get('priority', 'Normal') != first_priority:
                    break  # End of top tier

                core = self._find_available_core(order_info['core_number'], current_slot)
                if not core:
                    continue  # No core — try next in tier

                rubber_type = self._get_rubber_type_for_order(order_info)
                injection_time = (order_info['part_data'].get('injection_time')
                                  if order_info['part_data'] else None) or 0.5

                is_bottleneck, machine_id = self._check_injection_bottleneck(
                    rubber_type, current_slot, injection_time)
                if is_bottleneck:
                    tier_had_core_but_bottleneck = True
                    continue  # Bottleneck — try next in tier

                tier_candidates.append((i, order_info, core, rubber_type, machine_id))

            # Phase 2: If no candidates from top tier, scan remaining orders
            # from OTHER priority tiers (orders already checked in Phase 1 are skipped)
            if not tier_candidates:
                any_core_but_bottleneck = tier_had_core_but_bottleneck
                # Find where the top tier ends in remaining_orders
                top_tier_end = 0
                for idx, oi in enumerate(remaining_orders):
                    if oi['order'].get('priority', 'Normal') != first_priority:
                        break
                    top_tier_end = idx + 1

                for i in range(top_tier_end, len(remaining_orders)):
                    order_info = remaining_orders[i]

                    core = self._find_available_core(order_info['core_number'], current_slot)
                    if not core:
                        continue

                    rubber_type = self._get_rubber_type_for_order(order_info)
                    injection_time = (order_info['part_data'].get('injection_time')
                                      if order_info['part_data'] else None) or 0.5

                    is_bottleneck, machine_id = self._check_injection_bottleneck(
                        rubber_type, current_slot, injection_time)
                    if is_bottleneck:
                        any_core_but_bottleneck = True
                        continue

                    # Found a viable order from a lower tier
                    tier_candidates.append((i, order_info, core, rubber_type, machine_id))
                    break  # Take the first viable from lower tiers

                if not tier_candidates:
                    all_blocked_by_bottleneck = any_core_but_bottleneck

            # Phase 3: Select the best candidate (prefer rubber alternation)
            if tier_candidates:
                selected = tier_candidates[0]
                if last_rubber_type and len(tier_candidates) > 1:
                    for candidate in tier_candidates:
                        if candidate[3] and candidate[3] != last_rubber_type:
                            selected = candidate
                            break

                i, order_info, core, rubber_type, machine_id = selected
                order = order_info['order']
                core_number = order_info['core_number']
                part_data = order_info['part_data']
                wo_number = order.get('wo_number')

                # Create part state
                part_id = self._generate_part_id()
                part_number = order.get('part_number', '')
                is_reline = part_number.startswith('XN')

                # Calculate BLAST time - account for rework lead time
                blast_time = current_slot
                is_rework = order.get('is_rework', False)
                rework_lead_time_hours = order.get('rework_lead_time_hours', 0)

                if is_rework and rework_lead_time_hours > 0:
                    blast_time = self.work_config.advance_time(
                        current_slot, rework_lead_time_hours
                    )

                injection_time = (part_data.get('injection_time') if part_data else None) or 0.5

                part_state = PartState(
                    part_id=part_id,
                    wo_number=wo_number,
                    part_number=part_number,
                    description=order.get('description', ''),
                    customer=order.get('customer', ''),
                    is_reline=is_reline,
                    rubber_type=rubber_type,
                    core_number=core_number,
                    core_suffix=core['suffix'],
                    injection_time=injection_time,
                    cure_time=(part_data.get('cure_time') if part_data else None) or 1.5,
                    quench_time=(part_data.get('quench_time') if part_data else None) or 0.75,
                    disassembly_time=(part_data.get('disassembly_time') if part_data else None) or 0.5,
                    promise_date=order.get('promise_date'),
                    creation_date=order.get('creation_date') or order.get('created_on'),
                    basic_finish_date=order.get('basic_finish_date'),
                    serial_number=order.get('serial_number'),
                    priority=order.get('priority', 'Normal'),
                    special_instructions=order.get('special_instructions'),
                    supermarket_location=order.get('supermarket_location'),
                    days_idle=order.get('days_idle')
                )

                self.parts[part_id] = part_state
                last_rubber_type = rubber_type

                # Assign core (use blast_time for core return calculation)
                self._assign_core(core_number, core['suffix'],
                                 wo_number, blast_time, part_data)

                # Reserve injection machine slot for bottleneck tracking
                if machine_id:
                    self._reserve_injection_machine(
                        machine_id, rubber_type, blast_time, injection_time)

                # Schedule BLAST arrival event
                event = SimEvent(
                    time=blast_time,
                    event_type=EventType.BLAST_ARRIVAL,
                    part_id=part_id,
                    station='BLAST'
                )
                heapq.heappush(self.event_queue, event)

                remaining_orders.pop(i)
                scheduled_this_slot = True

            # Advance to next slot
            if scheduled_this_slot:
                consecutive_empty = 0
                takt_minutes = self.work_config.get_takt_for_day(current_slot.weekday())
                current_slot = self.work_config.advance_time(
                    current_slot, takt_minutes / 60.0
                )
            elif all_blocked_by_bottleneck:
                # All orders have cores but injection is full — skip one takt slot
                consecutive_empty += 1
                if consecutive_empty >= max_empty_slots:
                    print(f"[WARN] Scheduling stopped: {consecutive_empty} consecutive "
                          f"empty slots (injection bottleneck). {len(remaining_orders)} "
                          f"orders unscheduled.")
                    break
                takt_minutes = self.work_config.get_takt_for_day(current_slot.weekday())
                current_slot = self.work_config.advance_time(
                    current_slot, takt_minutes / 60.0
                )
            else:
                # No cores available for any order — jump to earliest core return
                earliest_avail = None
                for order_info in remaining_orders:
                    avail = self._get_earliest_core_availability(order_info['core_number'])
                    if avail is None:
                        earliest_avail = current_slot
                        break
                    if earliest_avail is None or avail < earliest_avail:
                        earliest_avail = avail

                if earliest_avail is None:
                    # No cores will ever become available — record shortages and stop
                    for order_info in remaining_orders:
                        wo_number = order_info['order'].get('wo_number')
                        if wo_number in self.hot_list_lookup:
                            self.hot_list_core_shortages.append({
                                'wo_number': wo_number,
                                'core_number_needed': order_info['core_number'],
                                'hot_list_entry': self.hot_list_lookup[wo_number]
                            })
                    break

                # Jump to earliest availability
                takt_minutes = self.work_config.get_takt_for_day(current_slot.weekday())
                next_slot = max(
                    self.work_config.advance_time(current_slot, takt_minutes / 60.0),
                    earliest_avail
                )
                current_slot = self.work_config.next_unblocked_time(next_slot)

    def _run_simulation(self):
        """Run the discrete event simulation."""
        while self.event_queue:
            event = heapq.heappop(self.event_queue)
            self.current_time = event.time

            if event.event_type == EventType.BLAST_ARRIVAL:
                self._handle_blast_arrival(event)
            elif event.event_type == EventType.STATION_ENTRY:
                self._handle_station_entry(event)
            elif event.event_type == EventType.STATION_COMPLETE:
                self._handle_station_complete(event)
            elif event.event_type == EventType.CONCURRENT_READY:
                self._handle_concurrent_ready(event)

    def _handle_blast_arrival(self, event: SimEvent):
        """Handle part arriving at BLAST station."""
        part = self.parts[event.part_id]
        part.blast_time = event.time
        part.current_station = 'BLAST'

        # Process BLAST
        station = self.stations['BLAST']
        cycle_time = station.cycle_time_hours

        end_time = self.work_config.advance_time(event.time, cycle_time)

        # Record operation
        part.operation_history.append({
            'operation': 'BLAST',
            'start_time': event.time,
            'end_time': end_time
        })

        # Schedule completion
        complete_event = SimEvent(
            time=end_time,
            event_type=EventType.STATION_COMPLETE,
            part_id=event.part_id,
            station='BLAST'
        )
        heapq.heappush(self.event_queue, complete_event)

    def _handle_station_entry(self, event: SimEvent):
        """Handle part entering a station."""
        part = self.parts[event.part_id]
        station_name = event.station
        station = self.stations[station_name]

        part.current_station = station_name

        # Get cycle time (may be variable) - ensure not None
        if station_name == 'INJECTION':
            cycle_time = part.injection_time or 0.5
        elif station_name == 'CURE':
            cycle_time = part.cure_time or 1.5
        elif station_name == 'QUENCH':
            cycle_time = part.quench_time or 0.75
        elif station_name == 'DISASSEMBLY':
            cycle_time = part.disassembly_time or 0.5
        else:
            cycle_time = station.cycle_time_hours

        # Calculate end time
        continues_during_breaks = station.continues_during_breaks
        start_time = event.time

        # Handle INJECTION machine selection
        if station_name == 'INJECTION':
            machine, available_time = self._select_injection_machine(
                part.rubber_type or 'HR', start_time
            )
            start_time = available_time

            # Update machine state and track planned Desma
            end_time = self.work_config.advance_time(start_time, cycle_time)
            machine.available_at = end_time
            machine.current_rubber = part.rubber_type or 'HR'
            part.planned_desma = machine.machine_id  # Track which Desma is assigned

            part.operation_history.append({
                'operation': station_name,
                'start_time': start_time,
                'end_time': end_time,
                'machine': machine.machine_id
            })
        else:
            end_time = self.work_config.advance_time(
                start_time, cycle_time,
                continue_during_breaks=continues_during_breaks
            )

            part.operation_history.append({
                'operation': station_name,
                'start_time': start_time,
                'end_time': end_time
            })

        # Handle concurrent operations (TUBE PREP / CORE OVEN)
        if station_name == 'TUBE PREP':
            part.tube_prep_complete = end_time
        elif station_name == 'CORE OVEN':
            part.core_oven_complete = end_time

        # Schedule completion
        complete_event = SimEvent(
            time=end_time,
            event_type=EventType.STATION_COMPLETE,
            part_id=event.part_id,
            station=station_name
        )
        heapq.heappush(self.event_queue, complete_event)

    def _handle_station_complete(self, event: SimEvent):
        """Handle part completing a station."""
        part = self.parts[event.part_id]
        station_name = event.station

        # Get routing
        routing = self._get_routing(part.is_reline)

        # Find next station(s)
        try:
            current_idx = routing.index(station_name)
        except ValueError:
            # Station not in routing (shouldn't happen)
            return

        # Handle special case: BLAST -> TUBE PREP + CORE OVEN (concurrent)
        if station_name == 'BLAST':
            # Start both TUBE PREP and CORE OVEN concurrently
            for next_station in ['TUBE PREP', 'CORE OVEN']:
                entry_event = SimEvent(
                    time=event.time,
                    event_type=EventType.STATION_ENTRY,
                    part_id=event.part_id,
                    station=next_station
                )
                heapq.heappush(self.event_queue, entry_event)
            return

        # Handle concurrent completion: TUBE PREP or CORE OVEN
        if station_name in ['TUBE PREP', 'CORE OVEN']:
            # Check if both are complete and ASSEMBLY not yet scheduled
            if part.tube_prep_complete and part.core_oven_complete and not part.assembly_scheduled:
                # Both done - proceed to ASSEMBLY
                part.assembly_scheduled = True
                ready_time = max(part.tube_prep_complete, part.core_oven_complete)
                entry_event = SimEvent(
                    time=ready_time,
                    event_type=EventType.STATION_ENTRY,
                    part_id=event.part_id,
                    station='ASSEMBLY'
                )
                heapq.heappush(self.event_queue, entry_event)
            # Otherwise wait for the other one to complete
            return

        # Normal sequential flow
        if current_idx < len(routing) - 1:
            next_station = routing[current_idx + 1]

            # Skip TUBE PREP and CORE OVEN (handled above)
            if next_station in ['TUBE PREP', 'CORE OVEN']:
                return

            # Schedule entry to next station
            entry_event = SimEvent(
                time=event.time,
                event_type=EventType.STATION_ENTRY,
                part_id=event.part_id,
                station=next_station
            )
            heapq.heappush(self.event_queue, entry_event)
        else:
            # Last station - part complete
            part.completion_time = event.time
            part.current_station = 'COMPLETE'

    def _handle_concurrent_ready(self, event: SimEvent):
        """Handle both concurrent operations completing."""
        # This is handled in _handle_station_complete for simplicity
        pass

    def _collect_results(self, ScheduledOrder, ScheduledOperation):
        """Collect simulation results into ScheduledOrder objects."""
        for part_id, part in self.parts.items():
            if part.completion_time is None:
                # Part didn't complete - add to unscheduled
                continue

            # Create ScheduledOperation objects
            operations = []
            for op_record in part.operation_history:
                sched_op = ScheduledOperation(
                    operation_name=op_record['operation'],
                    start_time=op_record['start_time'],
                    end_time=op_record['end_time'],
                    resource_id=op_record.get('machine'),
                    cycle_time=(op_record['end_time'] - op_record['start_time']).total_seconds() / 3600
                )
                operations.append(sched_op)

            # Calculate turnaround: Completion Date - WO Creation Date (for all order types)
            # MVP 1.1: Unified turnaround logic (Pegging Report eliminated)
            turnaround_days = None
            if part.completion_time:
                try:
                    if part.creation_date:
                        turnaround_days = (part.completion_time - part.creation_date).days
                except:
                    pass

            # Check on-time status (compare against Basic Finish Date, not Promise Date)
            on_time = True
            if part.basic_finish_date and part.completion_time:
                try:
                    on_time = part.completion_time <= part.basic_finish_date
                except:
                    pass

            # Create ScheduledOrder
            scheduled = ScheduledOrder(
                wo_number=part.wo_number,
                part_number=part.part_number,
                description=part.description,
                customer=part.customer,
                is_reline=part.is_reline,
                serial_number=part.serial_number,
                assigned_core=f"{part.core_number}-{part.core_suffix}" if part.core_number else None,
                rubber_type=part.rubber_type,
                operations=operations,
                blast_date=part.blast_time,
                completion_date=part.completion_time,
                turnaround_days=turnaround_days,
                basic_finish_date=part.basic_finish_date,
                promise_date=part.promise_date,
                on_time=on_time,
                creation_date=part.creation_date,
                planned_desma=part.planned_desma,
                priority=part.priority,
                special_instructions=part.special_instructions,
                supermarket_location=part.supermarket_location,
                days_idle=part.days_idle
            )

            self.scheduled_orders.append(scheduled)

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

        # Pipeline metrics
        completion_times = []
        for o in self.scheduled_orders:
            if o.completion_date and o.blast_date:
                hours = (o.completion_date - o.blast_date).total_seconds() / 3600
                completion_times.append(hours)

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
            'unscheduled': len(self.unscheduled_orders),
            'avg_pipeline_hours': sum(completion_times) / len(completion_times) if completion_times else None,
            'min_pipeline_hours': min(completion_times) if completion_times else None,
            'max_pipeline_hours': max(completion_times) if completion_times else None,
        }

    def print_summary(self):
        """Print scheduling summary."""
        summary = self.get_summary()

        print(f"\n{'='*70}")
        print("DES SCHEDULING SUMMARY")
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

        if summary.get('avg_pipeline_hours'):
            print(f"\nPIPELINE FLOW:")
            print(f"   Average completion time: {summary['avg_pipeline_hours']:.1f} hours")
            print(f"   Min: {summary['min_pipeline_hours']:.1f} hours")
            print(f"   Max: {summary['max_pipeline_hours']:.1f} hours")

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

    print("Testing DES Scheduler")
    print()

    # Load data
    loader = DataLoader()
    if not loader.load_all():
        print("Failed to load data")
        sys.exit(1)

    # Create DES scheduler
    scheduler = DESScheduler(
        orders=loader.orders,
        core_mapping=loader.core_mapping,
        core_inventory=loader.core_inventory,
        operations=loader.operations
    )

    # Run scheduling
    start_date = datetime(2026, 2, 2, 5, 30)  # Feb 2, 2026, 5:30 AM (Mon, after handover)
    scheduled = scheduler.schedule_orders(start_date=start_date)

    # Print summary
    scheduler.print_summary()

    # Show sample scheduled orders
    print(f"\n{'='*70}")
    print("SAMPLE SCHEDULED ORDERS (first 5):")
    print(f"{'='*70}")

    for order in scheduled[:5]:
        print(f"\nWO#: {order.wo_number}")
        print(f"  Part: {order.part_number}")
        print(f"  Core: {order.assigned_core}")
        print(f"  Rubber: {order.rubber_type}")
        print(f"  BLAST: {order.blast_date}")
        print(f"  Completion: {order.completion_date}")
        if order.blast_date and order.completion_date:
            hours = (order.completion_date - order.blast_date).total_seconds() / 3600
            print(f"  Pipeline time: {hours:.1f} hours")
        print(f"  Operations: {len(order.operations)}")
