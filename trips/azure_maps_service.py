"""
Azure Maps Integration Service
Handles routing and geocoding using Azure Maps API
"""
import requests
from django.conf import settings
from typing import Dict, List, Tuple
import math


class AzureMapsService:
    """
    Service for interacting with Azure Maps API
    """
    
    BASE_URL = "https://atlas.microsoft.com"
    
    def __init__(self):
        self.subscription_key = settings.AZURE_MAPS_SUBSCRIPTION_KEY
        self.client_id = settings.AZURE_MAPS_CLIENT_ID
        
    def calculate_route(self, 
                       waypoints: List[Dict[str, float]], 
                       ) -> Dict:
        """
        Calculate route between multiple waypoints
        
        Args:
            waypoints: List of {lat, lon} dictionaries
            
        Returns:
            Route information including distance, duration, and path
        """
        if len(waypoints) < 2:
            raise ValueError("At least 2 waypoints required")
        
        # Format waypoints for Azure Maps API
        coordinates = ":".join([f"{wp['lon']},{wp['lat']}" for wp in waypoints])
        
        url = f"{self.BASE_URL}/route/directions/json"
        params = {
            'api-version': '1.0',
            'subscription-key': self.subscription_key,
            'query': coordinates,
            'travelMode': 'truck',
            'vehicleWidth': '2.6',  # meters (typical truck width)
            'vehicleHeight': '4.0',  # meters (typical truck height)
            'vehicleLength': '20',  # meters (typical truck length)
            'vehicleWeight': '36000',  # kg (typical loaded truck weight)
            'computeBestOrder': 'false',
            'routeType': 'fastest',
            'traffic': 'true'
        }
        
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            return self._parse_route_response(data)
        except requests.exceptions.RequestException as e:
            print(f"Azure Maps API error: {e}")
            # Return fallback calculation based on straight-line distance
            return self._calculate_fallback_route(waypoints)
    
    def _parse_route_response(self, data: Dict) -> Dict:
        """
        Parse Azure Maps route response
        """
        if 'routes' not in data or len(data['routes']) == 0:
            raise ValueError("No routes found in response")
        
        route = data['routes'][0]
        summary = route['summary']
        
        # Convert meters to miles and seconds to hours
        distance_miles = summary['lengthInMeters'] * 0.000621371
        duration_hours = summary['travelTimeInSeconds'] / 3600
        
        # Extract leg information
        legs = []
        if 'legs' in route:
            for leg in route['legs']:
                leg_summary = leg['summary']
                legs.append({
                    'distance_miles': leg_summary['lengthInMeters'] * 0.000621371,
                    'duration_hours': leg_summary['travelTimeInSeconds'] / 3600,
                })
        
        # Extract route points for map display
        route_points = []
        if 'legs' in route:
            for leg in route['legs']:
                if 'points' in leg:
                    for point in leg['points']:
                        route_points.append({
                            'lat': point['latitude'],
                            'lon': point['longitude']
                        })
        
        return {
            'total_distance_miles': round(distance_miles, 1),
            'total_duration_hours': round(duration_hours, 1),
            'legs': legs,
            'route_points': route_points,
            'summary': summary
        }
    
    def _calculate_fallback_route(self, waypoints: List[Dict[str, float]]) -> Dict:
        """
        Calculate route using Haversine formula as fallback
        """
        total_distance = 0
        legs = []
        route_points = waypoints.copy()
        
        for i in range(len(waypoints) - 1):
            distance = self._haversine_distance(
                waypoints[i]['lat'], waypoints[i]['lon'],
                waypoints[i+1]['lat'], waypoints[i+1]['lon']
            )
            total_distance += distance
            
            # Estimate duration (assuming 55 mph average)
            duration = distance / 55
            
            legs.append({
                'distance_miles': round(distance, 1),
                'duration_hours': round(duration, 2)
            })
        
        total_duration = total_distance / 55
        
        return {
            'total_distance_miles': round(total_distance, 1),
            'total_duration_hours': round(total_duration, 1),
            'legs': legs,
            'route_points': route_points,
            'fallback': True
        }
    
    def _haversine_distance(self, lat1: float, lon1: float, 
                           lat2: float, lon2: float) -> float:
        """
        Calculate distance between two points using Haversine formula
        
        Returns distance in miles
        """
        R = 3959  # Earth's radius in miles
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        
        a = (math.sin(dlat / 2) ** 2 + 
             math.cos(lat1_rad) * math.cos(lat2_rad) * 
             math.sin(dlon / 2) ** 2)
        c = 2 * math.asin(math.sqrt(a))
        
        return R * c
    
    def geocode_address(self, address: str) -> Dict[str, float]:
        """
        Convert address to coordinates
        
        Args:
            address: Street address to geocode
            
        Returns:
            Dictionary with lat and lon
        """
        url = f"{self.BASE_URL}/search/address/json"
        params = {
            'api-version': '1.0',
            'subscription-key': self.subscription_key,
            'query': address,
            'limit': 1
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if 'results' in data and len(data['results']) > 0:
                position = data['results'][0]['position']
                return {
                    'lat': position['lat'],
                    'lon': position['lon']
                }
            else:
                raise ValueError(f"Could not geocode address: {address}")
        except requests.exceptions.RequestException as e:
            print(f"Geocoding error: {e}")
            raise ValueError(f"Could not geocode address: {address}")
    
    def reverse_geocode(self, lat: float, lon: float) -> str:
        """
        Convert coordinates to address
        
        Args:
            lat: Latitude
            lon: Longitude
            
        Returns:
            Formatted address string
        """
        url = f"{self.BASE_URL}/search/address/reverse/json"
        params = {
            'api-version': '1.0',
            'subscription-key': self.subscription_key,
            'query': f"{lat},{lon}"
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if 'addresses' in data and len(data['addresses']) > 0:
                address = data['addresses'][0]['address']
                parts = []
                if 'streetNumber' in address and 'streetName' in address:
                    parts.append(f"{address.get('streetNumber', '')} {address.get('streetName', '')}")
                if 'municipality' in address:
                    parts.append(address['municipality'])
                if 'countrySubdivision' in address:
                    parts.append(address['countrySubdivision'])
                return ', '.join(parts)
            else:
                return f"{lat}, {lon}"
        except requests.exceptions.RequestException as e:
            print(f"Reverse geocoding error: {e}")
            return f"{lat}, {lon}"
    
    def calculate_multi_leg_route(self,
                                  current_location: Dict[str, float],
                                  pickup_location: Dict[str, float],
                                  dropoff_location: Dict[str, float]) -> Dict:
        """
        Calculate route with separate legs
        
        Returns detailed route information for each leg
        """
        # Leg 1: Current to Pickup
        leg1 = self.calculate_route([current_location, pickup_location])
        
        # Leg 2: Pickup to Dropoff
        leg2 = self.calculate_route([pickup_location, dropoff_location])
        
        # Combine route points for full route visualization
        all_route_points = leg1.get('route_points', []) + leg2.get('route_points', [])
        
        return {
            'leg1': {
                'distance_miles': leg1['total_distance_miles'],
                'duration_hours': leg1['total_duration_hours'],
                'route_points': leg1.get('route_points', [])
            },
            'leg2': {
                'distance_miles': leg2['total_distance_miles'],
                'duration_hours': leg2['total_duration_hours'],
                'route_points': leg2.get('route_points', [])
            },
            'total_distance_miles': leg1['total_distance_miles'] + leg2['total_distance_miles'],
            'total_duration_hours': leg1['total_duration_hours'] + leg2['total_duration_hours'],
            'all_route_points': all_route_points
        }
