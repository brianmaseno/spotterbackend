"""
API Views for trip planning and ELD log generation
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.http import HttpResponse
from datetime import datetime
import traceback

from .serializers import TripPlanRequestSerializer, TripPlanResponseSerializer
from .hos_calculator import HOSCalculator
from .azure_maps_service import AzureMapsService
from .eld_log_generator import ELDLogGenerator
from .mongodb_handler import MongoDBHandler


class TripPlanView(APIView):
    """
    API endpoint for trip planning
    POST: Calculate trip plan with HOS compliance
    """
    
    def post(self, request):
        """
        Calculate trip plan
        
        Request body:
        {
            "current_location": {"lat": 37.7749, "lon": -122.4194},
            "pickup_location": {"lat": 38.5816, "lon": -121.4944},
            "dropoff_location": {"lat": 40.7128, "lon": -74.0060},
            "current_cycle_used": 15.5,
            "driver_name": "John Doe",
            "carrier_name": "Example Carrier",
            "main_office": "123 Main St, City, ST",
            "vehicle_number": "TRUCK-001"
        }
        """
        try:
            # Validate request
            serializer = TripPlanRequestSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(
                    {"error": "Invalid request data", "details": serializer.errors},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            data = serializer.validated_data
            
            # Initialize services
            azure_maps = AzureMapsService()
            hos_calculator = HOSCalculator(
                current_cycle_used=data['current_cycle_used']
            )
            
            # Calculate route
            route_data = azure_maps.calculate_multi_leg_route(
                current_location=data['current_location'],
                pickup_location=data['pickup_location'],
                dropoff_location=data['dropoff_location']
            )
            
            # Calculate trip plan with HOS compliance
            trip_plan = hos_calculator.calculate_trip_plan(
                current_location=data['current_location'],
                pickup_location=data['pickup_location'],
                dropoff_location=data['dropoff_location'],
                route_data=route_data,
                start_time=datetime.now()
            )
            
            # Save to database
            mongo = MongoDBHandler()
            trip_id = mongo.save_trip({
                'current_location': data['current_location'],
                'pickup_location': data['pickup_location'],
                'dropoff_location': data['dropoff_location'],
                'current_cycle_used': data['current_cycle_used'],
                'trip_plan': trip_plan,
                'driver_info': {
                    'driver_name': data['driver_name'],
                    'carrier_name': data['carrier_name'],
                    'main_office': data['main_office'],
                    'vehicle_number': data['vehicle_number'],
                }
            })
            mongo.close()
            
            # Format response
            response_data = {
                'trip_id': trip_id,
                'total_distance_miles': trip_plan['total_distance_miles'],
                'total_driving_hours': trip_plan['total_driving_hours'],
                'estimated_total_hours': trip_plan['estimated_total_hours'],
                'schedule': trip_plan['schedule'],
                'daily_logs': self._format_daily_logs(trip_plan['daily_logs']),
                'hos_compliance': trip_plan['hos_compliance'],
                'summary': trip_plan['summary'],
                'route_data': route_data
            }
            
            return Response(response_data, status=status.HTTP_200_OK)
            
        except Exception as e:
            print(f"Error in trip planning: {str(e)}")
            traceback.print_exc()
            return Response(
                {"error": "Failed to calculate trip plan", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _format_daily_logs(self, daily_logs):
        """Format daily logs for JSON response"""
        formatted_logs = []
        for log in daily_logs:
            formatted_log = {
                'date': log['date'].isoformat(),
                'total_miles': log['total_miles'],
                'total_driving': log['total_driving'],
                'total_on_duty': log['total_on_duty'],
                'total_off_duty': log['total_off_duty'],
                'total_sleeper': log['total_sleeper'],
                'activities': [
                    {
                        'start_time': activity['start_time'].isoformat(),
                        'duration_hours': activity['duration_hours'],
                        'duty_status': activity['duty_status'],
                        'activity': activity['activity'],
                        'description': activity['description'],
                        'distance_miles': activity.get('distance_miles', 0)
                    }
                    for activity in log['activities']
                ]
            }
            formatted_logs.append(formatted_log)
        return formatted_logs


class GenerateELDPDFView(APIView):
    """
    API endpoint to generate ELD logs as PDF
    GET: Generate PDF for a specific trip
    """
    
    def get(self, request, trip_id):
        """
        Generate ELD log PDF for trip
        
        URL: /api/trips/{trip_id}/eld-pdf/
        """
        try:
            # Retrieve trip from database
            mongo = MongoDBHandler()
            trip = mongo.get_trip(trip_id)
            mongo.close()
            
            if not trip:
                return Response(
                    {"error": "Trip not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Parse daily logs
            daily_logs = []
            for log in trip['trip_plan']['daily_logs']:
                parsed_log = {
                    'date': datetime.fromisoformat(log['date']),
                    'total_miles': log['total_miles'],
                    'total_driving': log['total_driving'],
                    'total_on_duty': log['total_on_duty'],
                    'total_off_duty': log['total_off_duty'],
                    'total_sleeper': log['total_sleeper'],
                    'activities': [
                        {
                            'start_time': datetime.fromisoformat(activity['start_time']),
                            'duration_hours': activity['duration_hours'],
                            'duty_status': activity['duty_status'],
                            'activity': activity['activity'],
                            'description': activity.get('description', ''),
                            'distance_miles': activity.get('distance_miles', 0)
                        }
                        for activity in log['activities']
                    ]
                }
                daily_logs.append(parsed_log)
            
            # Generate PDF
            eld_generator = ELDLogGenerator()
            pdf_bytes = eld_generator.generate_daily_logs(
                daily_logs=daily_logs,
                driver_info=trip.get('driver_info', {})
            )
            
            # Return PDF
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="eld_logs_{trip_id}.pdf"'
            return response
            
        except Exception as e:
            print(f"Error generating PDF: {str(e)}")
            traceback.print_exc()
            return Response(
                {"error": "Failed to generate PDF", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class TripDetailView(APIView):
    """
    API endpoint to retrieve trip details
    GET: Get trip by ID
    """
    
    def get(self, request, trip_id):
        """Get trip details"""
        try:
            mongo = MongoDBHandler()
            trip = mongo.get_trip(trip_id)
            mongo.close()
            
            if not trip:
                return Response(
                    {"error": "Trip not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            return Response(trip, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response(
                {"error": "Failed to retrieve trip", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class TripListView(APIView):
    """
    API endpoint to list trips
    GET: List recent trips
    """
    
    def get(self, request):
        """List recent trips"""
        try:
            mongo = MongoDBHandler()
            trips = mongo.list_trips(limit=20)
            mongo.close()
            
            return Response({"trips": trips}, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response(
                {"error": "Failed to retrieve trips", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class HealthCheckView(APIView):
    """
    Health check endpoint
    """
    
    def get(self, request):
        """Health check"""
        return Response({
            "status": "ok",
            "message": "ELD Trip Planning API is running"
        }, status=status.HTTP_200_OK)

