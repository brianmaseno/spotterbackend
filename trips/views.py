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
            
            # Parse daily logs with comprehensive error handling
            daily_logs = []
            print(f"Processing trip: {trip_id}")
            print(f"Trip has {len(trip['trip_plan']['daily_logs'])} daily logs")
            
            for idx, log in enumerate(trip['trip_plan']['daily_logs']):
                try:
                    print(f"\nProcessing log {idx + 1}")
                    print(f"Log keys: {log.keys()}")
                    
                    # Parse date - handle both string and datetime objects
                    date_value = log.get('date')
                    if date_value is None:
                        print("Warning: No date field found, using current date")
                        parsed_date = datetime.now()
                    elif isinstance(date_value, str):
                        # Try multiple date formats
                        try:
                            parsed_date = datetime.fromisoformat(date_value.replace('Z', '+00:00'))
                        except:
                            try:
                                parsed_date = datetime.strptime(date_value.split('T')[0], '%Y-%m-%d')
                            except:
                                print(f"Warning: Could not parse date '{date_value}', using current date")
                                parsed_date = datetime.now()
                    else:
                        parsed_date = date_value
                    
                    parsed_log = {
                        'date': parsed_date,
                        'total_miles': float(log.get('total_miles', 0)),
                        'total_driving': float(log.get('total_driving', 0)),
                        'total_on_duty': float(log.get('total_on_duty', 0)),
                        'total_off_duty': float(log.get('total_off_duty', 0)),
                        'total_sleeper': float(log.get('total_sleeper', 0)),
                        'activities': []
                    }
                    
                    # Parse activities
                    activities = log.get('activities', [])
                    print(f"Processing {len(activities)} activities")
                    
                    for act_idx, activity in enumerate(activities):
                        try:
                            start_time_value = activity.get('start_time')
                            if start_time_value is None:
                                print(f"Warning: Activity {act_idx} has no start_time")
                                activity_start_time = parsed_date
                            elif isinstance(start_time_value, str):
                                try:
                                    activity_start_time = datetime.fromisoformat(start_time_value.replace('Z', '+00:00'))
                                except:
                                    print(f"Warning: Could not parse activity start_time '{start_time_value}'")
                                    activity_start_time = parsed_date
                            else:
                                activity_start_time = start_time_value
                            
                            parsed_log['activities'].append({
                                'start_time': activity_start_time,
                                'duration_hours': float(activity.get('duration_hours', 0)),
                                'duty_status': activity.get('duty_status', 'off_duty'),
                                'activity': activity.get('activity', 'Unknown'),
                                'description': activity.get('description', ''),
                                'distance_miles': float(activity.get('distance_miles', 0))
                            })
                        except Exception as e:
                            print(f"Error parsing activity {act_idx}: {e}")
                            continue
                    
                    daily_logs.append(parsed_log)
                    print(f"Successfully parsed log {idx + 1}")
                    
                except Exception as e:
                    print(f"Error parsing log {idx + 1}: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
            
            print(f"\nSuccessfully parsed {len(daily_logs)} logs")
            
            if len(daily_logs) == 0:
                return Response(
                    {"error": "No valid daily logs found for this trip"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Generate PDF
            print("Generating PDF...")
            eld_generator = ELDLogGenerator()
            pdf_bytes = eld_generator.generate_daily_logs(
                daily_logs=daily_logs,
                driver_info=trip.get('driver_info', {})
            )
            print(f"PDF generated successfully: {len(pdf_bytes)} bytes")
            
            # Return PDF
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="eld_logs_{trip_id}.pdf"'
            return response
            
        except Exception as e:
            print(f"Error generating PDF: {str(e)}")
            print(f"Error type: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            return Response(
                {"error": "Failed to generate PDF", "details": str(e), "type": type(e).__name__},
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
        """List recent trips with full details"""
        try:
            limit = int(request.GET.get('limit', 50))
            mongo = MongoDBHandler()
            trips = mongo.list_trips_full(limit=limit)
            mongo.close()
            
            return Response({"trips": trips}, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response(
                {"error": "Failed to retrieve trips", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class TripDeleteView(APIView):
    """
    API endpoint to delete a trip
    DELETE: Delete trip by ID
    """
    
    def delete(self, request, trip_id):
        """Delete a trip"""
        try:
            mongo = MongoDBHandler()
            deleted = mongo.delete_trip(trip_id)
            mongo.close()
            
            if not deleted:
                return Response(
                    {"error": "Trip not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            return Response(
                {"message": "Trip deleted successfully"},
                status=status.HTTP_200_OK
            )
            
        except Exception as e:
            return Response(
                {"error": "Failed to delete trip", "details": str(e)},
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

