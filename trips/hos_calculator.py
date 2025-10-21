"""
Hours of Service (HOS) Calculator
Based on FMCSA regulations for property-carrying CMV drivers
"""
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
import math


class HOSCalculator:
    """
    Calculate Hours of Service compliance for truck drivers
    Following 70hrs/8days rule for property-carrying drivers
    Includes support for split sleeper berth, 34-hour restart, and HOS exceptions
    """
    
    # HOS Limits (in hours)
    MAX_DRIVING_TIME = 11  # Maximum driving time per shift
    MAX_ON_DUTY_TIME = 14  # Maximum on-duty window
    MAX_WEEKLY_HOURS_70 = 70  # 70 hours in 8 days
    MAX_WEEKLY_HOURS_60 = 60  # 60 hours in 7 days
    MAX_DAYS_70 = 8
    MAX_DAYS_60 = 7
    MIN_OFF_DUTY_TIME = 10  # Minimum consecutive off-duty time
    BREAK_REQUIRED_AFTER = 8  # Hours of driving before break required
    MIN_BREAK_DURATION = 0.5  # 30 minutes break
    
    # Split Sleeper Berth
    SPLIT_SLEEPER_7_3 = (7, 3)  # 7 hours + 3 hours
    SPLIT_SLEEPER_8_2 = (8, 2)  # 8 hours + 2 hours
    
    # 34-Hour Restart
    RESTART_HOURS = 34
    
    # 16-Hour Short-Haul Extension
    SHORT_HAUL_EXTENSION_HOURS = 16
    
    # Adverse Driving Conditions
    ADVERSE_CONDITIONS_EXTENSION = 2
    
    # 150 Air-Mile Exception
    AIR_MILE_EXCEPTION_DISTANCE = 150
    AIR_MILE_EXCEPTION_TIME = 14
    
    # Operational constants
    AVERAGE_SPEED = 60  # mph (accounting for stops, traffic, etc.)
    FUELING_TIME = 0.5  # 30 minutes for fueling
    PICKUP_DROPOFF_TIME = 1.0  # 1 hour for pickup/dropoff
    FUELING_INTERVAL = 1000  # miles between fueling stops
    
    def __init__(self, 
                 current_cycle_used: float = 0,
                 weekly_mode: str = '70/8',
                 daily_hours_history: List[Dict] = None,
                 use_split_sleeper: bool = False,
                 reverse_geocode_func=None):
        """
        Initialize HOS Calculator
        
        Args:
            current_cycle_used: Hours already used in current cycle
            weekly_mode: '70/8' or '60/7' for weekly hours limit
            daily_hours_history: List of {'date': str, 'on_duty_hours': float} for rolling calculation
            use_split_sleeper: Whether to use split sleeper berth option
            reverse_geocode_func: Function to convert coordinates to city, state
        """
        self.current_cycle_used = current_cycle_used
        self.weekly_mode = weekly_mode
        self.use_split_sleeper = use_split_sleeper
        self.reverse_geocode_func = reverse_geocode_func
        
        # Set max hours based on mode
        if weekly_mode == '60/7':
            self.max_weekly_hours = self.MAX_WEEKLY_HOURS_60
            self.max_days = self.MAX_DAYS_60
        else:
            self.max_weekly_hours = self.MAX_WEEKLY_HOURS_70
            self.max_days = self.MAX_DAYS_70
        
        # Initialize daily hours history
        self.daily_hours_history = daily_hours_history or []
        
        # Calculate remaining weekly hours
        self.remaining_weekly_hours = self.max_weekly_hours - current_cycle_used
        
        # Track split sleeper berth segments
        self.sleeper_segments = []
        
        # Track 34-hour restart eligibility
        self.last_restart_time = None
        
        # HOS exceptions tracking
        self.short_haul_used_count = 0  # Can use 16-hour exception once per 7 days
        self.adverse_conditions_active = False
        self.air_mile_exception_active = False
        
    def calculate_trip_plan(self, 
                           current_location: Dict[str, float],
                           pickup_location: Dict[str, float],
                           dropoff_location: Dict[str, float],
                           route_data: Dict,
                           start_time: datetime = None) -> Dict:
        """
        Calculate complete trip plan with HOS compliance
        
        Args:
            current_location: {lat, lon} of current position
            pickup_location: {lat, lon} of pickup point
            dropoff_location: {lat, lon} of delivery point
            route_data: Route information from Azure Maps
            start_time: Trip start time (defaults to now)
            
        Returns:
            Complete trip plan with stops, rest breaks, and ELD logs
        """
        if start_time is None:
            start_time = datetime.now()
            
        # Extract route segments
        legs = []
        
        # Leg 1: Current to Pickup
        if route_data.get('leg1'):
            legs.append({
                'start': current_location,
                'end': pickup_location,
                'distance_miles': route_data['leg1']['distance_miles'],
                'duration_hours': route_data['leg1']['duration_hours'],
                'type': 'to_pickup',
                'description': 'Current Location to Pickup'
            })
        
        # Leg 2: Pickup to Dropoff
        if route_data.get('leg2'):
            legs.append({
                'start': pickup_location,
                'end': dropoff_location,
                'distance_miles': route_data['leg2']['distance_miles'],
                'duration_hours': route_data['leg2']['duration_hours'],
                'type': 'to_dropoff',
                'description': 'Pickup to Dropoff'
            })
        
        # Calculate total distance and time
        total_distance = sum(leg['distance_miles'] for leg in legs)
        total_driving_time = sum(leg['duration_hours'] for leg in legs)
        
        # Calculate required stops and breaks
        schedule = self._create_schedule(legs, start_time)
        
        # Generate daily logs
        daily_logs = self._generate_daily_logs(schedule)
        
        return {
            'total_distance_miles': round(total_distance, 1),
            'total_driving_hours': round(total_driving_time, 1),
            'estimated_total_hours': round(schedule[-1]['end_time_hours'], 1),
            'schedule': schedule,
            'daily_logs': daily_logs,
            'hos_compliance': self._check_hos_compliance(schedule),
            'summary': self._generate_summary(schedule, start_time)
        }
    
    def _create_schedule(self, legs: List[Dict], start_time: datetime) -> List[Dict]:
        """
        Create detailed schedule with all stops and breaks
        
        Returns list of schedule items with timing and duty status
        """
        schedule = []
        current_time = start_time
        current_shift_driving = 0  # Driving hours in current shift
        current_shift_on_duty = 0  # On-duty hours in current shift
        current_continuous_driving = 0  # Continuous driving since last break
        total_distance_covered = 0
        
        # Track for split sleeper berth
        pending_sleeper_segment = None
        
        # Track work reporting location for 16-hour exception
        work_reporting_location = None
        consecutive_days_same_location = 0
        
        for leg_index, leg in enumerate(legs):
            leg_distance = leg['distance_miles']
            remaining_leg_distance = leg_distance
            current_location = leg['start']
            
            # Get location info
            location_info = self._get_location_info(current_location)
            
            # Add pickup/dropoff time at start of leg
            if leg['type'] == 'to_pickup':
                # Start of trip - pre-trip inspection
                schedule.append({
                    'activity': 'Pre-Trip Inspection',
                    'duty_status': 'on_duty_not_driving',
                    'duration_hours': 0.25,
                    'start_time': current_time,
                    'location': current_location,
                    'location_info': location_info,
                    'description': 'Pre-trip vehicle inspection'
                })
                current_time += timedelta(hours=0.25)
                current_shift_on_duty += 0.25
                
                # Set work reporting location
                if work_reporting_location is None:
                    work_reporting_location = current_location
                
            elif leg['type'] == 'to_dropoff':
                # Pickup stop
                pickup_location_info = self._get_location_info(leg['start'])
                schedule.append({
                    'activity': 'Pickup',
                    'duty_status': 'on_duty_not_driving',
                    'duration_hours': self.PICKUP_DROPOFF_TIME,
                    'start_time': current_time,
                    'location': leg['start'],
                    'location_info': pickup_location_info,
                    'description': 'Loading at pickup location'
                })
                current_time += timedelta(hours=self.PICKUP_DROPOFF_TIME)
                current_shift_on_duty += self.PICKUP_DROPOFF_TIME
            
            # Drive this leg with breaks as needed
            while remaining_leg_distance > 0:
                # Update current location for tracking
                current_location = leg['start']
                location_info = self._get_location_info(current_location)
                
                # Check if we need a 30-minute break
                if current_continuous_driving >= self.BREAK_REQUIRED_AFTER:
                    schedule.append({
                        'activity': '30-Minute Break',
                        'duty_status': 'off_duty',
                        'duration_hours': self.MIN_BREAK_DURATION,
                        'start_time': current_time,
                        'location': current_location,
                        'location_info': location_info,
                        'description': 'Required 30-minute rest break'
                    })
                    current_time += timedelta(hours=self.MIN_BREAK_DURATION)
                    current_continuous_driving = 0
                
                # Determine if we can use 16-hour short-haul exception
                can_use_16hr_exception = (
                    self.short_haul_used_count == 0 and
                    work_reporting_location is not None and
                    consecutive_days_same_location >= 5
                )
                
                # Apply 16-hour exception if available
                max_on_duty_for_shift = self.MAX_ON_DUTY_TIME
                if can_use_16hr_exception:
                    max_on_duty_for_shift = self.SHORT_HAUL_EXTENSION_HOURS
                
                # Apply adverse conditions exception if active
                max_driving_for_shift = self.MAX_DRIVING_TIME
                if self.adverse_conditions_active:
                    max_driving_for_shift += self.ADVERSE_CONDITIONS_EXTENSION
                
                # Check if we need a rest break (with split sleeper berth option)
                needs_rest = (
                    current_shift_driving >= max_driving_for_shift or 
                    current_shift_on_duty >= max_on_duty_for_shift or
                    self.remaining_weekly_hours <= 0
                )
                
                if needs_rest:
                    # Check if 34-hour restart is beneficial
                    can_restart = self._check_34_hour_restart_benefit()
                    
                    if self.use_split_sleeper and pending_sleeper_segment is None:
                        # Use split sleeper berth - First segment (7 or 8 hours)
                        sleeper_duration = 7  # Can be 7 or 8
                        segment_id = f"sleeper_{len(schedule)}"
                        
                        schedule.append({
                            'activity': f'{sleeper_duration}-Hour Split Rest (Segment 1)',
                            'duty_status': 'sleeper_berth',
                            'duration_hours': sleeper_duration,
                            'start_time': current_time,
                            'location': current_location,
                            'location_info': location_info,
                            'description': f'Split sleeper berth - segment 1 of 2',
                            'rest_break_type': 'split_sleeper',
                            'sleeper_segment': 1,
                            'segment_id': segment_id,
                            'paired_with': None,  # Will be set when second segment is added
                            'excludes_from_14hr': True
                        })
                        current_time += timedelta(hours=sleeper_duration)
                        pending_sleeper_segment = segment_id
                        
                        # Partial reset - only driving time
                        current_shift_driving = 0
                        
                    elif self.use_split_sleeper and pending_sleeper_segment is not None:
                        # Use split sleeper berth - Second segment (3 or 2 hours)
                        sleeper_duration = 3  # Complement to first segment
                        segment_id = f"sleeper_{len(schedule)}"
                        
                        schedule.append({
                            'activity': f'{sleeper_duration}-Hour Split Rest (Segment 2)',
                            'duty_status': 'sleeper_berth',
                            'duration_hours': sleeper_duration,
                            'start_time': current_time,
                            'location': current_location,
                            'location_info': location_info,
                            'description': f'Split sleeper berth - segment 2 of 2',
                            'rest_break_type': 'split_sleeper',
                            'sleeper_segment': 2,
                            'segment_id': segment_id,
                            'paired_with': pending_sleeper_segment,
                            'excludes_from_14hr': True
                        })
                        current_time += timedelta(hours=sleeper_duration)
                        
                        # Link the segments
                        for item in schedule:
                            if item.get('segment_id') == pending_sleeper_segment:
                                item['paired_with'] = segment_id
                                break
                        
                        pending_sleeper_segment = None
                        
                        # Full reset after second segment
                        current_shift_driving = 0
                        current_shift_on_duty = 0
                        
                    elif can_restart:
                        # Use 34-hour restart
                        schedule.append({
                            'activity': '34-Hour Restart',
                            'duty_status': 'off_duty',
                            'duration_hours': self.RESTART_HOURS,
                            'start_time': current_time,
                            'location': current_location,
                            'location_info': location_info,
                            'description': '34-hour restart to reset weekly hours',
                            'rest_break_type': 'full_restart'
                        })
                        current_time += timedelta(hours=self.RESTART_HOURS)
                        
                        # Reset all counters
                        current_shift_driving = 0
                        current_shift_on_duty = 0
                        self.remaining_weekly_hours = self.max_weekly_hours
                        self.last_restart_time = current_time
                        
                    else:
                        # Standard 10-hour rest break
                        schedule.append({
                            'activity': '10-Hour Rest Break',
                            'duty_status': 'sleeper_berth',
                            'duration_hours': self.MIN_OFF_DUTY_TIME,
                            'start_time': current_time,
                            'location': current_location,
                            'location_info': location_info,
                            'description': 'Mandatory 10-hour rest period',
                            'rest_break_type': 'full_rest'
                        })
                        current_time += timedelta(hours=self.MIN_OFF_DUTY_TIME)
                        
                        # Reset shift counters
                        current_shift_driving = 0
                        current_shift_on_duty = 0
                        
                    # Reset 16-hour exception if used
                    if can_use_16hr_exception and current_shift_on_duty >= self.MAX_ON_DUTY_TIME:
                        self.short_haul_used_count += 1
                
                # Calculate how much we can drive
                hours_until_break = self.BREAK_REQUIRED_AFTER - current_continuous_driving
                hours_until_shift_limit = min(
                    self.MAX_DRIVING_TIME - current_shift_driving,
                    self.MAX_ON_DUTY_TIME - current_shift_on_duty
                )
                hours_can_drive = min(hours_until_break, hours_until_shift_limit)
                
                # Calculate distance until fueling
                distance_until_fuel = self.FUELING_INTERVAL - (total_distance_covered % self.FUELING_INTERVAL)
                hours_until_fuel = distance_until_fuel / self.AVERAGE_SPEED
                
                # Drive the minimum of: remaining distance, time until break, or time until fuel
                distance_can_drive = hours_can_drive * self.AVERAGE_SPEED
                drive_distance = min(remaining_leg_distance, distance_can_drive, distance_until_fuel)
                drive_hours = drive_distance / self.AVERAGE_SPEED
                
                # Add driving segment
                schedule.append({
                    'activity': 'Driving',
                    'duty_status': 'driving',
                    'duration_hours': drive_hours,
                    'distance_miles': drive_distance,
                    'start_time': current_time,
                    'location': leg['start'],
                    'description': f'Driving - {leg["description"]}'
                })
                
                current_time += timedelta(hours=drive_hours)
                current_shift_driving += drive_hours
                current_shift_on_duty += drive_hours
                current_continuous_driving += drive_hours
                total_distance_covered += drive_distance
                remaining_leg_distance -= drive_distance
                self.remaining_weekly_hours -= drive_hours
                
                # Check if we need to fuel
                if total_distance_covered % self.FUELING_INTERVAL < drive_distance:
                    schedule.append({
                        'activity': 'Fueling',
                        'duty_status': 'on_duty_not_driving',
                        'duration_hours': self.FUELING_TIME,
                        'start_time': current_time,
                        'location': leg['start'],
                        'description': 'Fueling stop'
                    })
                    current_time += timedelta(hours=self.FUELING_TIME)
                    current_shift_on_duty += self.FUELING_TIME
                    self.remaining_weekly_hours -= self.FUELING_TIME
            
            # Add dropoff time at end of last leg
            if leg_index == len(legs) - 1:
                schedule.append({
                    'activity': 'Dropoff',
                    'duty_status': 'on_duty_not_driving',
                    'duration_hours': self.PICKUP_DROPOFF_TIME,
                    'start_time': current_time,
                    'location': leg['end'],
                    'description': 'Unloading at dropoff location'
                })
                current_time += timedelta(hours=self.PICKUP_DROPOFF_TIME)
                
                # Post-trip inspection
                schedule.append({
                    'activity': 'Post-Trip Inspection',
                    'duty_status': 'on_duty_not_driving',
                    'duration_hours': 0.25,
                    'start_time': current_time,
                    'location': leg['end'],
                    'description': 'Post-trip vehicle inspection'
                })
                current_time += timedelta(hours=0.25)
        
        # Calculate cumulative time for each item
        cumulative_hours = 0
        for item in schedule:
            item['start_time_hours'] = cumulative_hours
            item['end_time_hours'] = cumulative_hours + item['duration_hours']
            cumulative_hours = item['end_time_hours']
        
        return schedule
    
    def _generate_daily_logs(self, schedule: List[Dict]) -> List[Dict]:
        """
        Generate daily log sheets from schedule
        
        Returns list of daily logs with proper ELD formatting
        """
        if not schedule:
            return []
        
        daily_logs = []
        current_log = None
        current_day_start = schedule[0]['start_time'].replace(hour=0, minute=0, second=0, microsecond=0)
        
        for item in schedule:
            item_date = item['start_time'].replace(hour=0, minute=0, second=0, microsecond=0)
            
            # Start new log if new day
            if current_log is None or item_date > current_day_start:
                if current_log:
                    daily_logs.append(current_log)
                
                current_day_start = item_date
                current_log = {
                    'date': current_day_start,
                    'activities': [],
                    'total_driving': 0,
                    'total_on_duty': 0,
                    'total_off_duty': 0,
                    'total_sleeper': 0,
                    'total_miles': 0
                }
            
            # Add activity to current log
            activity_entry = {
                'start_time': item['start_time'],
                'duration_hours': item['duration_hours'],
                'duty_status': item['duty_status'],
                'activity': item['activity'],
                'description': item.get('description', ''),
                'distance_miles': item.get('distance_miles', 0)
            }
            current_log['activities'].append(activity_entry)
            
            # Update totals
            if item['duty_status'] == 'driving':
                current_log['total_driving'] += item['duration_hours']
                current_log['total_on_duty'] += item['duration_hours']
                current_log['total_miles'] += item.get('distance_miles', 0)
            elif item['duty_status'] == 'on_duty_not_driving':
                current_log['total_on_duty'] += item['duration_hours']
            elif item['duty_status'] == 'off_duty':
                current_log['total_off_duty'] += item['duration_hours']
            elif item['duty_status'] == 'sleeper_berth':
                current_log['total_sleeper'] += item['duration_hours']
        
        # Add the last log
        if current_log:
            daily_logs.append(current_log)
        
        return daily_logs
    
    def _check_hos_compliance(self, schedule: List[Dict]) -> Dict:
        """
        Check if schedule complies with HOS regulations
        """
        violations = []
        
        # Check each shift
        shifts = []
        current_shift = {'driving': 0, 'on_duty': 0, 'start_time': None}
        
        for item in schedule:
            if item['duty_status'] in ['driving', 'on_duty_not_driving']:
                if current_shift['start_time'] is None:
                    current_shift['start_time'] = item['start_time']
                
                current_shift['on_duty'] += item['duration_hours']
                if item['duty_status'] == 'driving':
                    current_shift['driving'] += item['duration_hours']
            elif item['duty_status'] in ['sleeper_berth', 'off_duty']:
                if item['duration_hours'] >= self.MIN_OFF_DUTY_TIME:
                    if current_shift['start_time'] is not None:
                        shifts.append(current_shift)
                    current_shift = {'driving': 0, 'on_duty': 0, 'start_time': None}
        
        # Check for violations
        for i, shift in enumerate(shifts):
            if shift['driving'] > self.MAX_DRIVING_TIME:
                violations.append(f"Shift {i+1}: Exceeded 11-hour driving limit")
            if shift['on_duty'] > self.MAX_ON_DUTY_TIME:
                violations.append(f"Shift {i+1}: Exceeded 14-hour on-duty limit")
        
        return {
            'compliant': len(violations) == 0,
            'violations': violations,
            'total_shifts': len(shifts)
        }
    
    def _generate_summary(self, schedule: List[Dict], start_time: datetime) -> Dict:
        """
        Generate trip summary
        """
        total_driving = sum(item['duration_hours'] for item in schedule if item['duty_status'] == 'driving')
        total_on_duty = sum(item['duration_hours'] for item in schedule 
                           if item['duty_status'] in ['driving', 'on_duty_not_driving'])
        total_rest = sum(item['duration_hours'] for item in schedule 
                        if item['duty_status'] in ['off_duty', 'sleeper_berth'])
        
        end_time = start_time + timedelta(hours=schedule[-1]['end_time_hours'])
        
        return {
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'total_duration_hours': round(schedule[-1]['end_time_hours'], 1),
            'total_driving_hours': round(total_driving, 1),
            'total_on_duty_hours': round(total_on_duty, 1),
            'total_rest_hours': round(total_rest, 1),
            'number_of_stops': len([item for item in schedule if item['activity'] in ['Fueling', '30-Minute Break']]),
            'rest_breaks': len([item for item in schedule if '10-Hour Rest' in item['activity']]),
        }
    
    def _get_location_info(self, location: Dict[str, float]) -> Dict:
        """
        Get location information including city and state
        
        Args:
            location: Dictionary with 'lat' and 'lon'
            
        Returns:
            Dictionary with location details
        """
        if self.reverse_geocode_func:
            try:
                address = self.reverse_geocode_func(location['lat'], location['lon'])
                # Parse city, state from address
                parts = address.split(', ')
                city = parts[-2] if len(parts) >= 2 else 'Unknown'
                state = parts[-1] if len(parts) >= 1 else 'Unknown'
                
                return {
                    'city': city,
                    'state': state,
                    'coordinates': location,
                    'formatted_address': address
                }
            except Exception as e:
                print(f"Reverse geocoding error: {e}")
        
        return {
            'city': 'Unknown',
            'state': 'Unknown',
            'coordinates': location,
            'formatted_address': f"{location['lat']}, {location['lon']}"
        }
    
    def _check_34_hour_restart_benefit(self) -> bool:
        """
        Check if 34-hour restart would be beneficial
        
        Returns:
            True if restart would help, False otherwise
        """
        # Restart is beneficial if we have less than 14 hours remaining
        return self.remaining_weekly_hours < 14
    
    def calculate_rolling_hours(self, daily_hours_history: List[Dict]) -> Dict:
        """
        Calculate rolling 60/70-hour limits
        
        Args:
            daily_hours_history: List of {'date': str, 'on_duty_hours': float}
            
        Returns:
            Dictionary with hours available and breakdown
        """
        if not daily_hours_history:
            return {
                'hours_used': 0,
                'hours_available': self.max_weekly_hours,
                'mode': self.weekly_mode,
                'daily_breakdown': []
            }
        
        # Sort by date
        sorted_history = sorted(daily_hours_history, key=lambda x: x['date'])
        
        # Get last N days based on mode
        recent_history = sorted_history[-self.max_days:]
        
        # Calculate total hours
        total_hours = sum(day.get('on_duty_hours', 0) for day in recent_history)
        hours_available = max(0, self.max_weekly_hours - total_hours)
        
        return {
            'hours_used': round(total_hours, 1),
            'hours_available': round(hours_available, 1),
            'mode': self.weekly_mode,
            'daily_breakdown': [
                {
                    'date': day.get('date'),
                    'on_duty_hours': round(day.get('on_duty_hours', 0), 1)
                }
                for day in recent_history
            ]
        }
    
    def set_adverse_conditions(self, active: bool = True):
        """
        Activate or deactivate adverse driving conditions exception
        
        Args:
            active: Whether adverse conditions are active
        """
        self.adverse_conditions_active = active
    
    def set_air_mile_exception(self, active: bool = True):
        """
        Activate or deactivate 150 air-mile exception
        
        Args:
            active: Whether air-mile exception is active
        """
        self.air_mile_exception_active = active

