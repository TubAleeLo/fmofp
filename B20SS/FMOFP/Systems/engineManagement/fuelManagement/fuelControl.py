import threading
import time
import random
from typing import Dict, List
from collections import defaultdict
import Utils.common.fetching as fetching
from FMOFP.storage.DBM import DatabaseManager
from FMOFP.MIL_STD_1553B.Messaging import ScheduleMessage
from FMOFP.MIL_STD_1553B.mil_std_1553B  import MIL_STD_1553B_Message
from FMOFP.Utils.logger.sys_logger import get_logger

logger = get_logger()

class FuelTank:
    def __init__(self, name: str, capacity: float):
        self.name = name
        self.capacity = capacity
        self.current_level = capacity
        self.flow_rate = 0.0

    def consume(self, amount: float) -> float:
        if amount > self.current_level:
            consumed = self.current_level
            self.current_level = 0
        else:
            consumed = amount
            self.current_level -= amount
        return consumed

    def refill(self, amount: float) -> float:
        space_available = self.capacity - self.current_level
        if amount > space_available:
            filled = space_available
            self.current_level = self.capacity
        else:
            filled = amount
            self.current_level += amount
        return filled

class Engine:
    def __init__(self, name: str, max_thrust: float):
        self.name = name
        self.max_thrust = max_thrust
        self.current_thrust = 0.0
        self.fuel_consumption_rate = 0.0

    def set_thrust(self, thrust_percentage: float):
        self.current_thrust = self.max_thrust * (thrust_percentage / 100)
        self.fuel_consumption_rate = self.current_thrust * 0.1  # Simplified fuel consumption model

class FuelSystem:
    def __init__(self):
        self.tanks: Dict[str, FuelTank] = {}
        self.engines: Dict[str, Engine] = {}
        self.fuel_lines: Dict[str, List[str]] = defaultdict(list)
        self.transfer_rates: Dict[str, float] = {}
        self.lock = threading.Lock()
        self.db = DatabaseManager('FMOFP/dbConfig.xml').get_system_db('engine')
        self.messaging = ScheduleMessage()
        self.rt_address = 3  # Assign a unique RT address for the Fuel Management System

    def add_tank(self, name: str, capacity: float):
        self.tanks[name] = FuelTank(name, capacity)
        self.db.insert_into_table('fuel_tanks', {'name': name, 'capacity': capacity, 'current_level': capacity})

    def add_engine(self, name: str, max_thrust: float):
        self.engines[name] = Engine(name, max_thrust)
        self.db.insert_into_table('engines', {'name': name, 'max_thrust': max_thrust})

    def connect_tank_to_engine(self, tank_name: str, engine_name: str, transfer_rate: float):
        self.fuel_lines[tank_name].append(engine_name)
        self.transfer_rates[(tank_name, engine_name)] = transfer_rate
        self.db.insert_into_table('fuel_lines', {'tank_name': tank_name, 'engine_name': engine_name, 'transfer_rate': transfer_rate})

    def set_engine_thrust(self, engine_name: str, thrust_percentage: float):
        if engine_name in self.engines:
            self.engines[engine_name].set_thrust(thrust_percentage)
            self.db.update_table('engines', {'current_thrust': self.engines[engine_name].current_thrust}, {'name': engine_name})

    def transfer_fuel(self, source_tank: str, destination_tank: str, amount: float):
        with self.lock:
            transferred = self.tanks[source_tank].consume(amount)
            self.tanks[destination_tank].refill(transferred)
            self.db.update_table('fuel_tanks', {'current_level': self.tanks[source_tank].current_level}, {'name': source_tank})
            self.db.update_table('fuel_tanks', {'current_level': self.tanks[destination_tank].current_level}, {'name': destination_tank})

    def update(self, delta_time: float):
        with self.lock:
            for tank_name, tank in self.tanks.items():
                for engine_name in self.fuel_lines[tank_name]:
                    engine = self.engines[engine_name]
                    fuel_required = engine.fuel_consumption_rate * delta_time
                    fuel_consumed = tank.consume(fuel_required)
                    if fuel_consumed < fuel_required:
                        logger.info(f"Warning: Engine {engine_name} is not receiving enough fuel from tank {tank_name}")
                    self.db.update_table('fuel_tanks', {'current_level': tank.current_level}, {'name': tank_name})

    def get_fuel_status(self) -> Dict[str, float]:
        return {tank.name: tank.current_level for tank in self.tanks.values()}

    def send_fuel_status(self):
        status = self.get_fuel_status()
        message = MIL_STD_1553B_Message(self.rt_address, 0, status)
        self.messaging.send_message(message)

    def receive_message(self, message):
        data = message.data
        if 'engine_thrust' in data:
            engine_name = data['engine_name']
            thrust_percentage = data['engine_thrust']
            self.set_engine_thrust(engine_name, thrust_percentage)
        elif 'fuel_transfer' in data:
            source_tank = data['source_tank']
            destination_tank = data['destination_tank']
            amount = data['amount']
            self.transfer_fuel(source_tank, destination_tank, amount)

class FuelManagementSystem:
    def __init__(self):
        self.fuel_system = FuelSystem()
        self.running = False
        self.update_interval = 0.1  # seconds

    def setup_aircraft(self):
        # Set up fuel tanks
        self.fuel_system.add_tank("Main Left", 10000)
        self.fuel_system.add_tank("Main Right", 10000)
        self.fuel_system.add_tank("Center", 20000)

        # Set up engines
        self.fuel_system.add_engine("Engine 1", 50000)
        self.fuel_system.add_engine("Engine 2", 50000)

        # Connect tanks to engines
        self.fuel_system.connect_tank_to_engine("Main Left", "Engine 1", 100)
        self.fuel_system.connect_tank_to_engine("Main Right", "Engine 2", 100)
        self.fuel_system.connect_tank_to_engine("Center", "Engine 1", 50)
        self.fuel_system.connect_tank_to_engine("Center", "Engine 2", 50)

    def update_fuel_system(self):
        self.fuel_system.update(self.update_interval)

    def check_fuel_levels(self):
        status = self.fuel_system.get_fuel_status()
        for tank, level in status.items():
            if level < 1000:  # Example threshold
                logger.info(f"Warning: Low fuel level in {tank}: {level}")

    def perform_fuel_transfer(self):
        # Example: transfer fuel from center tank to main tanks if they are low
        status = self.fuel_system.get_fuel_status()
        if status["Center"] > 5000:
            if status["Main Left"] < 5000:
                self.fuel_system.transfer_fuel("Center", "Main Left", 1000)
            if status["Main Right"] < 5000:
                self.fuel_system.transfer_fuel("Center", "Main Right", 1000)

    def run(self):
        self.running = True
        self.scheduler.start()

    def stop(self):
        self.running = False
        self.scheduler.stop()

    def set_engine_thrust(self, engine_name: str, thrust_percentage: float):
        self.fuel_system.set_engine_thrust(engine_name, thrust_percentage)

    def get_fuel_status(self):
        return self.fuel_system.get_fuel_status()

    def transfer_fuel(self, source_tank: str, destination_tank: str, amount: float):
        self.fuel_system.transfer_fuel(source_tank, destination_tank, amount)

# Example usage
if __name__ == "__main__":
    fms = FuelManagementSystem()
    fms.setup_aircraft()

    # Start the fuel management system
    fms_thread = threading.Thread(target=fms.run)    # THREAD STARTED IN WRONG PLACE - SHOULD START IN system_manager.py
    fms_thread.start()

    try:
        # Simulate a flight
        for i in range(100):
            # Randomly adjust engine thrust
            fms.set_engine_thrust("Engine 1", random.uniform(50, 100))
            fms.set_engine_thrust("Engine 2", random.uniform(50, 100))

            # logger.info fuel status every 10 iterations
            if i % 10 == 0:
                logger.info(f"Fuel status: {fms.get_fuel_status()}")

            time.sleep(1)

    finally:
        # Stop the fuel management system
        fms.stop()
        fms_thread.join()

    logger.info("Final fuel status:", fms.get_fuel_status())
