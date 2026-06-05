"""
Mission Planning Service

Wraps MissionPlanningSystem, RouteManagement, OrderOfBattle, and Targeting
into a single service that:
  - Starts the mission data update loop
  - Persists state via current DBM API
  - Exposes get_data() for MFD mission page and TSD
  - Singleton: get_mission_service()
"""

import threading
import time
import json
from typing import Dict, Any, List, Optional

from FMOFP.Utils.logger.sys_logger import get_logger

logger = get_logger()

_mission_service = None


class MissionService:
    def __init__(self):
        self._lock    = threading.Lock()
        self._running = threading.Event()
        self._thread  = None
        self._db      = None
        self._init_db()

        # Mission state
        self._phase      = 'PLANNING'
        self._waypoints: List[Dict] = []
        self._targets:   List[Dict] = []
        self._threats:   List[Dict] = []
        self._current_position = {'lat': 35.4147, 'lon': -97.3866, 'alt_ft': 1290.6}
        self._active_waypoint_idx = 0

        # Import and initialise MissionPlanningSystem if available
        self._mps = None
        try:
            from FMOFP.Systems.missionPlanning.missionControl import MissionPlanningSystem
            self._mps = MissionPlanningSystem()
            logger.info("[MISSION] MissionPlanningSystem attached")
        except Exception as e:
            logger.warning(f"[MISSION] MissionPlanningSystem unavailable: {e}")

    def _init_db(self):
        try:
            from FMOFP.storage.DBM import DatabaseManager
            db_manager = DatabaseManager('FMOFP/dbConfig.xml')
            self._db = db_manager.get_system_db('mission_management_system')
            self._db.create_table('mission_data', {
                'id':        'INTEGER PRIMARY KEY AUTOINCREMENT',
                'timestamp': 'REAL NOT NULL',
                'phase':     'TEXT NOT NULL',
                'data':      'TEXT NOT NULL',
            })
            logger.info("[MISSION] Database initialised")
        except Exception as e:
            logger.warning(f"[MISSION] DB init failed (non-fatal): {e}")

    def _update(self):
        """Sync position from FMS if available."""
        try:
            from FMOFP.Systems.flightManagementSys.flightManagementSystem import get_flightManagementSystem
            fms = get_flightManagementSystem()
            fd  = fms.get_flight_data()
            nav = fd.get('navigation', {})
            if nav:
                with self._lock:
                    self._current_position = {
                        'lat':    nav.get('latitude',  self._current_position['lat']),
                        'lon':    nav.get('longitude', self._current_position['lon']),
                        'alt_ft': nav.get('altitude',  self._current_position['alt_ft']),
                    }
                    if self._mps:
                        self._mps.update_current_position(
                            self._current_position['lat'],
                            self._current_position['lon'],
                            self._current_position['alt_ft'],
                        )
        except Exception:
            pass   # FMS not yet ready — silent

    def _persist(self):
        if self._db is None:
            return
        try:
            with self._lock:
                snapshot = {
                    'position':  self._current_position,
                    'waypoints': self._waypoints,
                    'targets':   self._targets,
                    'threats':   self._threats,
                }
            self._db.insert_into_table('mission_data', {
                'timestamp': time.time(),
                'phase':     self._phase,
                'data':      json.dumps(snapshot),
            })
        except Exception as e:
            logger.debug(f"[MISSION] DB insert skipped: {e}")

    def _update_loop(self):
        logger.info("[MISSION] Update loop started")
        while not self._running.is_set():
            try:
                self._update()
                self._persist()
            except Exception as e:
                logger.error(f"[MISSION] Update error: {e}")
                time.sleep(5)
                continue
            time.sleep(1.0)

    # ------------------------------------------------------------------ public API

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._running.clear()
        self._thread = threading.Thread(target=self._update_loop, daemon=True, name="MISSION_Update")
        self._thread.start()
        logger.info("[MISSION] Mission service started")

    def stop(self):
        self._running.set()
        if self._thread:
            self._thread.join(timeout=2)
        logger.info("[MISSION] Mission service stopped")

    def get_data(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'phase':            self._phase,
                'current_position': dict(self._current_position),
                'waypoints':        list(self._waypoints),
                'targets':          list(self._targets),
                'threats':          list(self._threats),
                'active_waypoint':  self._active_waypoint_idx,
            }

    def get_status(self) -> Dict[str, Any]:
        return {'running': self._thread is not None and self._thread.is_alive(),
                'healthy': True, **self.get_data()}

    def add_waypoint(self, lat: float, lon: float, alt_ft: float, name: str = ''):
        with self._lock:
            wp = {'id': len(self._waypoints), 'lat': lat, 'lon': lon,
                  'alt_ft': alt_ft, 'name': name}
            self._waypoints.append(wp)
        if self._mps:
            self._mps.add_waypoint(lat, lon, alt_ft)

    def add_target(self, lat: float, lon: float, priority: int = 1, name: str = ''):
        with self._lock:
            self._targets.append({'id': len(self._targets), 'lat': lat,
                                  'lon': lon, 'priority': priority, 'name': name,
                                  'status': 'PENDING'})

    def set_phase(self, phase: str):
        valid = ('PLANNING', 'INGRESS', 'OBJECTIVE', 'EGRESS', 'COMPLETE')
        if phase in valid:
            with self._lock:
                self._phase = phase
            logger.info(f"[MISSION] Phase → {phase}")


def get_mission_service() -> MissionService:
    global _mission_service
    if _mission_service is None:
        _mission_service = MissionService()
    return _mission_service
