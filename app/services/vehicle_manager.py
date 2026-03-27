"""
Vehicle database manager for the Vehicle Emission Eco-Route System.

This module provides efficient vehicle data storage and retrieval with
in-memory caching and O(1) lookup performance.

Requirements: 1.3, 13.1, 13.3, 13.4, 14.1, 14.5
"""

import pandas as pd
from typing import Optional, List
from pathlib import Path


class VehicleManager:
    """
    Manages vehicle database with in-memory caching and indexed lookup.
    
    Provides O(1) vehicle lookup by number with case-insensitive and
    whitespace-tolerant matching.
    
    Requirements: 1.3, 13.1, 13.3, 13.4, 14.1, 14.5
    """
    
    def __init__(self, csv_path: str):
        """
        Initialize the vehicle manager.
        
        Args:
            csv_path: Path to the vehicle database CSV file
        """
        self.csv_path = csv_path
        self.vehicles_df: Optional[pd.DataFrame] = None
        self.vehicle_index: dict[str, dict] = {}
    
    def load(self) -> None:
        """
        Load vehicle database into memory and create index.
        
        Reads the CSV file and creates an in-memory dictionary index
        for O(1) lookup performance. Vehicle identifiers are normalized
        to uppercase for case-insensitive matching.
        
        Supports Canada dataset format with Make/Model as identifier.
        
        Raises:
            FileNotFoundError: If CSV file doesn't exist
            pd.errors.EmptyDataError: If CSV file is empty
            KeyError: If required columns are missing
            
        Requirements: 14.1, 14.5
        """
        # Check if file exists
        if not Path(self.csv_path).exists():
            raise FileNotFoundError(f"Vehicle database not found at: {self.csv_path}")
        
        # Load CSV into DataFrame
        self.vehicles_df = pd.read_csv(self.csv_path)
        
        # Map Canada dataset columns to expected format
        fuel_type_map = {
            'Z': 'Petrol',
            'X': 'Petrol',
            'D': 'Diesel',
            'E': 'Ethanol',
            'N': 'CNG'
        }
        
        vehicle_class_map = {
            'Sport utility vehicle: Small': 'SUV',
            'Sport utility vehicle: Standard': 'SUV',
            'Compact': 'Car',
            'Mid-size': 'Car',
            'Full-size': 'Car',
            'Subcompact': 'Car',
            'Minicompact': 'Car',
            'Two-seater': 'Car',
            'Pickup truck: Small': 'Truck',
            'Pickup truck: Standard': 'Truck',
            'Station wagon: Small': 'Car',
            'Minivan': 'Car',
            'Special purpose vehicle': 'Truck'
        }
        
        # Create O(1) lookup index
        self.vehicle_index = {}
        for idx, row in self.vehicles_df.iterrows():
            # Create vehicle identifier from Make + Model, normalize spaces
            vehicle_id = ' '.join(f"{row['Make']} {row['Model']}".strip().upper().split())
            
            # Convert L/100km to km/L for mileage
            combined_l_per_100km = row['Combined (L/100 km)']
            mileage_km_per_l = 100 / combined_l_per_100km if combined_l_per_100km > 0 else 0
            
            # Map to expected format
            vehicle_data = {
                'vehicle_no': vehicle_id,
                'type': vehicle_class_map.get(row['Vehicle class'], 'Car'),
                'fuel': fuel_type_map.get(row['Fuel type'], 'Petrol'),
                'engine_size': row['Engine size (L)'],
                'mileage': round(mileage_km_per_l, 2),
                'make': row['Make'],
                'model': row['Model'],
                'year': row['Model year'],
                'co2_emissions': row['CO2 emissions (g/km)']
            }
            
            self.vehicle_index[vehicle_id] = vehicle_data
    
    def get_vehicle(self, vehicle_no: str) -> Optional[dict]:
        """
        O(1) vehicle lookup by number.
        
        Performs case-insensitive and whitespace-tolerant lookup.
        Handles multiple spaces and normalizes input.
        
        Args:
            vehicle_no: Vehicle identification number
            
        Returns:
            dict: Vehicle data if found, None otherwise
            
        Requirements: 13.1, 13.3, 13.4, 14.5
        """
        # Normalize input: trim whitespace, convert to uppercase, collapse multiple spaces
        normalized_vehicle_no = ' '.join(vehicle_no.strip().upper().split())
        
        # O(1) dictionary lookup
        return self.vehicle_index.get(normalized_vehicle_no)
    
    def vehicle_exists(self, vehicle_no: str) -> bool:
        """
        Check if vehicle exists in the database.
        
        Performs case-insensitive and whitespace-tolerant check.
        Handles multiple spaces and normalizes input.
        
        Args:
            vehicle_no: Vehicle identification number
            
        Returns:
            bool: True if vehicle exists, False otherwise
            
        Requirements: 13.1, 13.3, 13.4
        """
        # Normalize input: trim whitespace, convert to uppercase, collapse multiple spaces
        normalized_vehicle_no = ' '.join(vehicle_no.strip().upper().split())
        
        # Check if key exists in index
        return normalized_vehicle_no in self.vehicle_index
    
    def get_sample_vehicles(self, count: int = 5) -> List[str]:
        """
        Get sample vehicle numbers for error messages.
        
        Returns a list of example vehicle numbers that can be shown
        to users when their vehicle lookup fails.
        
        Args:
            count: Number of sample vehicles to return (default: 5)
            
        Returns:
            list[str]: List of sample vehicle numbers
            
        Requirements: 13.2
        """
        # Return first N vehicle numbers from the index
        return list(self.vehicle_index.keys())[:count]

    @staticmethod
    def get_emission_grade(co2_per_km: float) -> str:
        """
        Return emission grade A/B/C/D based on CO2 g/km.
        A: < 120 g/km (Excellent)
        B: 120-160 g/km (Good)
        C: 160-200 g/km (Fair)
        D: > 200 g/km (Poor)
        """
        if co2_per_km < 120:
            return "A"
        elif co2_per_km < 160:
            return "B"
        elif co2_per_km < 200:
            return "C"
        else:
            return "D"

    def get_greener_alternatives(self, vehicle_no: str, limit: int = 3) -> list:
        """
        Find vehicles of the same class with lower CO2 emissions.
        Returns top `limit` alternatives sorted by CO2 ascending.
        """
        current = self.get_vehicle(vehicle_no)
        if not current:
            return []

        current_co2 = float(current.get("co2_emissions", 9999))
        current_type = current.get("type", "")

        alternatives = []
        for key, v in self.vehicle_index.items():
            if key == vehicle_no.strip().upper():
                continue
            if v.get("type") != current_type:
                continue
            alt_co2 = float(v.get("co2_emissions", 9999))
            if alt_co2 < current_co2:
                savings_pct = round((current_co2 - alt_co2) / current_co2 * 100, 1)
                alternatives.append({
                    "vehicle_no": v["vehicle_no"],
                    "co2_per_km": alt_co2,
                    "emission_grade": self.get_emission_grade(alt_co2),
                    "savings_percent": savings_pct
                })

        alternatives.sort(key=lambda x: x["co2_per_km"])
        return alternatives[:limit]
