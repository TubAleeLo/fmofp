import Utils.common.fetching as fetching
import random
import time
import threading
import json              # CHANGE TO XML
from storage.DBM import DatabaseManager
from FMOFP.MIL_STD_1553B.Messaging import send1553Msg
from FMOFP.MIL_STD_1553B.mil_std_1553B  import MIL_STD_1553B_Message
from FMOFP.Utils.logger.sys_logger import get_logger

logger = get_logger()

class EngineControlUnit:
    def __init__(self):
        self.aircraft = 'aircraft'
        self.db_name = "system_data.db"
        self.key = "B20SS"
        self.ecu_data = {}
        self.running = threading.Event()
        self.lock = threading.Lock()
        self.thrust = 0  # Thrust in percentage (0-100)
        self.fuel_flow = 0  # Fuel flow in kg/h
        self.engine_temp = 20  # Engine temperature in Celsius
        self.engine_pressure = 1013  # Engine pressure in hPa
        self.db = DatabaseManager(self.db_name, self.key)
        self._setup_database()
        self.thread = None

        # Initialize messaging
        self.messaging = send1553Msg()
        self.rt_address = 2  # Assign a unique RT address for the Engine Control Unit

    def _setup_database(self):
        try:
            table_name = 'ecu_data'
            received_from = 'engine_sensors'
            information_type = 'engine_control_data'
            field_data_dict = {'id': 'INTEGER PRIMARY KEY', 'data': 'TEXT'}
            
            if table_name is not None and received_from is not None and information_type is not None and field_data_dict is not None:
                self.db.create_table(table_name, received_from, information_type, field_data_dict)
            else:
                logger.warning("Skipping create_table call due to None values")
        except Exception as e:
            logger.error(f"Database setup failed: {e}")

    def adjust_engine_parameters(self):
        with self.lock:
            self.thrust += random.uniform(-1, 1)
            self.fuel_flow = self.thrust * 50  # Simple linear relationship
            self.engine_temp += random.uniform(-0.5, 0.5)
            self.engine_pressure += random.uniform(-1, 1)

            # Ensure values are within realistic ranges
            self.thrust = max(0, min(100, self.thrust))
            self.fuel_flow = max(0, self.fuel_flow)
            self.engine_temp = max(0, min(1000, self.engine_temp))
            self.engine_pressure = max(900, min(1100, self.engine_pressure))

    def monitor(self):
        with self.lock:
            self.ecu_data = {
                'thrust': round(self.thrust, 2),
                'fuel_flow': round(self.fuel_flow, 2),
                'engine_temp': round(self.engine_temp, 2),
                'engine_pressure': round(self.engine_pressure, 2),
                'rpm': int(self.thrust * 100),  # RPM increases with thrust
                'exhaust_gas_temp': round(self.engine_temp * 1.5, 2),  # EGT is typically higher than engine temp
                'oil_pressure': random.uniform(30, 70),  # Oil pressure in PSI
                'vibration': random.uniform(0, 5),  # Engine vibration level
                'compressor_efficiency': random.uniform(80, 95),  # Compressor efficiency in percentage
            }
            self.send_ecu_data(self.ecu_data)

    def send_ecu_data(self, ecu_data):
        message = MIL_STD_1553B_Message(self.rt_address, 0, ecu_data)
        self.messaging.send_message(message)

    def update(self):
        while not self.running.is_set():
            try:
                self.adjust_engine_parameters()
                self.monitor()
                with self.lock:
                    self.db.insert_into_table('ecu_data', {'data': json.dumps(self.ecu_data)})
            except Exception as e:
                logger.error(f"ECU monitoring failed: {e}")
                time.sleep(5)
            else:
                time.sleep(0.5)  # Update every half second for responsive engine control

    def start(self):
        if self.thread is None or not self.thread.is_alive():
            self.running.clear()
            self.thread = threading.Thread(target=self.update)   # THREAD STARTED IN WRONG PLACE - SHOULD START IN system_manager.py
            self.thread.start()
            logger.info("Engine Control Unit started.")

    def stop(self):
        self.running.set()
        if self.thread is not None:
            self.thread.join()
            logger.info("Engine Control Unit stopped.")

    def get_data(self):
        with self.lock:
            return self.ecu_data

    def set_thrust(self, thrust):
        with self.lock:
            self.thrust = max(0, min(100, thrust))
            logger.info(f"Thrust set to {self.thrust}%.")

    def receive_message(self):
        message = self.messaging.receive_message()
        if message:
            self._process_received_message(message)

    def _process_received_message(self, message):
        # Extract the data from the MIL-STD-1553B_Message
        data = message.data
        
        # Process the received message data
        logger.info(f"Received message data: {data}")
        # Here you would typically parse the message data and take appropriate action
        # For example, adjusting engine parameters based on commands

# Example usage
if __name__ == "__main__":
    ecu = EngineControlUnit()
    ecu.start()
    ecu.monitor()
    ecu.receive_message()
    ecu.stop()

