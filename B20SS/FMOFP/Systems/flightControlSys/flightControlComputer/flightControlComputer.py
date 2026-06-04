import Utils.common.fetching as fetching
import random
import time
import threading
import json        # CHANGE TO XML
from storage.DBM import DatabaseManager
from FMOFP.MIL_STD_1553B.Messaging import ScheduleMessage
from FMOFP.MIL_STD_1553B.mil_std_1553B  import MIL_STD_1553B_Message
from FMOFP.Utils.logger.sys_logger import get_logger

logger = get_logger()

class FlightControlComputer:
    def __init__(self):
        self.aircraft = 'aircraft'
        self.db_name = "system_data.db"
        self.key = "B20SS"
        self.fcs_data = {}
        self.running = threading.Event()
        self.lock = threading.Lock()
        self.altitude = 10000  # Default altitude in feet
        self.speed = 500  # Default speed in knots
        self.heading = 0  # Default heading in degrees
        self.pitch = 0  # Default pitch in degrees
        self.roll = 0  # Default roll in degrees
        self.db = DatabaseManager(self.db_name, self.key)
        self._setup_database()
        self.thread = None

        # Initialize messaging
        self.messaging = ScheduleMessage()
        self.rt_address = 4  # Assign a unique RT address for the Flight Control Computer

    def _setup_database(self):
        try:
            table_name = 'fcs_data'
            received_from = 'flight_control_sensors'
            information_type = 'flight_control_data'
            field_data_dict = {'id': 'INTEGER PRIMARY KEY', 'data': 'TEXT'}
            
            if table_name is not None and received_from is not None and information_type is not None and field_data_dict is not None:
                self.db.create_table(table_name, received_from, information_type, field_data_dict)
            else:
                logger.warning("Skipping create_table call due to None values")
        except Exception as e:
            logger.error(f"Database setup failed: {e}")

    def adjust_flight_parameters(self):
        with self.lock:
            self.altitude += random.uniform(-50, 50)
            self.speed += random.uniform(-5, 5)
            self.heading += random.uniform(-1, 1)
            self.pitch += random.uniform(-0.5, 0.5)
            self.roll += random.uniform(-0.5, 0.5)

            # Ensure values are within realistic ranges
            self.altitude = max(0, min(60000, self.altitude))
            self.speed = max(100, min(1000, self.speed))
            self.heading = self.heading % 360
            self.pitch = max(-45, min(45, self.pitch))
            self.roll = max(-60, min(60, self.roll))

    def monitor(self):
        with self.lock:
            self.fcs_data = {
                'altitude': round(self.altitude, 2),
                'speed': round(self.speed, 2),
                'heading': round(self.heading, 2),
                'pitch': round(self.pitch, 2),
                'roll': round(self.roll, 2),
                'vertical_speed': random.uniform(-500, 500),  # Vertical speed in feet per minute
                'angle_of_attack': random.uniform(0, 15),  # Angle of attack in degrees
                'g_force': random.uniform(0.8, 1.2),  # G-force
                'flaps_position': random.randint(0, 30),  # Flaps position in degrees
                'landing_gear': random.choice(['up', 'down']),  # Landing gear status
            }
            self.send_fcs_data(self.fcs_data)

    def send_fcs_data(self, fcs_data):
        message = MIL_STD_1553B_Message(self.rt_address, 0, fcs_data)
        #self.messaging.send_message(message)

    def update(self):
        while not self.running.is_set():
            try:
                self.adjust_flight_parameters()
                self.monitor()
                with self.lock:
                    self.db.insert_into_table('fcs_data', {'data': json.dumps(self.fcs_data)})
            except Exception as e:
                logger.error(f"FCS monitoring failed: {e}")
                time.sleep(5)
            else:
                time.sleep(0.1)  # Update more frequently for flight controls

    def start(self):
        if self.thread is None or not self.thread.is_alive():
            self.running.clear()
            self.thread = threading.Thread(target=self.update)   # THREAD STARTED IN WRONG PLACE - SHOULD START IN system_manager.py
            self.thread.start()
            logger.info("Flight Control System started.")

    def stop(self):
        self.running.set()
        if self.thread is not None:
            self.thread.join()
            logger.info("Flight Control System stopped.")

    def get_data(self):
        with self.lock:
            return self.fcs_data

    def set_altitude(self, altitude):
        with self.lock:
            self.altitude = altitude
            logger.info(f"Altitude set to {altitude} feet.")

    def set_speed(self, speed):
        with self.lock:
            self.speed = speed
            logger.info(f"Speed set to {speed} knots.")

    def set_heading(self, heading):
        with self.lock:
            self.heading = heading % 360
            logger.info(f"Heading set to {self.heading} degrees.")

    def receive_message(self):
        message = self.messaging.receive_message()
        if message:
            self._process_received_message(message)

    def _process_received_message(self, message):
        # Extract the data from the MIL-STD-1553B_Message
        data = message.data
        
        # Process the received message data
        if 'altitude' in data:
            self.set_altitude(data['altitude'])
        if 'speed' in data:
            self.set_speed(data['speed'])
        if 'heading' in data:
            self.set_heading(data['heading'])
        # Handle other parameters as needed

# Example usage
if __name__ == "__main__":
    fcs = FlightControlComputer()
    fcs.start()
    fcs.monitor()
    fcs.receive_message()
    fcs.stop()
