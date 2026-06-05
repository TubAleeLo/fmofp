import os
import sys
import Utils.common.fetching as fetching
import random
import time
import threading
import json   # CHANGE TO XML
from FMOFP.storage.DBM import DatabaseManager

from FMOFP.Utils.logger.sys_logger import get_logger

logger = get_logger()

class SatCom:
    def __init__(self):
        self.aircraft = 'aircraft'
        self.db_name = "system_data.db"
        self.key = "B20SS"
        self.satcom_data = {}
        self.running = threading.Event()
        self.lock = threading.Lock()
        self.connection_status = 'disconnected'
        self.signal_strength = 0
        self.data_rate = 0
        self.latency = 0
        self.satellite_id = None
        self.db = DatabaseManager('FMOFP/dbConfig.xml').get_system_db('comms')
        self._setup_database()
        self.thread = None

        # Initialize messaging
        #self.message_handler = MessageHandler()

    def _setup_database(self):
        try:
            table_name = 'satcom_data'
            received_from = 'satcom_system'
            information_type = 'communication_data'
            field_data_dict = {'id': 'INTEGER PRIMARY KEY', 'data': 'TEXT'}

            if table_name is not None and received_from is not None and information_type is not None and field_data_dict is not None:
                self.db.create_table(table_name, received_from, information_type, field_data_dict)
            else:
                logger.warning("Skipping create_table call due to None values")
        except Exception as e:
            logger.error(f"Database setup failed: {e}")

    def simulate_satcom_parameters(self):
        with self.lock:
            # Simulate connection status changes
            if random.random() < 0.02:  # 2% chance of connection status change
                self.connection_status = random.choice(['connected', 'disconnected', 'acquiring'])

            if self.connection_status == 'connected':
                self.signal_strength = random.uniform(60, 100)  # Signal strength in dB
                self.data_rate = random.uniform(0.1, 2)  # Data rate in Mbps
                self.latency = random.uniform(500, 1000)  # Latency in ms
                if not self.satellite_id:
                    self.satellite_id = f"SAT-{random.randint(1000, 9999)}"
            else:
                self.signal_strength = 0
                self.data_rate = 0
                self.latency = 0
                self.satellite_id = None

    def monitor(self):
        with self.lock:
            self.satcom_data = {
                'connection_status': self.connection_status,
                'signal_strength': round(self.signal_strength, 2),
                'data_rate': round(self.data_rate, 2),
                'latency': round(self.latency, 2),
                'satellite_id': self.satellite_id,
                'elevation_angle': random.uniform(0, 90) if self.connection_status == 'connected' else 0,
                'azimuth_angle': random.uniform(0, 360) if self.connection_status == 'connected' else 0,
                'frequency_band': random.choice(['L', 'Ku', 'Ka']) if self.connection_status == 'connected' else None,
                'bit_error_rate': random.uniform(0, 0.001) if self.connection_status == 'connected' else 0,
            }
#            self.message_handler.send_satcom_data(self.satcom_data)

    def update(self):
        while not self.running.is_set():
            try:
                self.simulate_satcom_parameters()
                self.monitor()
                with self.lock:
                    self.db.insert_into_table('satcom_data', {'data': json.dumps(self.satcom_data)})
            except Exception as e:
                logger.error(f"SatCom monitoring failed: {e}")
                time.sleep(5)
            else:
                time.sleep(1)  # Update every second

    def start(self):
        if self.thread is None or not self.thread.is_alive():
            self.running.clear()
            self.thread = threading.Thread(target=self.update)   # THREAD STARTED IN WRONG PLACE - SHOULD START IN system_manager.py
            self.thread.start()
            logger.info("SatCom system started.")

    def stop(self):
        self.running.set()
        if self.thread is not None:
            self.thread.join()
            logger.info("SatCom system stopped.")

    def get_data(self):
        with self.lock:
            return self.satcom_data

    def send_message(self, message):
        if self.connection_status == 'connected':
            logger.info(f"Sending message via SatCom: {message}")
            # Here you would implement the actual message sending logic
            return True
        else:
            logger.warning("Cannot send message: SatCom not connected")
            return False

    def receive_message(self):
        message = self.message_handler.receive_message()
        if message:
            self._process_received_message(message)

    def _process_received_message(self, message):
        # Process the received message
        logger.info(f"Received SatCom message: {message}")
        # Here you would typically parse the message and take appropriate action
        # For example, updating satcom parameters or forwarding to other systems

    def acquire_satellite(self):
        if self.connection_status != 'connected':
            logger.info("Attempting to acquire satellite...")
            # Simulate satellite acquisition process
            acquisition_time = random.uniform(5, 30)
            time.sleep(acquisition_time)
            if random.random() < 0.8:  # 80% chance of successful acquisition
                self.connection_status = 'connected'
                self.satellite_id = f"SAT-{random.randint(1000, 9999)}"
                logger.info(f"Satellite acquired. Connected to {self.satellite_id}")
                return True
            else:
                logger.warning("Failed to acquire satellite")
                return False
        else:
            logger.info("Already connected to a satellite")
            return True

# Example usage
if __name__ == "__main__":
    satcom = SatCom()
    satcom.start()
    satcom.acquire_satellite()
    satcom.send_message("Test SatCom message")
    satcom.receive_message()
    satcom.stop()
