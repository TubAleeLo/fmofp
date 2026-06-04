import os
import sys
import Utils.common.fetching as fetching
import random
import time
import threading
import json    # CHANGE TO XML
from storage.DBM import DatabaseManager
from FMOFP.Utils.logger.sys_logger import get_logger

logger = get_logger()

class PowerManagementSystem:
    def __init__(self):
        self.aircraft = 'aircraft'
        self.db_name = "system_data.db"
        self.key = "B20SS"
        self.pms_data = {}
        self.running = threading.Event()
        self.lock = threading.Lock()
        self.main_battery_charge = 100  # Main battery charge in percentage
        self.aux_battery_charge = 100  # Auxiliary battery charge in percentage
        self.generator_output = 0  # Generator output in kW
        self.total_power_consumption = 0  # Total power consumption in kW
        self.db = DatabaseManager(self.db_name, self.key)
        self._setup_database()
        self.thread = None

        # Initialize messaging
        #self.message_handler = MessageHandler()

    def _setup_database(self):
        try:
            table_name = 'pms_data'
            received_from = 'power_management_sensors'
            information_type = 'power_management_data'
            field_data_dict = {'id': 'INTEGER PRIMARY KEY', 'data': 'TEXT'}
            
            if table_name is not None and received_from is not None and information_type is not None and field_data_dict is not None:
                self.db.create_table(table_name, received_from, information_type, field_data_dict)
            else:
                logger.warning("Skipping create_table call due to None values")
        except Exception as e:
            logger.error(f"Database setup failed: {e}")

    def adjust_power_parameters(self):
        with self.lock:
            # Simulate power generation and consumption
            self.generator_output = random.uniform(200, 250)  # Generator output between 200-250 kW
            self.total_power_consumption = random.uniform(180, 220)  # Total consumption between 180-220 kW

            # Battery charge/discharge based on power balance
            power_balance = self.generator_output - self.total_power_consumption
            battery_charge_rate = power_balance / 10  # Arbitrary scaling factor

            self.main_battery_charge += battery_charge_rate
            self.aux_battery_charge += battery_charge_rate / 2  # Aux battery charges/discharges at half the rate

            # Ensure battery charges are within limits
            self.main_battery_charge = max(0, min(100, self.main_battery_charge))
            self.aux_battery_charge = max(0, min(100, self.aux_battery_charge))

    def monitor(self):
        with self.lock:
            self.pms_data = {
                'main_battery_charge': round(self.main_battery_charge, 2),
                'aux_battery_charge': round(self.aux_battery_charge, 2),
                'generator_output': round(self.generator_output, 2),
                'total_power_consumption': round(self.total_power_consumption, 2),
                'power_balance': round(self.generator_output - self.total_power_consumption, 2),
                'main_bus_voltage': random.uniform(110, 120),  # Main bus voltage (assuming 115V system)
                'aux_bus_voltage': random.uniform(25, 28),  # Auxiliary bus voltage (assuming 28V system)
                'generator_frequency': random.uniform(398, 402),  # Generator frequency (assuming 400Hz system)
                'power_factor': random.uniform(0.95, 1),  # Power factor
            }

    def update(self):
        while not self.running.is_set():
            try:
                self.adjust_power_parameters()
                self.monitor()
                with self.lock:
                    self.db.insert_into_table('pms_data', {'data': json.dumps(self.pms_data)})
            except Exception as e:
                logger.error(f"PMS monitoring failed: {e}")
                time.sleep(5)
            else:
                time.sleep(1)  # Update every second

    def start(self):
        if self.thread is None or not self.thread.is_alive():
            self.running.clear()
            self.thread = threading.Thread(target=self.update)      # THREAD STARTED IN WRONG PLACE - SHOULD START IN system_manager.py
            self.thread.start()
            logger.info("Power Management System started.")

    def stop(self):
        self.running.set()
        if self.thread is not None:
            self.thread.join()
            logger.info("Power Management System stopped.")

    def get_data(self):
        with self.lock:
            return self.pms_data

    def set_generator_output(self, output):
        with self.lock:
            self.generator_output = max(0, output)
            logger.info(f"Generator output set to {self.generator_output} kW.")

    def receive_message(self):
        message = self.message_handler.receive_message()
        if message:
            self._process_received_message(message)

    def _process_received_message(self, message):
        # Process the received message
        logger.info(f"Received message: {message}")
        # Here you would typically parse the message and take appropriate action
        # For example, adjusting power distribution based on commands

# Example usage
if __name__ == "__main__":
    pms = PowerManagementSystem()
    pms.start()
    pms.monitor()
    pms.receive_message()
    pms.stop()