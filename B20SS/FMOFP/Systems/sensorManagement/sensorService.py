"""
Sensor Management Service — Phase 5

Wraps ActiveSensorManager and PassiveSensorManager into a single singleton
that polls at 5 Hz, reads contact counts from RadarDataFusion, and exposes
a get_data() dict consumed by the EICAS avionics section.

Usage:
    from FMOFP.Systems.sensorManagement.sensorService import get_sensor_service
    svc = get_sensor_service()
    svc.start()
    data = svc.get_data()
    svc.stop()
"""

import threading
import time
from typing import Any, Dict, Optional

from FMOFP.Utils.logger.sys_logger import get_logger

logger = get_logger()

# ── patched sensor managers ───────────────────────────────────────────────────
# The existing stubs call self.logger = logger("name") which treats the module-
# level logger as a callable.  We instantiate them here with the bug bypassed.

class _ActiveSensors:
    """Thin wrapper around ActiveSensorManager that survives import errors."""
    def __init__(self):
        self._mgr = None
        try:
            from FMOFP.Systems.sensorManagement.activeSensors.activeSensors import (
                ActiveSensorManager,
            )
            # Patch: bypass broken self.logger = logger("name") call by
            # monkey-patching __init__ to skip that line.
            obj = object.__new__(ActiveSensorManager)
            obj.sensors = {}
            # Manually build the sensors dict that __init__ would have built.
            try:
                from FMOFP.Systems.sensorManagement.activeSensors.activeSensors import (
                    Radar, Lidar,
                )
                obj.sensors = {
                    "main_radar":              Radar("Main Radar", 300_000, 0.95, 10e9),
                    "terrain_following_radar": Radar("Terrain Following Radar", 50_000, 0.99, 15e9),
                    "lidar":                   Lidar("LIDAR", 1_000, 0.99, 1_000_000),
                }
            except Exception as exc:
                logger.debug(f"[SensorService] ActiveSensor sub-import: {exc}")
            self._mgr = obj
        except Exception as exc:
            logger.debug(f"[SensorService] ActiveSensorManager unavailable: {exc}")

    def activate_all(self):
        if self._mgr:
            for name in self._mgr.sensors:
                try:
                    self._mgr.sensors[name].activate()
                except Exception:
                    pass

    def get_statuses(self) -> Dict[str, Any]:
        if not self._mgr:
            return {}
        return {name: s.get_status() for name, s in self._mgr.sensors.items()}


class _PassiveSensors:
    """Thin wrapper around PassiveSensorManager that survives import errors."""
    def __init__(self):
        self._mgr = None
        try:
            from FMOFP.Systems.sensorManagement.passiveSensors.passiveSensors import (
                PassiveSensorManager,
            )
            obj = object.__new__(PassiveSensorManager)
            obj.sensors = {}
            try:
                from FMOFP.Systems.sensorManagement.passiveSensors.passiveSensors import (
                    InfraredSensor, ESMSensor,
                )
                obj.sensors = {
                    "forward_looking_infrared": InfraredSensor(
                        "Forward Looking Infrared", 0.1, 60, (8e-6, 14e-6)),
                    "missile_approach_warning": InfraredSensor(
                        "Missile Approach Warning", 0.05, 360, (3e-6, 5e-6)),
                    "electronic_support_measures": ESMSensor(
                        "Electronic Support Measures", 0.01, 360, (0.5e9, 40e9)),
                }
            except Exception as exc:
                logger.debug(f"[SensorService] PassiveSensor sub-import: {exc}")
            self._mgr = obj
        except Exception as exc:
            logger.debug(f"[SensorService] PassiveSensorManager unavailable: {exc}")

    def activate_all(self):
        if self._mgr:
            for name in self._mgr.sensors:
                try:
                    self._mgr.sensors[name].activate()
                except Exception:
                    pass

    def get_statuses(self) -> Dict[str, Any]:
        if not self._mgr:
            return {}
        return {name: s.get_status() for name, s in self._mgr.sensors.items()}


# ── SensorService ─────────────────────────────────────────────────────────────

class SensorService:
    """
    Singleton sensor orchestration service.

    Polls at 5 Hz (configurable via POLL_HZ).  Reads fused track count from
    RadarDataFusion and combines it with active/passive sensor health into a
    dict returned by get_data().  The dict is consumed by the EICAS avionics
    panel and any other display that needs sensor state.
    """

    POLL_HZ = 5

    def __init__(self):
        self._active   = _ActiveSensors()
        self._passive  = _PassiveSensors()
        self._fusion   = None          # lazy-loaded
        self._lock     = threading.Lock()
        self._stop_evt = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._data: Dict[str, Any] = {
            "active_sensors":  {},
            "passive_sensors": {},
            "fused_track_count": 0,
            "health": "INITIALISING",
        }

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._active.activate_all()
        self._passive.activate_all()
        self._stop_evt.clear()
        self._thread = threading.Thread(
            target=self._poll_loop, daemon=True, name="SensorService"
        )
        self._thread.start()
        logger.info("[SensorService] Started at %d Hz", self.POLL_HZ)

    def stop(self):
        self._stop_evt.set()
        if self._thread:
            self._thread.join(timeout=2)
        logger.info("[SensorService] Stopped")

    # ── public API ────────────────────────────────────────────────────────────

    def get_data(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._data)

    # ── internal ──────────────────────────────────────────────────────────────

    def _lazy_fusion(self):
        if self._fusion is None:
            try:
                from FMOFP.Systems.radarManagement.radar_data_fusion import (
                    get_radar_data_fusion,
                )
                self._fusion = get_radar_data_fusion()
            except Exception as exc:
                logger.debug(f"[SensorService] RadarDataFusion not ready: {exc}")

    def _poll_loop(self):
        interval = 1.0 / self.POLL_HZ
        while not self._stop_evt.is_set():
            try:
                self._update()
            except Exception as exc:
                logger.error(f"[SensorService] Poll error: {exc}")
            self._stop_evt.wait(interval)

    def _update(self):
        active_status  = self._active.get_statuses()
        passive_status = self._passive.get_statuses()

        # Fused track count from RadarDataFusion
        self._lazy_fusion()
        track_count = 0
        try:
            if self._fusion:
                track_count = len(self._fusion.get_fused_tracks())
        except Exception:
            pass

        # Overall health
        active_ok  = all(s.get("is_active") for s in active_status.values()) if active_status else False
        passive_ok = all(s.get("is_active") for s in passive_status.values()) if passive_status else False
        if active_ok and passive_ok:
            health = "NOMINAL"
        elif active_ok or passive_ok:
            health = "DEGRADED"
        else:
            health = "FAULT"

        with self._lock:
            self._data = {
                "active_sensors":    active_status,
                "passive_sensors":   passive_status,
                "fused_track_count": track_count,
                "health":            health,
            }


# ── singleton accessor ────────────────────────────────────────────────────────

_sensor_service: Optional[SensorService] = None
_sensor_lock = threading.Lock()


def get_sensor_service() -> SensorService:
    global _sensor_service
    with _sensor_lock:
        if _sensor_service is None:
            _sensor_service = SensorService()
    return _sensor_service
