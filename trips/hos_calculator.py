"""
Hours of Service (HOS) Calculator
Based on FMCSA regulations for property-carrying CMV drivers
"""
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
import math


class HOSCalculator:
    """
    Calculate Hours of Service compliance for truck drivers
    Following 70hrs/8days rule for property-carrying drivers
    """
    
    # HOS Limits (in hours)
    MAX_DRIVING_TIME = 11  # Maximum driving time per shift
    MAX_ON_DUTY_TIME = 14  # Maximum on-duty window
    MAX_WEEKLY_HOURS = 70  # 70 hours in 8 days
    MAX_DAYS = 8
    MIN_OFF_DUTY_TIME = 10  # Minimum consecutive off-duty time
    BREAK_REQUIRED_AFTER = 8  # Hours of driving before break required
    MIN_BREAK_DURATION = 0.5  # 30 minutes break
    
    # Operational constants
    AVERAGE_SPEED = 60  # mph (accounting for stops, traffic, etc.)
    FUELING_TIME = 0.5  # 30 minutes for fueling
    PICKUP_DROPOFF_TIME = 1.0  # 1 hour for pickup/dropoff
    FUELING_INTERVAL = 1000  # miles between fueling stops
    
    def __init__(self, current_cycle_used: float = 0):
        """
        Initialize HOS Calculator
        
        Args:
            current_cycle_used: Hours already used in current 8-day cycle
        """
        self.current_cycle_used = current_cycle_used
        self.remaining_weekly_hours = self.MAX_WEEKLY_HOURS - current_cycle_used
        
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
        
        for leg_index, leg in enumerate(legs):
            leg_distance = leg['distance_miles']
            remaining_leg_distance = leg_distance
            
            # Add pickup/dropoff time at start of leg
            if leg['type'] == 'to_pickup':
                # Start of trip - pre-trip inspection
                schedule.append({
                    'activity': 'Pre-Trip Inspection',
                    'duty_status': 'on_duty_not_driving',
                    'duration_hours': 0.25,
                    'start_time': current_time,
                    'location': leg['start'],
                    'description': 'Pre-trip vehicle inspection'
                })
                current_time += timedelta(hours=0.25)
                current_shift_on_duty += 0.25
                
            elif leg['type'] == 'to_dropoff':
                # Pickup stop
                schedule.append({
                    'activity': 'Pickup',
                    'duty_status': 'on_duty_not_driving',
                    'duration_hours': self.PICKUP_DROPOFF_TIME,
                    'start_time': current_time,
                    'location': leg['start'],
                    'description': 'Loading at pickup location'
                })
                current_time += timedelta(hours=self.PICKUP_DROPOFF_TIME)
                current_shift_on_duty += self.PICKUP_DROPOFF_TIME
            
            # Drive this leg with breaks as needed
            while remaining_leg_distance > 0:
                # Check if we need a 30-minute break
                if current_continuous_driving >= self.BREAK_REQUIRED_AFTER:
                    schedule.append({
                        'activity': '30-Minute Break',
                        'duty_status': 'off_duty',
                        'duration_hours': self.MIN_BREAK_DURATION,
                        'start_time': current_time,
                        'location': leg['start'],
                        'description': 'Required 30-minute rest break'
                    })
                    current_time += timedelta(hours=self.MIN_BREAK_DURATION)
                    current_continuous_driving = 0
                
                # Check if we need a 10-hour rest break
                if (current_shift_driving >= self.MAX_DRIVING_TIME or 
                    current_shift_on_duty >= self.MAX_ON_DUTY_TIME or
                    self.remaining_weekly_hours <= 0):
                    
                    schedule.append({
                        'activity': '10-Hour Rest Break',
                        'duty_status': 'sleeper_berth',
                        'duration_hours': self.MIN_OFF_DUTY_TIME,
                        'start_time': current_time,
                        'location': leg['start'],
                        'description': 'Mandatory 10-hour rest period'
                    })
                    current_time += timedelta(hours=self.MIN_OFF_DUTY_TIME)
                    
                    # Reset shift counters
                    current_shift_driving = 0
                    current_shift_on_duty = 0
                    self.remaining_weekly_hours = min(
                        self.MAX_WEEKLY_HOURS, 
                        self.remaining_weekly_hours + self.MIN_OFF_DUTY_TIME
                    )
                
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
