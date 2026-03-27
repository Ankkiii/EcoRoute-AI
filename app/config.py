"""
Configuration management for Vehicle Emission Eco-Route System.
Loads settings from environment variables with validation.
"""

import os
from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator


class Settings(BaseSettings):
    """Application configuration loaded from environment variables"""
    
    # API Configuration
    google_maps_api_key: str = Field(..., description="Google Maps API key for route data")
    api_host: str = Field(default="0.0.0.0", description="API server host")
    api_port: int = Field(default=8000, description="API server port")
    
    # File Paths
    vehicle_database_path: str = Field(
        default="data/cleaned_fuel_consumption.csv",
        description="Path to vehicle database CSV file (Canada dataset)"
    )
    model_path: str = Field(
        default="models/stacking_ensemble.pkl",
        description="Path to trained ML model pickle file"
    )
    model_columns_path: str = Field(
        default="models/stacking_model_columns.pkl",
        description="Path to model columns pickle file"
    )
    
    # CORS Configuration
    cors_origins: List[str] = Field(
        default=["*"],
        description="Allowed CORS origins"
    )
    cors_allow_credentials: bool = Field(
        default=True,
        description="Allow credentials in CORS requests"
    )
    cors_allow_methods: List[str] = Field(
        default=["*"],
        description="Allowed HTTP methods for CORS"
    )
    cors_allow_headers: List[str] = Field(
        default=["*"],
        description="Allowed headers for CORS"
    )
    
    # Rate Limiting
    rate_limit_requests: int = Field(
        default=100,
        description="Maximum requests per period"
    )
    rate_limit_period: int = Field(
        default=60,
        description="Rate limit period in seconds"
    )
    
    # Caching
    route_cache_ttl: int = Field(
        default=300,
        description="Route cache TTL in seconds (5 minutes)"
    )
    
    # Logging
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
    )
    log_file: str = Field(
        default="app.log",
        description="Log file path"
    )
    log_format: str = Field(
        default="json",
        description="Log format (json or text)"
    )
    
    # External API
    maps_api_timeout: int = Field(
        default=10,
        description="Google Maps API timeout in seconds"
    )
    maps_api_retries: int = Field(
        default=3,
        description="Number of retries for Maps API calls"
    )
    
    # Environment
    environment: str = Field(
        default="development",
        description="Environment (development or production)"
    )

    # Carbon Tax
    carbon_tax_rate_per_kg: float = Field(
        default=1.0,
        description="Carbon tax rate in INR per kg CO2 (default ₹1/kg = ₹1000/tonne)"
    )
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is valid"""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}")
        return v_upper
    
    @field_validator("log_format")
    @classmethod
    def validate_log_format(cls, v: str) -> str:
        """Validate log format is valid"""
        valid_formats = ["json", "text"]
        v_lower = v.lower()
        if v_lower not in valid_formats:
            raise ValueError(f"log_format must be one of {valid_formats}")
        return v_lower
    
    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate environment is valid"""
        valid_envs = ["development", "production"]
        v_lower = v.lower()
        if v_lower not in valid_envs:
            raise ValueError(f"environment must be one of {valid_envs}")
        return v_lower


# Singleton instance
_settings: Settings = None


def get_settings() -> Settings:
    """
    Get settings singleton instance.
    Creates instance on first call, returns cached instance on subsequent calls.
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def validate_startup_config(settings: Settings) -> None:
    """
    Validate required files and configuration at startup.
    
    Raises:
        FileNotFoundError: If required files are missing
        ValueError: If configuration values are invalid
    """
    # Check Google Maps API key is not placeholder
    if not settings.google_maps_api_key or settings.google_maps_api_key == "your_google_maps_api_key_here":
        raise ValueError(
            "GOOGLE_MAPS_API_KEY is not configured. "
            "Please set a valid Google Maps API key in your .env file or environment variables."
        )
    
    # Check required files exist
    required_files = [
        (settings.vehicle_database_path, "Vehicle database CSV file"),
        (settings.model_path, "ML model pickle file"),
        (settings.model_columns_path, "Model columns pickle file"),
    ]
    
    for file_path, description in required_files:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(
                f"{description} not found at: {file_path}\n"
                f"Please ensure the file exists or update the configuration."
            )
        
        if not path.is_file():
            raise ValueError(
                f"{description} path is not a file: {file_path}"
            )
    
    # Validate numeric ranges
    if settings.api_port < 1 or settings.api_port > 65535:
        raise ValueError(f"api_port must be between 1 and 65535, got {settings.api_port}")
    
    if settings.rate_limit_requests < 1:
        raise ValueError(f"rate_limit_requests must be positive, got {settings.rate_limit_requests}")
    
    if settings.rate_limit_period < 1:
        raise ValueError(f"rate_limit_period must be positive, got {settings.rate_limit_period}")
    
    if settings.route_cache_ttl < 0:
        raise ValueError(f"route_cache_ttl must be non-negative, got {settings.route_cache_ttl}")
    
    if settings.maps_api_timeout < 1:
        raise ValueError(f"maps_api_timeout must be positive, got {settings.maps_api_timeout}")
    
    if settings.maps_api_retries < 1:
        raise ValueError(f"maps_api_retries must be positive, got {settings.maps_api_retries}")
