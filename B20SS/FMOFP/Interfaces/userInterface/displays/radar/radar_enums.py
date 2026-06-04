"""
Radar Enums for Display System

Contains radar-related enumerations needed by the display system.
This file is a local copy of radar_enums.py in the Radar system.
"""

from enum import Enum

class weather_radarMode(Enum):
    """Weather radar mode enumeration for display system."""
    # Universal Base Modes (0-9)
    INITIALIZING = -1   # Special pre-operational state
    STANDBY = 0         # Power-saving/inactive state
    NORMAL = 1          # Standard operational mode
    DEGRADED = 2        # Reduced capability mode
    TEST = 3            # Built-in test mode 
    MAINTENANCE = 4     # Maintenance/calibration mode
    EMERGENCY = 5       # Emergency operations mode
    FAILURE = 6         # System failure mode
    RECOVERY = 7        # Recovery from failure mode
    CALIBRATION = 8     # Active calibration mode
    
    # Weather Radar Specific Modes (10-19)
    SURVEILLANCE = 10   # Primary weather surveillance mode
    MAPPING = 11        # Ground mapping (Weather radar)
    TURBULENCE = 12     # Turbulence detection (Weather radar)
    WINDSHEAR = 13      # Wind shear detection (Weather radar)
    PRECIPITATION = 14  # Precipitation measurement mode

class targeting_radarMode(Enum):
    """Targeting radar mode enumeration for display system."""
    # Universal Base Modes (0-9)
    INITIALIZING = -1   # Special pre-operational state
    STANDBY = 0         # Power-saving/inactive state
    NORMAL = 1          # Standard operational mode
    DEGRADED = 2        # Reduced capability mode
    TEST = 3            # Built-in test mode 
    MAINTENANCE = 4     # Maintenance/calibration mode
    EMERGENCY = 5       # Emergency operations mode
    FAILURE = 6         # System failure mode
    RECOVERY = 7        # Recovery from failure mode
    CALIBRATION = 8     # Active calibration mode
    
    # Targeting Radar Specific Modes (40-49)
    TARGET_SEARCH = 40  # Target search mode
    SEARCH = 40         # Alias for TARGET_SEARCH
    TARGET_TRACK = 41   # Target tracking mode
    TRACK = 41          # Alias for TARGET_TRACK
    LOCK = 42           # Lock mode (Targeting)
    TERRAIN_AVOIDANCE = 43 # Terrain avoidance (Targeting)
    GROUND_MAPPING = 25 # Using TFR ground mapping value for compatibility

class sar_radarMode(Enum):
    """SAR radar mode enumeration for display system."""
    # Universal Base Modes (0-9)
    INITIALIZING = -1   # Special pre-operational state
    STANDBY = 0         # Power-saving/inactive state
    NORMAL = 1          # Standard operational mode
    DEGRADED = 2        # Reduced capability mode
    TEST = 3            # Built-in test mode 
    MAINTENANCE = 4     # Maintenance/calibration mode
    EMERGENCY = 5       # Emergency operations mode
    FAILURE = 6         # System failure mode
    RECOVERY = 7        # Recovery from failure mode
    CALIBRATION = 8     # Active calibration mode
    
    # SAR Radar Specific Modes (30-39)
    STRIPMAP = 30       # Stripmap mode (SAR)
    SPOTLIGHT = 31      # Spotlight mode (SAR)
    SCANSAR = 32        # ScanSAR mode (SAR)
    INTERFEROMETRIC = 33 # Interferometric mode (SAR)
    DOPPLER_BEAM = 34   # Doppler beam mode (SAR)

class aewc_radarMode(Enum):
    """AEWC radar mode enumeration for display system."""
    # Universal Base Modes (0-9)
    INITIALIZING = -1   # Special pre-operational state
    STANDBY = 0         # Power-saving/inactive state
    NORMAL = 1          # Standard operational mode
    DEGRADED = 2        # Reduced capability mode
    TEST = 3            # Built-in test mode 
    MAINTENANCE = 4     # Maintenance/calibration mode
    EMERGENCY = 5       # Emergency operations mode
    FAILURE = 6         # System failure mode
    RECOVERY = 7        # Recovery from failure mode
    CALIBRATION = 8     # Active calibration mode
    
    # AEWC Radar Specific Modes (50-59)
    AEWC_SEARCH = 50    # Search mode (AEWC)
    SEARCH = 50         # Alias for AEWC_SEARCH
    AEWC_SURVEILLANCE = 51 # Surveillance mode (AEWC)
    SURVEILLANCE = 51   # Alias for AEWC_SURVEILLANCE
    SECTOR_SCAN = 52    # Sector scan (AEWC)
    STEALTH_DETECTION = 53 # Stealth detection (AEWC)
    ELECTRONIC_PROTECTION = 54 # Electronic protection (AEWC)
    GROUND_MAPPING = 25 # Using TFR ground mapping value for compatibility

class tfr_radarMode(Enum):
    """TFR radar mode enumeration for display system."""
    # Universal Base Modes (0-9)
    INITIALIZING = -1   # Special pre-operational state
    STANDBY = 0         # Power-saving/inactive state
    NORMAL = 1          # Standard operational mode
    DEGRADED = 2        # Reduced capability mode
    TEST = 3            # Built-in test mode 
    MAINTENANCE = 4     # Maintenance/calibration mode
    EMERGENCY = 5       # Emergency operations mode
    FAILURE = 6         # System failure mode
    RECOVERY = 7        # Recovery from failure mode
    CALIBRATION = 8     # Active calibration mode
    
    # TFR Radar Specific Modes (20-29)
    TFR_SEARCH = 20     # Search mode (TFR)
    SEARCH = 20         # Alias for TFR_SEARCH
    TFR_TRACK = 21      # Track mode (TFR)
    TRACK = 21          # Alias for TFR_TRACK
    TFR_ACTIVE = 22     # Active mode (TFR)
    ACTIVE = 22         # Alias for TFR_ACTIVE
    TERRAIN_FOLLOWING = 23 # Terrain following (TFR)
    OBSTACLE_AVOIDANCE = 24 # Obstacle avoidance (TFR)
    TFR_GROUND_MAPPING = 25 # Ground mapping (TFR)
    GROUND_MAPPING = 25 # Alias for TFR_GROUND_MAPPING

class RadarMode(Enum):
    """Generic radar mode enumeration for display system."""
    STANDBY = 0
    NORMAL = 1
    ACTIVE = 2
    SEARCH = 3
    TRACK = 4
