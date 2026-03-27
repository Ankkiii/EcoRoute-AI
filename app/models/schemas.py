"""
Pydantic models for request validation and response serialization.

This module defines the data models used for API request validation,
including input sanitization and range checking.
"""

import re
from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, List


class EmissionRequest(BaseModel):
    """
    Request model for emission calculation endpoint.
    
    Validates vehicle number and distance with sanitization and range checking.
    
    Requirements: 2.1, 2.2, 2.3, 2.4, 2.6, 13.1, 13.3, 13.4
    
    Example:
        ```json
        {
            "vehicle_no": "BMW 320i",
            "distance_km": 50.5
        }
        ```
    """
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "vehicle_no": "BMW 320i",
                    "distance_km": 50.5
                },
                {
                    "vehicle_no": "Honda Civic",
                    "distance_km": 120.0
                }
            ]
        }
    )
    
    vehicle_no: str = Field(
        ..., 
        min_length=1, 
        max_length=50, 
        description="Vehicle make and model (e.g., BMW 320i, Honda Civic)",
        examples=["BMW 320i", "Honda Civic", "Toyota Camry"]
    )
    distance_km: float = Field(
        ..., 
        gt=0, 
        le=10000, 
        description="Distance in kilometers (must be positive and <= 10000)",
        examples=[50.5, 120.0, 250.75]
    )
    
    @field_validator('vehicle_no')
    @classmethod
    def sanitize_vehicle_no(cls, v):
        """
        Sanitize and normalize vehicle make/model.
        
        - Trims whitespace
        - Converts to uppercase
        - Collapses multiple spaces to single space
        
        Requirements: 2.5, 13.3, 13.4
        """
        # Trim whitespace and collapse multiple spaces to single space
        v = ' '.join(v.strip().split())
        
        # Convert to uppercase for case-insensitive matching
        return v.upper()


class RouteRequest(BaseModel):
    """
    Request model for eco-route recommendation endpoint.
    
    Validates vehicle number, source, and destination with sanitization.
    
    Requirements: 2.1, 2.3, 2.4, 13.1, 13.3, 13.4
    
    Example:
        ```json
        {
            "vehicle_no": "MH01AB1234",
            "source": "Mumbai, Maharashtra",
            "destination": "Pune, Maharashtra"
        }
        ```
    """
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "vehicle_no": "MH01AB1234",
                    "source": "Mumbai, Maharashtra",
                    "destination": "Pune, Maharashtra"
                },
                {
                    "vehicle_no": "DL02CD5678",
                    "source": "New Delhi",
                    "destination": "Agra, Uttar Pradesh"
                }
            ]
        }
    )
    
    vehicle_no: str = Field(
        ..., 
        min_length=1, 
        max_length=50, 
        description="Vehicle identification number (e.g., MH01AB1234)",
        examples=["MH01AB1234", "DL02CD5678"]
    )
    source: str = Field(
        ..., 
        min_length=1, 
        max_length=500, 
        description="Source location (city, state, or full address)",
        examples=["Mumbai, Maharashtra", "New Delhi", "Bangalore, Karnataka"]
    )
    destination: str = Field(
        ..., 
        min_length=1, 
        max_length=500, 
        description="Destination location (city, state, or full address)",
        examples=["Pune, Maharashtra", "Agra, Uttar Pradesh", "Chennai, Tamil Nadu"]
    )
    fuel_price_per_litre: Optional[float] = Field(
        default=None,
        gt=0,
        description="Optional fuel price per litre for cost estimation",
        examples=[1.50, 2.10]
    )
    
    @field_validator('vehicle_no')
    @classmethod
    def sanitize_vehicle_no(cls, v):
        """
        Sanitize and normalize vehicle make/model.
        
        - Trims whitespace
        - Converts to uppercase
        - Collapses multiple spaces to single space
        
        Requirements: 2.5, 13.3, 13.4
        """
        # Trim whitespace and collapse multiple spaces to single space
        v = ' '.join(v.strip().split())
        
        # Convert to uppercase for case-insensitive matching
        return v.upper()
    
    @field_validator('source', 'destination')
    @classmethod
    def sanitize_location(cls, v):
        """
        Sanitize location strings.
        
        - Trims whitespace
        - Removes control characters
        - Validates not empty after trimming
        
        Requirements: 2.3, 2.5
        """
        # Trim whitespace
        v = v.strip()
        
        # Check if empty after trimming
        if not v:
            raise ValueError("Location cannot be empty")
        
        # Remove control characters - keep only printable characters
        v = ''.join(char for char in v if char.isprintable())
        
        return v



class VehicleResponse(BaseModel):
    """
    Response model for vehicle lookup endpoint.
    
    Returns vehicle specifications from the database.
    
    Example:
        ```json
        {
            "vehicle_no": "MH01AB1234",
            "type": "Sedan",
            "fuel": "Petrol",
            "engine_size": 1.5,
            "mileage": 18.5
        }
        ```
    """
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "vehicle_no": "MH01AB1234",
                    "type": "Sedan",
                    "fuel": "Petrol",
                    "engine_size": 1.5,
                    "mileage": 18.5
                }
            ]
        }
    )
    
    vehicle_no: str = Field(..., description="Vehicle identification number")
    type: str = Field(..., description="Vehicle type (SUV, Sedan, or Hatchback)")
    fuel: str = Field(..., description="Fuel type (Petrol, Diesel, or CNG)")
    engine_size: float = Field(..., description="Engine size in liters")
    mileage: float = Field(..., description="Fuel efficiency in km/l")


class EmissionResponse(BaseModel):
    """
    Response model for emission calculation endpoint.
    
    Returns predicted CO₂ emission for the given vehicle and distance.
    
    Example:
        ```json
        {
            "vehicle_no": "MH01AB1234",
            "distance_km": 50.5,
            "predicted_co2_kg": 12.34,
            "model_used": "RandomForest Regression"
        }
        ```
    """
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "vehicle_no": "MH01AB1234",
                    "distance_km": 50.5,
                    "predicted_co2_kg": 12.34,
                    "model_used": "RandomForest Regression"
                }
            ]
        }
    )
    
    vehicle_no: str = Field(..., description="Vehicle identification number")
    distance_km: float = Field(..., description="Distance in kilometers")
    predicted_co2_kg: float = Field(..., description="Predicted CO₂ emission in kilograms")
    model_used: str = Field(default="RandomForest Regression", description="ML model used for prediction")


class RouteInfo(BaseModel):
    """
    Model representing a single route with emission prediction.
    
    Example:
        ```json
        {
            "route_number": 1,
            "distance_km": 148.5,
            "duration_minutes": 165.3,
            "traffic_level": "Medium",
            "predicted_co2_kg": 28.45,
            "summary": "Via Mumbai-Pune Expressway"
        }
        ```
    """
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "route_number": 1,
                    "distance_km": 148.5,
                    "duration_minutes": 165.3,
                    "traffic_level": "Medium",
                    "predicted_co2_kg": 28.45,
                    "summary": "Via Mumbai-Pune Expressway"
                }
            ]
        }
    )
    
    route_number: int = Field(..., description="Sequential route identifier")
    distance_km: float = Field(..., description="Route distance in kilometers")
    duration_minutes: float = Field(..., description="Expected duration in minutes")
    traffic_level: str = Field(..., description="Traffic level (Low, Medium, or High)")
    predicted_co2_kg: float = Field(..., description="Predicted CO₂ emission in kilograms")
    summary: str = Field(..., description="Route description or highway name")
    fuel_cost_estimate: Optional[float] = Field(default=None, description="Estimated fuel cost in the provided currency")


class EcoRouteResponse(BaseModel):
    """
    Response model for eco-route recommendation endpoint.
    
    Returns the recommended route with lowest emissions and all alternatives.
    
    Example:
        ```json
        {
            "source": "Mumbai, Maharashtra",
            "destination": "Pune, Maharashtra",
            "vehicle_no": "MH01AB1234",
            "recommended_route": {
                "route_number": 1,
                "distance_km": 148.5,
                "duration_minutes": 165.3,
                "traffic_level": "Medium",
                "predicted_co2_kg": 28.45,
                "summary": "Via Mumbai-Pune Expressway"
            },
            "all_routes": [...],
            "selection_criteria": "Minimum CO2 Emission (ML Predicted)",
            "emission_savings_kg": 0.67,
            "emission_savings_percent": 2.3
        }
        ```
    """
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "source": "Mumbai, Maharashtra",
                    "destination": "Pune, Maharashtra",
                    "vehicle_no": "MH01AB1234",
                    "recommended_route": {
                        "route_number": 1,
                        "distance_km": 148.5,
                        "duration_minutes": 165.3,
                        "traffic_level": "Medium",
                        "predicted_co2_kg": 28.45,
                        "summary": "Via Mumbai-Pune Expressway"
                    },
                    "all_routes": [
                        {
                            "route_number": 1,
                            "distance_km": 148.5,
                            "duration_minutes": 165.3,
                            "traffic_level": "Medium",
                            "predicted_co2_kg": 28.45,
                            "summary": "Via Mumbai-Pune Expressway"
                        },
                        {
                            "route_number": 2,
                            "distance_km": 162.0,
                            "duration_minutes": 180.0,
                            "traffic_level": "Low",
                            "predicted_co2_kg": 29.12,
                            "summary": "Via NH48"
                        }
                    ],
                    "selection_criteria": "Minimum CO2 Emission (ML Predicted)",
                    "emission_savings_kg": 0.67,
                    "emission_savings_percent": 2.3
                }
            ]
        }
    )
    
    source: str = Field(..., description="Source location")
    destination: str = Field(..., description="Destination location")
    vehicle_no: str = Field(..., description="Vehicle identification number")
    recommended_route: RouteInfo = Field(..., description="Route with lowest predicted emissions")
    all_routes: List[RouteInfo] = Field(..., description="All available route alternatives")
    selection_criteria: str = Field(..., description="Criteria used for route selection")
    emission_savings_kg: float = Field(..., description="Emission savings compared to worst route (kg)")
    emission_savings_percent: float = Field(..., description="Emission savings as percentage")


class ComponentStatus(BaseModel):
    """Model for individual component health status."""
    database: str = Field(..., description="Vehicle database status")
    ml_model: str = Field(..., description="ML model status")
    maps_api: str = Field(..., description="Google Maps API configuration status")


class HealthResponse(BaseModel):
    """
    Response model for health check endpoint.
    
    Returns system health status and component information.
    
    Example:
        ```json
        {
            "status": "healthy",
            "timestamp": "2024-01-15T10:30:00Z",
            "version": "1.0.0",
            "components": {
                "database": "loaded",
                "ml_model": "loaded",
                "maps_api": "configured"
            }
        }
        ```
    """
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "healthy",
                    "timestamp": "2024-01-15T10:30:00.000Z",
                    "version": "1.0.0",
                    "components": {
                        "database": "loaded",
                        "ml_model": "loaded",
                        "maps_api": "configured"
                    }
                }
            ]
        }
    )
    
    status: str = Field(..., description="Overall system status (healthy or unhealthy)")
    timestamp: str = Field(..., description="ISO 8601 timestamp of health check")
    version: str = Field(..., description="Application version")
    components: ComponentStatus = Field(..., description="Individual component statuses")


class ErrorResponse(BaseModel):
    """
    Standard error response model.
    
    Used for all error responses across the API.
    
    Example:
        ```json
        {
            "detail": "Vehicle not found",
            "error_code": "VEHICLE_NOT_FOUND",
            "suggestions": [
                "Check vehicle number format",
                "Example formats: MH01AB1234, DL02CD5678"
            ],
            "timestamp": "2024-01-15T10:30:00Z"
        }
        ```
    """
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "detail": "Vehicle not found",
                    "error_code": "VEHICLE_NOT_FOUND",
                    "suggestions": [
                        "Check vehicle number format",
                        "Example formats: MH01AB1234, DL02CD5678"
                    ],
                    "timestamp": "2024-01-15T10:30:00.000Z"
                },
                {
                    "detail": "Input validation failed",
                    "error_code": "VALIDATION_ERROR",
                    "errors": [
                        {
                            "field": "distance_km",
                            "message": "ensure this value is greater than 0",
                            "type": "value_error"
                        }
                    ],
                    "timestamp": "2024-01-15T10:30:00.000Z"
                }
            ]
        }
    )
    
    detail: str = Field(..., description="Human-readable error message")
    error_code: Optional[str] = Field(None, description="Machine-readable error code")
    suggestions: Optional[List[str]] = Field(None, description="Helpful suggestions for resolving the error")
    errors: Optional[List[dict]] = Field(None, description="Detailed validation errors (for validation failures)")
    timestamp: str = Field(..., description="ISO 8601 timestamp of error occurrence")
