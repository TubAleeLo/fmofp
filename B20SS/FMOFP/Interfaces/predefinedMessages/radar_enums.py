"""
Radar Enumerations for Predefined Message System

Contains radar-related enumerations needed by all radar systems.
This serves as a central reference for consistent mode values.
"""

from enum import Enum

class weather_radarMode(Enum):
    """Weather radar mode enumeration."""
    STANDBY = 0
    SURVEILLANCE = 1
    MAPPING = 2
    TURBULENCE = 3
    WINDSHEAR = 4
    NORMAL = 5

class targeting_radarMode(Enum):
    """Targeting radar mode enumeration."""
    STANDBY = 0
    NORMAL = 1
    SEARCH = 2
    TRACKING = 3  # Added TRACKING mode
    TRACK = 3     # Alias for TRACKING for backward compatibility
    LOCK = 4
    GROUND_MAPPING = 5
    TERRAIN_AVOIDANCE = 6

class sar_radarMode(Enum):
    """SAR radar mode enumeration."""
    STANDBY = 0
    NORMAL = 1
    STRIPMAP = 2
    SPOTLIGHT = 3
    SCANSAR = 4
    INTERFEROMETRIC = 5
    DOPPLER_BEAM = 6

class aewc_radarMode(Enum):
    """AEWC radar mode enumeration."""
    STANDBY = 0
    NORMAL = 1
    SEARCH = 2
    TRACK = 3
    SURVEILLANCE = 4  # Added SURVEILLANCE mode
    SECTOR_SCAN = 5
    STEALTH_DETECTION = 6
    ELECTRONIC_PROTECTION = 7

class tfr_radarMode(Enum):
    """TFR radar mode enumeration."""
    STANDBY = 0
    NORMAL = 1
    SEARCH = 2
    TRACK = 3
    ACTIVE = 4     # Added ACTIVE mode
    TERRAIN_FOLLOWING = 5
    OBSTACLE_AVOIDANCE = 6
    GROUND_MAPPING = 7

class RadarMode(Enum):
    """Generic radar mode enumeration."""
    STANDBY = 0
    NORMAL = 1
    ACTIVE = 2
    SEARCH = 3
    TRACK = 4
