"""
API Serializers for Trip data
"""
from rest_framework import serializers


class LocationSerializer(serializers.Serializer):
    """Serializer for location coordinates"""
    lat = serializers.FloatField()
    lon = serializers.FloatField()
    address = serializers.CharField(required=False, allow_blank=True, default="")


class TripPlanRequestSerializer(serializers.Serializer):
    """Serializer for trip planning request"""
    current_location = LocationSerializer()
    pickup_location = LocationSerializer()
    dropoff_location = LocationSerializer()
    current_cycle_used = serializers.FloatField(default=0, min_value=0, max_value=70)
    driver_name = serializers.CharField(max_length=100, default="John Doe")
    carrier_name = serializers.CharField(max_length=200, default="Example Carrier Inc.")
    main_office = serializers.CharField(max_length=200, default="123 Main St, City, ST")
    vehicle_number = serializers.CharField(max_length=50, default="TRUCK-001")
    
    # New HOS compliance fields
    weekly_mode = serializers.ChoiceField(choices=['70/8', '60/7'], default='70/8')
    use_split_sleeper = serializers.BooleanField(default=False)
    daily_hours_history = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        default=list
    )
    use_adverse_conditions = serializers.BooleanField(default=False)
    use_air_mile_exception = serializers.BooleanField(default=False)


class ActivitySerializer(serializers.Serializer):
    """Serializer for schedule activity"""
    activity = serializers.CharField()
    duty_status = serializers.CharField()
    duration_hours = serializers.FloatField()
    start_time = serializers.DateTimeField()
    description = serializers.CharField()
    distance_miles = serializers.FloatField(required=False)


class DailyLogSerializer(serializers.Serializer):
    """Serializer for daily log"""
    date = serializers.DateField()
    total_miles = serializers.FloatField()
    total_driving = serializers.FloatField()
    total_on_duty = serializers.FloatField()
    total_off_duty = serializers.FloatField()
    total_sleeper = serializers.FloatField()
    activities = ActivitySerializer(many=True)


class TripPlanResponseSerializer(serializers.Serializer):
    """Serializer for trip planning response"""
    trip_id = serializers.CharField()
    total_distance_miles = serializers.FloatField()
    total_driving_hours = serializers.FloatField()
    estimated_total_hours = serializers.FloatField()
    schedule = ActivitySerializer(many=True)
    daily_logs = DailyLogSerializer(many=True)
    hos_compliance = serializers.DictField()
    summary = serializers.DictField()
    route_data = serializers.DictField()
