import math
import random
from enum import Enum
import threading
import time
from typing import List, Tuple, Dict
from typing import Union
import Utils.common.fetching as fetching
from storage.DBM import DatabaseManager
from FMOFP.MIL_STD_1553B.Messaging import ScheduleMessage
from FMOFP.Utils.logger.sys_logger import get_logger

logger = get_logger()

class MissionPhase(Enum):
    PLANNING = 1
    INGRESS = 2
    OBJECTIVE = 3
    EGRESS = 4
    COMPLETE = 5

class Waypoint:
    def __init__(self, id: int, lat: float, lon: float, alt: float):
        self.id = id
        self.lat = lat
        self.lon = lon
        self.alt = alt

class Target:
    def __init__(self, id: int, lat: float, lon: float, priority: int):
        self.id = id
        self.lat = lat
        self.lon = lon
        self.priority = priority
        self.status = "Pending"

class Threat:
    def __init__(self, id: int, lat: float, lon: float, threat_level: int):
        self.id = id
        self.lat = lat
        self.lon = lon
        self.threat_level = threat_level

class MissionPlanningSystem:
    def __init__(self):
        self.phase = MissionPhase.PLANNING
        self.waypoints: List[Waypoint] = []
        self.targets: Dict[int, Target] = {}
        self.threats: Dict[int, Threat] = {}
        self.current_position = (35.414750000000004, -97.3866388888889, 1290.6)  # lat, lon, alt
        self.lock = threading.Lock()
        self.db = DatabaseManager('system_data.db', 'B20SS')
        self.message_handler = MessageHandler()
        self.aircraft_speed = 500  # km/h, assuming a constant speed for simplicity

    def set_phase(self, phase: MissionPhase):
        with self.lock:
            self.phase = phase
            self.db.update_table('mission_status', {'phase': phase.value}, {'id': 1})
            self._send_phase_update()

    def _send_phase_update(self):
        try:
            message = {
                'type': 'mission_phase_update',
                'phase': self.phase.value
            }
            self.message_handler.send_mission_data(message)
        except Exception as e:
            logger.error(f"Failed to send phase update: {e}")

    def add_waypoint(self, lat: float, lon: float, alt: float):
        with self.lock:
            try:
                waypoint_id = len(self.waypoints) + 1
                waypoint = Waypoint(waypoint_id, lat, lon, alt)
                self.waypoints.append(waypoint)
                self.db.insert_data('mission_waypoints', {
                    'id': waypoint_id,
                    'latitude': lat,
                    'longitude': lon,
                    'altitude': alt
                })
                logger.info(f"Added waypoint {waypoint_id}")
            except Exception as e:
                logger.error(f"Failed to add waypoint: {e}")

    def add_target(self, lat: float, lon: float, priority: int):
        with self.lock:
            try:
                target_id = len(self.targets) + 1
                target = Target(target_id, lat, lon, priority)
                self.targets[target_id] = target
                self.db.insert_data('mission_targets', {
                    'id': target_id,
                    'latitude': lat,
                    'longitude': lon,
                    'priority': priority,
                    'status': target.status
                })
                logger.info(f"Added target {target_id}")
            except Exception as e:
                logger.error(f"Failed to add target: {e}")

    def add_threat(self, lat: float, lon: float, threat_level: int):
        with self.lock:
            try:
                threat_id = len(self.threats) + 1
                threat = Threat(threat_id, lat, lon, threat_level)
                self.threats[threat_id] = threat
                self.db.insert_data('mission_threats', {
                    'id': threat_id,
                    'latitude': lat,
                    'longitude': lon,
                    'threat_level': threat_level
                })
                logger.info(f"Added threat {threat_id}")
            except Exception as e:
                logger.error(f"Failed to add threat: {e}")

    def update_current_position(self, lat: float, lon: float, alt: float):
        with self.lock:
            try:
                self.current_position = (lat, lon, alt)
                self.db.update_table('mission_status', {
                    'current_lat': lat,
                    'current_lon': lon,
                    'current_alt': alt
                }, {'id': 1})
            except Exception as e:
                logger.error(f"Failed to update current position: {e}")

    def get_next_waypoint(self) -> Waypoint:
        if not self.waypoints:
            return None
        return min(self.waypoints, key=lambda w: self._calculate_distance(w))


    
    def _calculate_distance(self, point: Union[Waypoint, Target, Threat]) -> float:
        lat1, lon1, _ = self.current_position
        lat2, lon2 = point.lat, point.lon
        return math.sqrt((lat2 - lat1)**2 + (lon2 - lon1)**2)

    def calculate_eta(self, waypoint: Waypoint) -> float:
        distance = self._calculate_distance(waypoint)
        return distance / self.aircraft_speed  # ETA in hours

    def update_target_status(self, target_id: int, status: str):
        with self.lock:
            try:
                if target_id in self.targets:
                    self.targets[target_id].status = status
                    self.db.update_data('mission_targets', {'status': status}, {'id': target_id})
                    logger.info(f"Updated target {target_id} status to {status}")
            except Exception as e:
                logger.error(f"Failed to update target status: {e}")

    def assess_threats(self):
        threat_assessment = {}
        for threat_id, threat in self.threats.items():
            distance = self._calculate_distance(threat)
            threat_assessment[threat_id] = {
                'distance': distance,
                'threat_level': threat.threat_level,
                'risk_factor': threat.threat_level / distance  # Simple risk calculation
            }
        return threat_assessment

    def optimize_route(self):
        # Simple route optimization: sort waypoints by distance and adjust for high-priority targets
        self.waypoints.sort(key=lambda w: self._calculate_distance(w))
        
        # Insert high-priority targets into the route
        for target_id, target in sorted(self.targets.items(), key=lambda x: x[1].priority, reverse=True):
            insert_index = next((i for i, w in enumerate(self.waypoints) if self._calculate_distance(w) > self._calculate_distance(target)), len(self.waypoints))
            self.waypoints.insert(insert_index, Waypoint(target.id, target.lat, target.lon, self.current_position[2]))
        
        # Avoid high-risk areas by adjusting waypoints
        threat_assessment = self.assess_threats()
        for i, waypoint in enumerate(self.waypoints):
            for threat_id, assessment in threat_assessment.items():
                if assessment['risk_factor'] > 0.5:  # Arbitrary threshold
                    # Move waypoint away from the threat
                    waypoint.lat += (waypoint.lat - self.threats[threat_id].lat) * 0.1
                    waypoint.lon += (waypoint.lon - self.threats[threat_id].lon) * 0.1
        
        logger.info("Route optimized based on targets and threats")

    def send_mission_update(self):
        try:
            next_waypoint = self.get_next_waypoint()
            if next_waypoint:
                message = {
                    'type': 'mission_update',
                    'phase': self.phase.value,
                    'next_waypoint': {
                        'id': next_waypoint.id,
                        'lat': next_waypoint.lat,
                        'lon': next_waypoint.lon,
                        'alt': next_waypoint.alt
                    },
                    'eta': self.calculate_eta(next_waypoint)
                }
                self.message_handler.send_mission_data(message)
        except Exception as e:
            logger.error(f"Failed to send mission update: {e}")

class MissionManagementSystem:
    def __init__(self):
        self.mps = MissionPlanningSystem()
        self.running = False
        self.update_interval = 1  # seconds
        self.thread = None
        

    def run(self):
        self.running = True


    def stop(self):
        self.running = False


    def update(self):
        while self.running:
            try:
                self.update_position()
                self.check_waypoints()
                self.update_targets()
                self.mps.send_mission_update()
                time.sleep(self.update_interval)
            except Exception as e:
                logger.error(f"Error in mission management update: {e}")

    def update_position(self):
        # Simulate position updates (in a real system, this would come from the GPS)
        lat, lon, alt = self.mps.current_position
        lat += random.uniform(-0.0001, 0.0001)
        lon += random.uniform(-0.0001, 0.0001)
        alt += random.uniform(-10, 10)
        self.mps.update_current_position(lat, lon, alt)

    def check_waypoints(self):
        next_waypoint = self.mps.get_next_waypoint()
        if next_waypoint:
            distance = self.mps._calculate_distance(next_waypoint)
            if distance < 0.001:  # If within 100 meters of the waypoint
                self.mps.waypoints.remove(next_waypoint)
                logger.info(f"Reached waypoint {next_waypoint.id}")
                if not self.mps.waypoints:
                    self.mps.set_phase(MissionPhase.OBJECTIVE)

    def update_targets(self):
        for target in self.mps.targets.values():
            if target.status == "Pending" and random.random() < 0.1:  # 10% chance to engage a target
                self.mps.update_target_status(target.id, "Engaged")
                logger.info(f"Engaged target {target.id}")

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self.update)   # THREAD STARTED IN WRONG PLACE - SHOULD START IN system_manager.py
        self.thread.start()
        logger.info("Mission Management System started.")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()
        logger.info("Mission Management System stopped.")

    def set_phase(self, phase: MissionPhase):
        self.mps.set_phase(phase)

    def add_waypoint(self, lat: float, lon: float, alt: float):
        self.mps.add_waypoint(lat, lon, alt)

    def add_target(self, lat: float, lon: float, priority: int):
        self.mps.add_target(lat, lon, priority)

    def add_threat(self, lat: float, lon: float, threat_level: int):
        self.mps.add_threat(lat, lon, threat_level)

    def optimize_route(self):
        self.mps.optimize_route()

# Example usage
if __name__ == "__main__":
    mms = MissionManagementSystem()
    mms.start()
    
    # Add some example waypoints, targets, and threats
    mms.add_waypoint(35.4148, -97.3867, 1300)
    mms.add_waypoint(35.4150, -97.3870, 1350)
    mms.add_target(35.4149, -97.3868, 2)
    mms.add_threat(35.4151, -97.3869, 3)
    
    mms.optimize_route()
    
    # Let the system run for a while
    time.sleep(30)
    
    mms.stop()
