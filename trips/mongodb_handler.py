"""
MongoDB Database Handler
Manages trip data storage and retrieval
"""
from pymongo import MongoClient
from django.conf import settings
from datetime import datetime
from bson import ObjectId
from typing import Dict, List, Optional
import json


class MongoDBHandler:
    """
    Handler for MongoDB operations
    """
    
    def __init__(self):
        self.client = MongoClient(settings.MONGODB_URI)
        self.db = self.client[settings.MONGODB_DB_NAME]
        self.trips_collection = self.db['trips']
    
    def save_trip(self, trip_data: Dict) -> str:
        """
        Save trip to database
        
        Args:
            trip_data: Complete trip information
            
        Returns:
            Trip ID
        """
        trip_document = {
            'created_at': datetime.now(),
            'current_location': trip_data['current_location'],
            'pickup_location': trip_data['pickup_location'],
            'dropoff_location': trip_data['dropoff_location'],
            'current_cycle_used': trip_data['current_cycle_used'],
            'trip_plan': trip_data['trip_plan'],
            'driver_info': trip_data.get('driver_info', {}),
        }
        
        result = self.trips_collection.insert_one(trip_document)
        return str(result.inserted_id)
    
    def get_trip(self, trip_id: str) -> Optional[Dict]:
        """
        Retrieve trip by ID
        
        Args:
            trip_id: MongoDB ObjectId as string
            
        Returns:
            Trip data or None if not found
        """
        try:
            trip = self.trips_collection.find_one({'_id': ObjectId(trip_id)})
            if trip:
                trip['_id'] = str(trip['_id'])
                trip['created_at'] = trip['created_at'].isoformat()
                return trip
            return None
        except Exception as e:
            print(f"Error retrieving trip: {e}")
            return None
    
    def list_trips(self, limit: int = 20) -> List[Dict]:
        """
        List recent trips
        
        Args:
            limit: Maximum number of trips to return
            
        Returns:
            List of trip summaries
        """
        trips = self.trips_collection.find().sort('created_at', -1).limit(limit)
        
        result = []
        for trip in trips:
            result.append({
                '_id': str(trip['_id']),
                'created_at': trip['created_at'].isoformat(),
                'current_location': trip['current_location'],
                'pickup_location': trip['pickup_location'],
                'dropoff_location': trip['dropoff_location'],
                'total_distance': trip['trip_plan'].get('total_distance_miles', 0),
                'total_hours': trip['trip_plan'].get('estimated_total_hours', 0),
            })
        
        return result
    
    def list_trips_full(self, limit: int = 50) -> List[Dict]:
        """
        List recent trips with full details
        
        Args:
            limit: Maximum number of trips to return
            
        Returns:
            List of complete trip data
        """
        trips = self.trips_collection.find().sort('created_at', -1).limit(limit)
        
        result = []
        for trip in trips:
            trip['_id'] = str(trip['_id'])
            trip['created_at'] = trip['created_at'].isoformat()
            result.append(trip)
        
        return result
    
    def delete_trip(self, trip_id: str) -> bool:
        """
        Delete trip by ID
        
        Args:
            trip_id: MongoDB ObjectId as string
            
        Returns:
            True if deleted, False otherwise
        """
        try:
            result = self.trips_collection.delete_one({'_id': ObjectId(trip_id)})
            return result.deleted_count > 0
        except Exception as e:
            print(f"Error deleting trip: {e}")
            return False
    
    def close(self):
        """Close MongoDB connection"""
        self.client.close()
