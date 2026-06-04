"""
Radar-to-Display Bridge
=======================

Provides a direct, synchronous path from weather-radar data handlers into the
RadarDisplayDataCoordinator that sits inside the UI layer.

WHY THIS EXISTS
---------------
The original flow tried to push radar data back through the MIL-STD-1553B
Remote-Terminal sender (RT → BC direction) and then rely on a chain of async
routing services to land in the coordinator.  That chain has two problems:

1.  The RT sender sends *toward* the Bus Controller, not toward the display.
    Data was never actually arriving at the coordinator.

2.  The VILResponseService → DisplayMessageHandler → MessageRoutingService
    → VILResponseService path creates a message loop that the loop-prevention
    decorators eventually kill, silently dropping the data.

This bridge short-circuits both problems by importing the coordinator directly.
It is intentionally framework-agnostic (no asyncio, no Qt) so it can be called
from any thread.

USAGE
-----
    from FMOFP.local_messaging.routing.radar_to_display_bridge import (
        push_vil_data, push_precipitation_data
    )

    push_vil_data(vil_objects, request_id)
    push_precipitation_data(precip_objects, request_id)

Both functions accept either a list of WeatherRadarVILData / PrecipitationData
objects OR a list of plain dictionaries that already contain the required keys.
"""

import time
import traceback
from typing import Any, List

from FMOFP.Utils.logger.sys_logger import get_logger

logger = get_logger()

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_coordinator():
    """Lazily import and return the RadarDisplayDataCoordinator singleton."""
    try:
        from FMOFP.Interfaces.userInterface.displays.radar.radar_display_data_coordinator import (
            get_radar_display_data_coordinator,
        )
        return get_radar_display_data_coordinator()
    except Exception as exc:
        logger.error(f"[BRIDGE] Cannot import RadarDisplayDataCoordinator: {exc}")
        return None


def _object_to_dict(item: Any, data_type: str) -> dict:
    """
    Convert a data object (WeatherRadarVILData, PrecipitationData, or plain
    dict) to the dictionary format expected by the coordinator.
    """
    if isinstance(item, dict):
        return item  # already the right format

    d: dict = {}

    # --- position ---
    if hasattr(item, "position"):
        pos = item.position
        if hasattr(pos, "tolist"):
            d["position"] = tuple(pos.tolist())
        elif isinstance(pos, (list, tuple)) and len(pos) >= 2:
            d["position"] = tuple(pos)
        else:
            d["position"] = (0.0, 0.0)
    elif hasattr(item, "x") and hasattr(item, "y"):
        d["position"] = (float(item.x), float(item.y))
    else:
        d["position"] = (0.0, 0.0)

    # --- id ---
    if hasattr(item, "id") and item.id:
        d["id"] = item.id
    elif hasattr(item, "request_id") and item.request_id:
        d["id"] = item.request_id

    # --- timestamp ---
    d["timestamp"] = getattr(item, "timestamp", time.time())

    # --- type-specific fields ---
    if data_type == "vil":
        d["value"] = float(getattr(item, "value", 0.0))
        d["layer_count"] = int(getattr(item, "layer_count", 1))
        d["intensity"] = float(getattr(item, "intensity", 0.5))
        d["show_values"] = bool(getattr(item, "show_values", True))

    elif data_type == "precipitation":
        raw_type = getattr(item, "type", None) or getattr(item, "precip_type", "rain")
        d["type"] = raw_type
        d["precip_type"] = raw_type
        d["rate"] = float(getattr(item, "rate", 0.0))
        d["intensity"] = float(getattr(item, "intensity", 0.5))
        d["show_values"] = bool(getattr(item, "show_values", True))

    return d


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def push_vil_data(vil_objects: List[Any], request_id: str) -> bool:
    """
    Push a list of VIL data objects/dicts directly into the display coordinator.

    Args:
        vil_objects:  List of WeatherRadarVILData instances or dicts.
        request_id:   The originating request UUID (required by coordinator).

    Returns:
        True if at least one item was stored, False otherwise.
    """
    if not vil_objects:
        logger.warning("[BRIDGE] push_vil_data called with empty list — nothing to store")
        return False

    if not request_id:
        logger.error("[BRIDGE] push_vil_data called without request_id — cannot store")
        return False

    coordinator = _get_coordinator()
    if coordinator is None:
        return False

    try:
        # Convert objects to dicts and stamp IDs
        processed = []
        for i, item in enumerate(vil_objects):
            d = _object_to_dict(item, "vil")
            if "id" not in d or not d["id"]:
                d["id"] = f"{request_id}_{i}"
            processed.append(d)

        count = coordinator.store_data("vil", processed, request_id)
        logger.info(f"[BRIDGE] Stored {count} VIL items for request {request_id}")
        return count > 0

    except Exception as exc:
        logger.error(f"[BRIDGE] Error pushing VIL data: {exc}")
        logger.error(traceback.format_exc())
        return False


def push_precipitation_data(precip_objects: List[Any], request_id: str) -> bool:
    """
    Push a list of precipitation data objects/dicts directly into the display
    coordinator.

    Args:
        precip_objects:  List of PrecipitationData instances or dicts.
        request_id:      The originating request UUID (required by coordinator).

    Returns:
        True if at least one item was stored, False otherwise.
    """
    if not precip_objects:
        logger.warning("[BRIDGE] push_precipitation_data called with empty list — nothing to store")
        return False

    if not request_id:
        logger.error("[BRIDGE] push_precipitation_data called without request_id — cannot store")
        return False

    coordinator = _get_coordinator()
    if coordinator is None:
        return False

    try:
        processed = []
        for i, item in enumerate(precip_objects):
            d = _object_to_dict(item, "precipitation")
            if "id" not in d or not d["id"]:
                d["id"] = f"{request_id}_{i}"
            processed.append(d)

        count = coordinator.store_data("precipitation", processed, request_id)
        logger.info(f"[BRIDGE] Stored {count} precipitation items for request {request_id}")
        return count > 0

    except Exception as exc:
        logger.error(f"[BRIDGE] Error pushing precipitation data: {exc}")
        logger.error(traceback.format_exc())
        return False
