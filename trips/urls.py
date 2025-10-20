"""
URL Configuration for trips app
"""
from django.urls import path
from .views import (
    TripPlanView,
    GenerateELDPDFView,
    TripDetailView,
    TripListView,
    TripDeleteView,
    HealthCheckView
)

urlpatterns = [
    path('plan/', TripPlanView.as_view(), name='trip-plan'),
    path('list/', TripListView.as_view(), name='trip-list'),
    path('<str:trip_id>/', TripDetailView.as_view(), name='trip-detail'),
    path('<str:trip_id>/delete/', TripDeleteView.as_view(), name='trip-delete'),
    path('<str:trip_id>/eld-pdf/', GenerateELDPDFView.as_view(), name='generate-eld-pdf'),
]
