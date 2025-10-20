"""
URL Configuration for trips app
"""
from django.urls import path
from .views import (
    TripPlanView,
    GenerateELDPDFView,
    TripDetailView,
    TripListView,
    HealthCheckView
)

urlpatterns = [
    path('plan/', TripPlanView.as_view(), name='trip-plan'),
    path('<str:trip_id>/', TripDetailView.as_view(), name='trip-detail'),
    path('<str:trip_id>/eld-pdf/', GenerateELDPDFView.as_view(), name='generate-eld-pdf'),
    path('', TripListView.as_view(), name='trip-list'),
]
