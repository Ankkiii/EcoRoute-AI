from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse, FileResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from pydantic import BaseModel
import pandas as pd
import requests
import pickle
from datetime import datetime
from app.config import get_settings, validate_startup_config
from app.services.traffic_analyzer import TrafficAnalyzer
from app.services.vehicle_manager import VehicleManager
from app.models.schemas import EmissionRequest, RouteRequest
from app.core.exceptions import (
    VehicleEmissionError,
    ConfigurationError,
    ValidationError,
    VehicleNotFoundError,
    MapsAPIError,
    MapsAPITimeoutError,
    MapsAPIAuthError,
    NoRoutesFoundError,
    ModelLoadError,
    DatabaseLoadError
)

# Load configuration
settings = get_settings()

# Validate configuration at startup
validate_startup_config(settings)

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="EcoRoute AI",
    version="1.0.0",
    openapi_tags=[
        {
            "name": "System",
            "description": "System health and status endpoints"
        },
        {
            "name": "Vehicles",
            "description": "Vehicle lookup and information"
        },
        {
            "name": "Emissions",
            "description": "CO₂ emission calculations"
        },
        {
            "name": "Routes",
            "description": "Eco-friendly route recommendations"
        }
    ]
)

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Mount static files directory
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# -----------------------------
# CORS MIDDLEWARE
# -----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)

# -----------------------------
# SECURITY HEADERS MIDDLEWARE
# -----------------------------
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses"""
    response = await call_next(request)
    
    # Add security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    
    # CSP with Swagger UI support
    csp = (
        "default-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
        "font-src 'self' https://fonts.gstatic.com; "
        "script-src 'self' 'unsafe-inline' https://maps.googleapis.com https://cdn.jsdelivr.net; "
        "img-src 'self' data: https://*.googleapis.com https://*.gstatic.com https://fastapi.tiangolo.com; "
        "connect-src 'self' https://maps.googleapis.com https://cdn.jsdelivr.net"
    )
    response.headers["Content-Security-Policy"] = csp
    
    return response

# -----------------------------
# CONTENT TYPE VALIDATION MIDDLEWARE
# -----------------------------
@app.middleware("http")
async def validate_content_type(request: Request, call_next):
    """Validate content type for POST requests"""
    if request.method == "POST":
        content_type = request.headers.get("content-type", "")
        if not content_type.startswith("application/json"):
            return JSONResponse(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                content={
                    "detail": "Content-Type must be application/json for POST requests",
                    "error_code": "INVALID_CONTENT_TYPE",
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
    
    response = await call_next(request)
    return response

# -----------------------------
# EXCEPTION HANDLERS
# -----------------------------

@app.exception_handler(VehicleNotFoundError)
async def vehicle_not_found_handler(request: Request, exc: VehicleNotFoundError):
    """Handle vehicle not found errors."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "detail": exc.message,
            "error_code": exc.error_code,
            "suggestions": exc.suggestions or [
                "Check vehicle make and model format",
                "Example formats: BMW 320i, Honda Civic, Toyota Camry"
            ],
            "timestamp": datetime.utcnow().isoformat()
        }
    )


@app.exception_handler(MapsAPITimeoutError)
async def maps_timeout_handler(request: Request, exc: MapsAPITimeoutError):
    """Handle Maps API timeout errors."""
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "detail": exc.message,
            "error_code": exc.error_code,
            "timestamp": datetime.utcnow().isoformat()
        }
    )


@app.exception_handler(MapsAPIAuthError)
async def maps_auth_handler(request: Request, exc: MapsAPIAuthError):
    """Handle Maps API authentication errors."""
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "detail": "Maps service authentication failed. Please contact support.",
            "error_code": exc.error_code,
            "timestamp": datetime.utcnow().isoformat()
        }
    )


@app.exception_handler(MapsAPIError)
async def maps_api_handler(request: Request, exc: MapsAPIError):
    """Handle general Maps API errors."""
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "detail": exc.message,
            "error_code": exc.error_code,
            "timestamp": datetime.utcnow().isoformat()
        }
    )


@app.exception_handler(NoRoutesFoundError)
async def no_routes_handler(request: Request, exc: NoRoutesFoundError):
    """Handle no routes found errors."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "detail": exc.message,
            "error_code": exc.error_code,
            "suggestions": [
                "Check spelling of location names",
                "Try using more specific addresses",
                "Ensure locations are accessible by road"
            ],
            "timestamp": datetime.utcnow().isoformat()
        }
    )


@app.exception_handler(ConfigurationError)
async def configuration_error_handler(request: Request, exc: ConfigurationError):
    """Handle configuration errors."""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": exc.message,
            "error_code": exc.error_code,
            "timestamp": datetime.utcnow().isoformat()
        }
    )


@app.exception_handler(ValidationError)
async def validation_error_handler(request: Request, exc: ValidationError):
    """Handle custom validation errors."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": exc.message,
            "error_code": exc.error_code,
            "timestamp": datetime.utcnow().isoformat()
        }
    )


@app.exception_handler(ModelLoadError)
async def model_load_error_handler(request: Request, exc: ModelLoadError):
    """Handle ML model loading errors."""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": exc.message,
            "error_code": exc.error_code,
            "timestamp": datetime.utcnow().isoformat()
        }
    )


@app.exception_handler(DatabaseLoadError)
async def database_load_error_handler(request: Request, exc: DatabaseLoadError):
    """Handle database loading errors."""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": exc.message,
            "error_code": exc.error_code,
            "timestamp": datetime.utcnow().isoformat()
        }
    )


@app.exception_handler(RequestValidationError)
async def pydantic_validation_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors."""
    errors = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"])
        errors.append({
            "field": field,
            "message": error["msg"],
            "type": error["type"]
        })
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Input validation failed",
            "error_code": "VALIDATION_ERROR",
            "errors": errors,
            "timestamp": datetime.utcnow().isoformat()
        }
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Handle all other exceptions with production error sanitization."""
    # Sanitize error message for production
    if settings.environment == "production":
        detail = "An internal error occurred. Please try again later."
    else:
        detail = str(exc)
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": detail,
            "error_code": "INTERNAL_ERROR",
            "timestamp": datetime.utcnow().isoformat()
        }
    )

# -----------------------------
# LOAD VEHICLE DATABASE
# -----------------------------
vehicle_manager = VehicleManager(settings.vehicle_database_path)
vehicle_manager.load()

# -----------------------------
# LOAD ML MODEL
# -----------------------------
with open(settings.model_path, "rb") as f:
    emission_model = pickle.load(f)

with open(settings.model_columns_path, "rb") as f:
    model_columns = pickle.load(f)

# -----------------------------
# GOOGLE MAPS API KEY
# -----------------------------
GOOGLE_MAPS_API_KEY = settings.google_maps_api_key


# -----------------------------
# ML PREDICTION FUNCTION
# -----------------------------
def predict_emission(vehicle, distance_km, traffic_level):
    """
    Predict CO2 emission using hybrid approach: ML model + traffic adjustment.
    
    Uses ML model to predict base emission rate per km based on vehicle specs,
    then applies traffic multiplier for real-world conditions.
    
    Args:
        vehicle: Vehicle data dictionary with specs
        distance_km: Distance in kilometers
        traffic_level: Traffic level (1=Low, 2=Medium, 3=High)
        
    Returns:
        float: Predicted CO2 emission in kg
    """
    try:
        # Prepare features for ML model
        input_data = {}
        
        # Basic features
        input_data["Engine_size_L"] = float(vehicle.get("engine_size", 2.0))
        
        # Estimate cylinders from engine size (rough approximation)
        engine_size = float(vehicle.get("engine_size", 2.0))
        if engine_size < 1.5:
            cylinders = 3
        elif engine_size < 2.5:
            cylinders = 4
        elif engine_size < 4.0:
            cylinders = 6
        else:
            cylinders = 8
        input_data["Cylinders"] = cylinders
        
        # Engineered features
        mileage = float(vehicle.get("mileage", 15.0))
        input_data["fuel_efficiency_score"] = mileage * 10  # Scale up
        input_data["engine_displacement_per_cylinder"] = engine_size / cylinders
        input_data["estimated_weight"] = 1000 + (engine_size * 200)  # Rough estimate
        input_data["power_to_weight_ratio"] = (engine_size * 50) / input_data["estimated_weight"]
        input_data["city_highway_diff"] = 2.0  # Average difference
        input_data["engine_efficiency"] = mileage / engine_size if engine_size > 0 else 10
        input_data["cylinder_efficiency"] = mileage / cylinders if cylinders > 0 else 5
        
        # One-hot encode Make (use vehicle make if available)
        make = vehicle.get("make", "Unknown")
        input_data[f"Make_{make}"] = 1
        
        # One-hot encode Model (use vehicle model if available)
        model_name = vehicle.get("model", "Unknown")
        input_data[f"Model_{model_name}"] = 1
        
        # One-hot encode Vehicle class
        vehicle_class = vehicle.get("type", "Car")
        input_data[f"Vehicle_class_{vehicle_class}"] = 1
        
        # One-hot encode Fuel type
        fuel_type = vehicle.get("fuel", "Petrol")
        # Map fuel types to dataset format
        fuel_map = {"Petrol": "Z", "Diesel": "D", "CNG": "N", "Ethanol": "E"}
        fuel_code = fuel_map.get(fuel_type, "Z")
        input_data[f"Fuel_type_{fuel_code}"] = 1
        
        # Convert to DataFrame
        input_df = pd.DataFrame([input_data])
        
        # Reindex to match model columns (fills missing with 0)
        input_df = input_df.reindex(columns=model_columns, fill_value=0)
        
        # Predict base emission rate (g/km) using ML model
        base_emission_rate_per_km = emission_model.predict(input_df)[0]
        
    except Exception as e:
        # Fallback to database value if ML prediction fails
        print(f"ML prediction failed, using database value: {e}")
        base_emission_rate_per_km = vehicle.get("co2_emissions", 200)
    
    # Traffic multipliers - higher traffic increases emissions
    traffic_multipliers = {
        1: 1.0,   # Low traffic - no increase
        2: 1.15,  # Medium traffic - 15% increase
        3: 1.30   # High traffic - 30% increase
    }
    
    # Apply traffic multiplier
    multiplier = traffic_multipliers.get(traffic_level, 1.0)
    adjusted_emission_rate = base_emission_rate_per_km * multiplier
    
    # Calculate total emission: (g/km) * km / 1000 = kg
    total_emission_kg = (adjusted_emission_rate * distance_km) / 1000
    
    return round(total_emission_kg, 2)


# -----------------------------
# HOME - Serve Frontend UI
# -----------------------------
@app.get("/", include_in_schema=False)
def home():
    return FileResponse("app/static/home.html")

@app.get("/route-planner", include_in_schema=False)
def route_planner():
    return FileResponse("app/static/index.html")


# -----------------------------
# MODEL INFO PAGE
# -----------------------------
@app.get("/model-info", include_in_schema=False)
def model_info():
    """
    Serve the ML model information page.
    
    Returns the model information HTML page showing details about
    the trained ML models, performance metrics, and training process.
    This endpoint is excluded from API documentation.
    """
    return FileResponse("app/static/model-info.html")


# -----------------------------
# MAPS API CONFIGURATION
# -----------------------------
@app.get("/api/maps-config", include_in_schema=False)
def get_maps_config():
    """
    Get Google Maps API configuration.
    
    Returns the Google Maps API key for frontend use.
    This endpoint is excluded from API documentation.
    """
    return {
        "api_key": settings.google_maps_api_key
    }


# -----------------------------
# SERVE VISUALIZATION IMAGES
# -----------------------------
@app.get("/visualizations/{filename}", include_in_schema=False)
def get_visualization(filename: str):
    """
    Serve visualization images.
    
    Returns visualization images from the visualizations directory.
    This endpoint is excluded from API documentation.
    """
    import os
    from pathlib import Path
    
    # Security: Only allow specific image files
    allowed_files = [
        "actual_vs_predicted.png",
        "residual_plots.png",
        "feature_importance.png",
        "learning_curves.png",
        "model_comparison.png",
        "shap_summary.png"
    ]
    
    if filename not in allowed_files:
        raise HTTPException(status_code=404, detail="Visualization not found")
    
    file_path = Path("visualizations") / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Visualization not found")
    
    return FileResponse(file_path)


# -----------------------------
# SERVE DATA ANALYSIS IMAGES
# -----------------------------
@app.get("/data-visualizations/{folder}/{filename}", include_in_schema=False)
def get_data_visualization(folder: str, filename: str):
    """
    Serve data analysis visualization images.
    
    Returns visualization images from the data analysis folders.
    This endpoint is excluded from API documentation.
    """
    import os
    from pathlib import Path
    
    # Security: Only allow specific folders and files
    allowed_folders = {
        "eda_plots": ["distributions.png", "correlation_heatmap.png", "categorical_distributions.png"],
        "feature_engineering": ["feature_importance.png", "correlation_heatmap.png"],
        "model_training": ["model_comparison.png"],
        "hyperparameter_tuning": ["tuning_comparison.png"]
    }
    
    if folder not in allowed_folders:
        raise HTTPException(status_code=404, detail="Folder not found")
    
    if filename not in allowed_folders[folder]:
        raise HTTPException(status_code=404, detail="Visualization not found")
    
    file_path = Path("data") / folder / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Visualization not found")
    
    return FileResponse(file_path)


# -----------------------------
# HEALTH CHECK
# -----------------------------
@app.get(
    "/health",
    response_model=dict,
    summary="System Health Check",
    description="Check the health status of the system and its components",
    responses={
        200: {
            "description": "System is healthy",
            "content": {
                "application/json": {
                    "example": {
                        "status": "healthy",
                        "timestamp": "2024-01-15T10:30:00.000Z",
                        "version": "1.0.0",
                        "components": {
                            "database": "loaded",
                            "ml_model": "loaded",
                            "maps_api": "configured"
                        }
                    }
                }
            }
        },
        503: {
            "description": "System is unhealthy",
            "content": {
                "application/json": {
                    "example": {
                        "status": "unhealthy",
                        "timestamp": "2024-01-15T10:30:00.000Z",
                        "version": "1.0.0",
                        "components": {
                            "database": "not_loaded",
                            "ml_model": "loaded",
                            "maps_api": "configured"
                        }
                    }
                }
            }
        }
    },
    tags=["System"]
)
@limiter.limit(f"{settings.rate_limit_requests}/{settings.rate_limit_period}seconds")
def health_check(request: Request):
    """
    System health check endpoint.
    
    Performs comprehensive health checks on all system components:
    - **Vehicle Database**: Verifies the vehicle database is loaded in memory
    - **ML Model**: Verifies the emission prediction model is loaded
    - **Maps API**: Verifies Google Maps API key is configured
    
    Returns:
        - **200 OK**: All components are healthy
        - **503 Service Unavailable**: One or more components are unhealthy
    
    The response includes:
    - Overall system status (healthy/unhealthy)
    - Timestamp of the health check
    - Application version
    - Individual component statuses
    
    This endpoint is useful for:
    - Monitoring system availability
    - Verifying successful deployment
    - Debugging configuration issues
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "components": {}
    }
    
    is_healthy = True
    
    # Check vehicle database
    try:
        if vehicle_manager is not None and len(vehicle_manager.vehicle_index) > 0:
            health_status["components"]["database"] = "loaded"
        else:
            health_status["components"]["database"] = "not_loaded"
            is_healthy = False
    except Exception as e:
        health_status["components"]["database"] = f"error: {str(e)}"
        is_healthy = False
    
    # Check ML model
    try:
        if emission_model is not None and model_columns is not None:
            health_status["components"]["ml_model"] = "loaded"
        else:
            health_status["components"]["ml_model"] = "not_loaded"
            is_healthy = False
    except Exception as e:
        health_status["components"]["ml_model"] = f"error: {str(e)}"
        is_healthy = False
    
    # Check Maps API configuration
    try:
        if GOOGLE_MAPS_API_KEY and GOOGLE_MAPS_API_KEY != "your_google_maps_api_key_here":
            health_status["components"]["maps_api"] = "configured"
        else:
            health_status["components"]["maps_api"] = "not_configured"
            is_healthy = False
    except Exception as e:
        health_status["components"]["maps_api"] = f"error: {str(e)}"
        is_healthy = False
    
    # Set overall status
    if not is_healthy:
        health_status["status"] = "unhealthy"
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=health_status
        )
    
    return health_status


# -----------------------------
# GREENER ALTERNATIVES
# -----------------------------
@app.get(
    "/vehicles/greener-alternatives",
    response_model=dict,
    summary="Get Greener Vehicle Alternatives",
    description="Find vehicles of the same class with lower CO2 emissions",
    tags=["Vehicles"]
)
@limiter.limit(f"{settings.rate_limit_requests}/{settings.rate_limit_period}seconds")
def greener_alternatives(vehicle_no: str, request: Request, limit: int = 3):
    """
    Return up to `limit` vehicles of the same class with lower CO2 g/km.
    Includes savings percentage vs the current vehicle.
    """
    vehicle = vehicle_manager.get_vehicle(vehicle_no)
    if not vehicle:
        raise HTTPException(status_code=404, detail=f"Vehicle '{vehicle_no}' not found.")

    co2_per_km = float(vehicle.get("co2_emissions", 200))
    alternatives = vehicle_manager.get_greener_alternatives(vehicle_no, limit)

    return {
        "current_vehicle": vehicle_no.upper(),
        "current_co2_per_km": co2_per_km,
        "current_emission_grade": VehicleManager.get_emission_grade(co2_per_km),
        "alternatives": alternatives
    }


# -----------------------------
# VEHICLE SEARCH (AUTOCOMPLETE)
# -----------------------------
@app.get(
    "/vehicles/search",
    response_model=dict,
    summary="Search Vehicles",
    description="Search for vehicles by make/model (autocomplete)",
    tags=["Vehicles"]
)
@limiter.limit(f"{settings.rate_limit_requests}/{settings.rate_limit_period}seconds")
def search_vehicles(q: str, request: Request):
    """
    Search for vehicles matching a query string.

    Returns up to 10 matching vehicle names for autocomplete.
    Requires at least 2 characters.

    **Query Parameters:**
    - **q** (string, required): Search query (min 2 characters)

    **Returns:**
    - **results**: List of matching vehicle name strings (max 10)
    """
    if len(q.strip()) < 2:
        return {"results": []}

    query_upper = q.strip().upper()
    matches = [
        key for key in vehicle_manager.vehicle_index
        if query_upper in key
    ]
    return {"results": matches[:10]}


# -----------------------------
# POPULAR VEHICLES
# -----------------------------
@app.get(
    "/vehicles/popular",
    response_model=dict,
    summary="Get Popular Vehicles",
    description="Return a curated list of 20 popular vehicles",
    tags=["Vehicles"]
)
@limiter.limit(f"{settings.rate_limit_requests}/{settings.rate_limit_period}seconds")
def popular_vehicles(request: Request):
    """
    Return a curated list of 20 popular vehicles from the dataset.

    **Returns:**
    - **vehicles**: List of popular vehicle name strings
    """
    popular = [
        "Toyota Camry",
        "Honda Accord Sedan",
        "Ford Mustang",
        "BMW 320i",
        "BMW 530i xDrive",
        "Volkswagen Jetta",
        "Hyundai Elantra GT",
        "Nissan Altima",
        "Audi A4 quattro",
        "Subaru Outback AWD",
        "Lexus RX 350 AWD",
        "Chevrolet Camaro",
        "Ford Edge",
        "Honda CR-V AWD",
        "Toyota RAV4 AWD",
        "Toyota Highlander AWD",
        "Honda Pilot AWD",
        "Ford Explorer AWD",
        "Nissan Rogue AWD",
        "Hyundai Tucson AWD",
    ]
    # Filter to only include vehicles that exist in the loaded index
    available = [v for v in popular if vehicle_manager.vehicle_exists(v)]
    return {"vehicles": available}


# -----------------------------
# GET VEHICLE DETAILS
# -----------------------------
@app.get(
    "/vehicle/{vehicle_no}",
    response_model=dict,
    summary="Get Vehicle Details",
    description="Retrieve vehicle specifications by vehicle number",
    responses={
        200: {
            "description": "Vehicle found successfully",
            "content": {
                "application/json": {
                    "example": {
                        "vehicle_no": "MH01AB1234",
                        "type": "Sedan",
                        "fuel": "Petrol",
                        "engine_size": 1.5,
                        "mileage": 18.5
                    }
                }
            }
        },
        404: {
            "description": "Vehicle not found",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Vehicle not found",
                        "error_code": "VEHICLE_NOT_FOUND",
                        "suggestions": [
                            "Check vehicle number format",
                            "Example formats: MH01AB1234, DL02CD5678"
                        ],
                        "timestamp": "2024-01-15T10:30:00.000Z"
                    }
                }
            }
        },
        422: {
            "description": "Validation error",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Input validation failed",
                        "error_code": "VALIDATION_ERROR",
                        "timestamp": "2024-01-15T10:30:00.000Z"
                    }
                }
            }
        }
    },
    tags=["Vehicles"]
)
@limiter.limit(f"{settings.rate_limit_requests}/{settings.rate_limit_period}seconds")
def get_vehicle(vehicle_no: str, request: Request):
    """
    Retrieve vehicle specifications from the database.
    
    Looks up a vehicle by its identification number and returns detailed specifications
    including type, fuel, engine size, and mileage.
    
    **Path Parameters:**
    - **vehicle_no** (string): Vehicle identification number (e.g., MH01AB1234)
    
    **Lookup Behavior:**
    - Case-insensitive matching (MH01AB1234 = mh01ab1234)
    - Whitespace is automatically trimmed
    - Vehicle numbers are normalized to uppercase
    
    **Returns:**
    - **vehicle_no**: Vehicle identification number
    - **type**: Vehicle type (SUV, Sedan, or Hatchback)
    - **fuel**: Fuel type (Petrol, Diesel, or CNG)
    - **engine_size**: Engine size in liters
    - **mileage**: Fuel efficiency in km/l
    
    **Status Codes:**
    - **200**: Vehicle found successfully
    - **404**: Vehicle not found in database
    - **422**: Invalid vehicle number format
    
    **Example Request:**
    ```
    GET /vehicle/MH01AB1234
    ```
    
    **Example Response:**
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

    # Use VehicleManager for lookup
    vehicle = vehicle_manager.get_vehicle(vehicle_no)

    if vehicle is None:
        sample_vehicles = vehicle_manager.get_sample_vehicles(5)
        raise HTTPException(
            status_code=404, 
            detail=f"Vehicle not found. Try examples like: {', '.join(sample_vehicles[:3])}"
        )

    return {
        "vehicle_no": str(vehicle["vehicle_no"]),
        "type": str(vehicle["type"]),
        "fuel": str(vehicle["fuel"]),
        "engine_size": float(vehicle["engine_size"]),
        "mileage": float(vehicle["mileage"])
    }


# -----------------------------
# ML EMISSION PREDICTION
# -----------------------------
@app.post(
    "/calculate-emission",
    response_model=dict,
    summary="Calculate CO₂ Emission",
    description="Predict CO₂ emission for a vehicle and distance using ML model",
    responses={
        200: {
            "description": "Emission calculated successfully",
            "content": {
                "application/json": {
                    "example": {
                        "vehicle_no": "MH01AB1234",
                        "distance_km": 50.5,
                        "predicted_co2_kg": 12.34,
                        "model_used": "RandomForest Regression"
                    }
                }
            }
        },
        404: {
            "description": "Vehicle not found",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Vehicle not found",
                        "error_code": "VEHICLE_NOT_FOUND",
                        "suggestions": [
                            "Check vehicle number format",
                            "Example formats: MH01AB1234, DL02CD5678"
                        ],
                        "timestamp": "2024-01-15T10:30:00.000Z"
                    }
                }
            }
        },
        422: {
            "description": "Validation error",
            "content": {
                "application/json": {
                    "example": {
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
                }
            }
        }
    },
    tags=["Emissions"]
)
@limiter.limit(f"{settings.rate_limit_requests}/{settings.rate_limit_period}seconds")
def calculate_emission(data: EmissionRequest, request: Request):
    """
    Calculate predicted CO₂ emission for a vehicle and distance.
    
    Uses a trained RandomForest regression model to predict carbon dioxide emissions
    based on vehicle specifications and travel distance. The prediction considers:
    - Vehicle type (SUV, Sedan, Hatchback)
    - Fuel type (Petrol, Diesel, CNG)
    - Engine size
    - Fuel efficiency (mileage)
    - Distance to travel
    - Traffic level (default: Medium)
    
    **Request Body:**
    - **vehicle_no** (string, required): Vehicle identification number
    - **distance_km** (float, required): Distance in kilometers (0 < distance ≤ 10000)
    
    **Validation Rules:**
    - Vehicle number must exist in the database
    - Distance must be positive and not exceed 10,000 km
    - Vehicle number is case-insensitive and whitespace-tolerant
    
    **Returns:**
    - **vehicle_no**: Vehicle identification number
    - **distance_km**: Distance in kilometers
    - **predicted_co2_kg**: Predicted CO₂ emission in kilograms
    - **model_used**: ML model used for prediction
    
    **Status Codes:**
    - **200**: Emission calculated successfully
    - **404**: Vehicle not found in database
    - **422**: Invalid input (negative distance, missing fields, etc.)
    
    **Example Request:**
    ```json
    {
        "vehicle_no": "MH01AB1234",
        "distance_km": 50.5
    }
    ```
    
    **Example Response:**
    ```json
    {
        "vehicle_no": "MH01AB1234",
        "distance_km": 50.5,
        "predicted_co2_kg": 12.34,
        "model_used": "RandomForest Regression"
    }
    ```
    
    **Notes:**
    - Predictions are based on medium traffic conditions by default
    - For traffic-aware predictions, use the `/eco-route` endpoint
    - Emission values are rounded to 2 decimal places
    """

    vehicle = vehicle_manager.get_vehicle(data.vehicle_no)

    if vehicle is None:
        sample_vehicles = vehicle_manager.get_sample_vehicles(5)
        raise HTTPException(
            status_code=404, 
            detail=f"Vehicle not found. Try examples like: {', '.join(sample_vehicles[:3])}"
        )

    traffic_level = 2  # Medium traffic default

    co2 = predict_emission(vehicle, data.distance_km, traffic_level)

    return {
        "vehicle_no": data.vehicle_no,
        "distance_km": data.distance_km,
        "predicted_co2_kg": co2,
        "model_used": "RandomForest Regression"
    }


# -----------------------------
# ECO ROUTE RECOMMENDATION
# -----------------------------
@app.post(
    "/eco-route",
    response_model=dict,
    summary="Get Eco-Route Recommendations",
    description="Get route recommendations optimized for minimum CO₂ emissions",
    responses={
        200: {
            "description": "Routes retrieved and analyzed successfully",
            "content": {
                "application/json": {
                    "example": {
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
                }
            }
        },
        400: {
            "description": "No routes found",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "No routes found between the specified locations. Please verify the source and destination addresses and ensure they are accessible by road.",
                        "error_code": "NO_ROUTES_FOUND",
                        "suggestions": [
                            "Check spelling of location names",
                            "Try using more specific addresses",
                            "Ensure locations are accessible by road"
                        ],
                        "timestamp": "2024-01-15T10:30:00.000Z"
                    }
                }
            }
        },
        404: {
            "description": "Vehicle not found",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Vehicle 'INVALID123' not found. Please check the vehicle number and try again.",
                        "error_code": "VEHICLE_NOT_FOUND",
                        "suggestions": [
                            "Check vehicle number format",
                            "Example formats: MH01AB1234, DL02CD5678"
                        ],
                        "timestamp": "2024-01-15T10:30:00.000Z"
                    }
                }
            }
        },
        422: {
            "description": "Validation error",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Input validation failed",
                        "error_code": "VALIDATION_ERROR",
                        "errors": [
                            {
                                "field": "source",
                                "message": "Location cannot be empty",
                                "type": "value_error"
                            }
                        ],
                        "timestamp": "2024-01-15T10:30:00.000Z"
                    }
                }
            }
        },
        503: {
            "description": "External service error",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Google Maps API request timed out. Please try again in a moment.",
                        "error_code": "MAPS_API_TIMEOUT",
                        "timestamp": "2024-01-15T10:30:00.000Z"
                    }
                }
            }
        }
    },
    tags=["Routes"]
)
@limiter.limit(f"{settings.rate_limit_requests}/{settings.rate_limit_period}seconds")
def eco_route(data: RouteRequest, request: Request):
    """
    Get eco-friendly route recommendations with emission predictions.
    
    This endpoint integrates with Google Maps Directions API to retrieve multiple route
    alternatives, analyzes real-time traffic conditions, predicts CO₂ emissions for each
    route using the ML model, and recommends the route with the lowest environmental impact.
    
    **Request Body:**
    - **vehicle_no** (string, required): Vehicle identification number
    - **source** (string, required): Source location (city, state, or full address)
    - **destination** (string, required): Destination location (city, state, or full address)
    
    **Processing Steps:**
    1. Validates vehicle exists in database
    2. Queries Google Maps API for route alternatives
    3. Analyzes traffic conditions for each route
    4. Predicts CO₂ emissions using ML model
    5. Ranks routes by emission levels
    6. Calculates emission savings
    
    **Traffic Analysis:**
    The system classifies traffic levels based on actual vs. expected duration:
    - **Low**: Actual duration ≤ 110% of expected
    - **Medium**: Actual duration 110-130% of expected
    - **High**: Actual duration > 130% of expected
    
    **Returns:**
    - **source**: Source location
    - **destination**: Destination location
    - **vehicle_no**: Vehicle identification number
    - **recommended_route**: Route with lowest predicted emissions
    - **all_routes**: All available route alternatives with emissions
    - **selection_criteria**: Criteria used for route selection
    - **emission_savings_kg**: Emission savings vs. worst route (kg)
    - **emission_savings_percent**: Emission savings as percentage
    
    **Status Codes:**
    - **200**: Routes retrieved and analyzed successfully
    - **400**: No routes found between locations
    - **404**: Vehicle not found in database
    - **422**: Invalid input (empty locations, invalid vehicle number)
    - **503**: Google Maps API error or timeout
    
    **Example Request:**
    ```json
    {
        "vehicle_no": "MH01AB1234",
        "source": "Mumbai, Maharashtra",
        "destination": "Pune, Maharashtra"
    }
    ```
    
    **Example Response:**
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
    
    **Notes:**
    - Requires valid Google Maps API key with Directions API enabled
    - Traffic data is requested for real-time accuracy
    - System automatically retries on timeout (up to 3 attempts)
    - Emission predictions consider vehicle specs, distance, and traffic
    - All routes are compared to help users make informed decisions
    """
    vehicle = vehicle_manager.get_vehicle(data.vehicle_no)

    if vehicle is None:
        sample_vehicles = vehicle_manager.get_sample_vehicles(5)
        raise HTTPException(
            status_code=404,
            detail=f"Vehicle '{data.vehicle_no}' not found. Try examples like: {', '.join(sample_vehicles[:3])}"
        )

    # Get route options from Google Directions API
    url = "https://maps.googleapis.com/maps/api/directions/json"
    params = {
        "origin": data.source,
        "destination": data.destination,
        "alternatives": "true",
        "departure_time": "now",  # Request traffic data
        "key": GOOGLE_MAPS_API_KEY
    }

    try:
        response = requests.get(url, params=params, timeout=settings.maps_api_timeout)
        response.raise_for_status()
        api_data = response.json()
    except requests.exceptions.Timeout:
        raise HTTPException(
            status_code=503,
            detail="Google Maps API request timed out. Please try again in a moment."
        )
    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=503,
            detail="Unable to connect to Google Maps API. Please try again later."
        )

    routes = api_data.get("routes", [])

    if not routes:
        raise HTTPException(
            status_code=400,
            detail="No routes found between the specified locations. Please verify the source and destination addresses and ensure they are accessible by road."
        )

    route_results = []

    for idx, route in enumerate(routes):
        leg = route["legs"][0]
        
        distance_meters = leg["distance"]["value"]
        duration_seconds = leg["duration"]["value"]
        distance_km = distance_meters / 1000
        
        # Get duration in traffic if available
        duration_in_traffic = None
        if "duration_in_traffic" in leg:
            duration_in_traffic = leg["duration_in_traffic"]["value"]
        
        # Use TrafficAnalyzer to calculate traffic level
        traffic_level = TrafficAnalyzer.calculate_traffic_level(
            duration_seconds,
            duration_in_traffic
        )
        traffic_label = TrafficAnalyzer.get_traffic_label(traffic_level)
        
        # Predict CO2 emission
        predicted_co2 = predict_emission(vehicle, distance_km, traffic_level)
        
        # Get route summary
        summary = route.get("summary", "")
        if not summary:
            summary = f"Route {idx + 1}"

        # Calculate fuel cost if price provided
        fuel_cost = None
        if data.fuel_price_per_litre is not None:
            mileage = float(vehicle.get("mileage", 1))
            if mileage > 0:
                fuel_cost = round((distance_km / mileage) * data.fuel_price_per_litre, 2)

        route_results.append({
            "route_number": idx + 1,
            "distance_km": round(distance_km, 2),
            "duration_minutes": round(duration_seconds / 60, 2),
            "traffic_level": traffic_label,
            "predicted_co2_kg": predicted_co2,
            "summary": summary,
            "fuel_cost_estimate": fuel_cost,
            "carbon_cost_inr": round(predicted_co2 * settings.carbon_tax_rate_per_kg, 2)
        })

    # Select lowest emission route
    best_route = min(route_results, key=lambda x: x["predicted_co2_kg"])
    
    # Calculate emission savings (difference from worst route)
    worst_route = max(route_results, key=lambda x: x["predicted_co2_kg"])
    emission_savings_kg = worst_route["predicted_co2_kg"] - best_route["predicted_co2_kg"]
    
    # Calculate emission savings percentage
    if worst_route["predicted_co2_kg"] > 0:
        emission_savings_percent = round(
            (emission_savings_kg / worst_route["predicted_co2_kg"]) * 100,
            2
        )
    else:
        emission_savings_percent = 0.0

    # Add eco_score to all routes
    route_results = TrafficAnalyzer.calculate_eco_score(route_results)
    # Re-fetch best_route after eco_score added
    best_route = min(route_results, key=lambda x: x["predicted_co2_kg"])

    # Emission grade for the vehicle
    co2_per_km = float(vehicle.get("co2_emissions", 200))
    emission_grade = VehicleManager.get_emission_grade(co2_per_km)

    # Calculate CO2 equivalents for the recommended route
    rec_co2 = best_route["predicted_co2_kg"]
    co2_equivalents = {
        "trees_to_offset": round(rec_co2 / 21, 2),
        "phone_charges": round(rec_co2 / 0.008, 1),
        "km_in_avg_car": round(rec_co2 / 0.21, 1)
    }

    return {
        "source": data.source,
        "destination": data.destination,
        "vehicle_no": data.vehicle_no,
        "emission_grade": emission_grade,
        "co2_per_km": co2_per_km,
        "recommended_route": best_route,
        "all_routes": route_results,
        "selection_criteria": "Minimum CO2 Emission (ML Predicted)",
        "emission_savings_kg": round(emission_savings_kg, 2),
        "emission_savings_percent": emission_savings_percent,
        "co2_equivalents": co2_equivalents
    }