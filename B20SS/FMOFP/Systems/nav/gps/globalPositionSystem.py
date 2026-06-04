import sys
import os
import math
from collections import deque
from datetime import datetime, timedelta
from typing import List, Tuple
import threading
import time
import Utils.common.fetching as fetching
from FMOFP.MIL_STD_1553B.Messaging import BusControllerModule, ScheduleMessage
from storage.DBM import DatabaseManager
from FMOFP.Utils.logger.sys_logger import get_logger

logger = get_logger()

class Satellite:
    def __init__(self, id: int, position: Tuple[float, float, float], clock_bias: float):
        self.id = id
        self.position = position
        self.clock_bias = clock_bias

class GPSReceiver:
    def __init__(self):
        self.position = (0, 0, 0)
        self.clock_bias = 0
        self.satellite_data = deque(maxlen=32)  # Store data from up to 32 satellites
        self.ephemeris_data = {}
        self.almanac_data = {}
        self.db = DatabaseManager('system_data.db')  
        self.bcm = BusControllerModule()
        self.last_known_position = None

    def update_satellite_data(self, satellite: Satellite):
        self.satellite_data.append(satellite)
        self.db.insert_data('satellite_data', {
            'satellite_id': satellite.id,
            'position_x': satellite.position[0],
            'position_y': satellite.position[1],
            'position_z': satellite.position[2],
            'clock_bias': satellite.clock_bias
        })

    def update_ephemeris(self, satellite_id: int, ephemeris: dict):
        self.ephemeris_data[satellite_id] = ephemeris
        self.db.insert_data('ephemeris_data', {
            'satellite_id': satellite_id,
            'ephemeris': str(ephemeris)  # Convert dict to string for storage
        })

    def update_almanac(self, almanac: dict):
        self.almanac_data.update(almanac)
        self.db.insert_data('almanac_data', {
            'almanac': str(almanac)  # Convert dict to string for storage
        })

    def calculate_pseudo_range(self, satellite: Satellite) -> float:
        dx = satellite.position[0] - self.position[0]
        dy = satellite.position[1] - self.position[1]
        dz = satellite.position[2] - self.position[2]
        geometric_range = math.sqrt(dx**2 + dy**2 + dz**2)
        return geometric_range + self.clock_bias - satellite.clock_bias

    def triangulate_position(self) -> Tuple[float, float, float]:
        if len(self.satellite_data) < 4:
            if self.last_known_position is not None:
                logger.info("Not enough satellites for triangulation, using last known position.")
                return self.last_known_position
            else:
                raise ValueError("Not enough satellites for triangulation and no last known position available.")

        # Implement least squares algorithm for position calculation
        # This is a placeholder for the actual implementation
        x, y, z = 0, 0, 0
        for satellite in self.satellite_data:
            x += satellite.position[0]
            y += satellite.position[1]
            z += satellite.position[2]
        n = len(self.satellite_data)
        self.last_known_position = (x/n, y/n, z/n)
        return self.last_known_position

    def send_position_update(self):
        position = self.triangulate_position()
        # Construct a command word for position update
        command = 0b0010000000010011  # Example command word (RT address 2, subaddress 1, 3 data words)
        data = [int(coord * 1000) for coord in position]  # Convert to millimeters and to integers
        for i, d in enumerate(data):
            self.bcm.sendCommandComms(bin(command)[2:].zfill(16), bin(d)[2:].zfill(16))
            if i < 2:  # Only need to send command word for first data word
                command = 0b0010000000000000  # Subsequent data words use this command

class GPSSystem:
    def __init__(self):
        self.receiver = GPSReceiver()
        self.satellites: List[Satellite] = []
        self.update_interval = timedelta(seconds=1)
        self.last_update = datetime.now()


    def add_satellite(self, satellite: Satellite):
        self.satellites.append(satellite)

    def update_satellites(self):
        for satellite in self.satellites:
            self.receiver.update_satellite_data(satellite)

    def update_position(self):
        try:
            new_position = self.receiver.triangulate_position()
            self.receiver.position = new_position
            self.receiver.db.update_data('gps_position', {'x': new_position[0], 'y': new_position[1], 'z': new_position[2]}, {'id': 1})
            logger.info(f"Updated position: {new_position}")
        except ValueError as e:
            logger.info(f"Position update failed: {str(e)}")

    def send_position_update(self):
        self.receiver.send_position_update()

    def update_almanac(self):
        # Simplified almanac update
        almanac = {'last_update': datetime.now().isoformat()}
        self.receiver.update_almanac(almanac)

    def run(self):
        pass
    
    def stop(self):
        pass

    def get_current_position(self) -> Tuple[float, float, float]:
        return self.receiver.position

# Example usage
if __name__ == "__main__":
    gps_system = GPSSystem()

    # Add some simulated satellites
    gps_system.add_satellite(Satellite(1, (20200000, 0, 0), 0.001))
    gps_system.add_satellite(Satellite(2, (0, 20200000, 0), 0.002))
    gps_system.add_satellite(Satellite(3, (0, 0, 20200000), 0.003))
    gps_system.add_satellite(Satellite(4, (20200000, 20200000, 20200000), 0.004))

    # Start GPS system
    gps_thread = threading.Thread(target=gps_system.run)    # THREAD STARTED IN WRONG PLACE - SHOULD START IN system_manager.py
    gps_thread.start()

    try:
        # Simulate GPS updates
        for _ in range(20):
            position = gps_system.get_current_position()
            logger.info(f"Current position: {position}")
            time.sleep(1)
    finally:
        gps_system.stop()
        gps_thread.join()

    logger.info("GPS system stopped.")
