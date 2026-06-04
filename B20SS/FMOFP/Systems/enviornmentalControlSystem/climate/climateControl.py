import sys
import FMOFP.Utils.common.fetching as fetching
from FMOFP.local_messaging.Messaging import Messaging
from FMOFP.Utils.logger.sys_logger import sys_logger

class ClimateControl:
    def __init__(self):
        self.messaging = Messaging()
        self.logger = sys_logger("ClimateControl")
        self.current_temperature = 22.0
        self.current_humidity = 50.0

    def adjust_temperature(self, target_temperature):
        self.logger.info(f"Adjusting temperature from {self.current_temperature}°C to {target_temperature}°C")
        # Simulating temperature adjustment
        self.current_temperature = target_temperature
        self.messaging.send_message("ECS", "Temperature adjusted", {"new_temperature": self.current_temperature})

    def adjust_humidity(self, target_humidity):
        self.logger.info(f"Adjusting humidity from {self.current_humidity}% to {target_humidity}%")
        # Simulating humidity adjustment
        self.current_humidity = target_humidity
        self.messaging.send_message("ECS", "Humidity adjusted", {"new_humidity": self.current_humidity})

    def get_climate_status(self):
        return {
            "temperature": self.current_temperature,
            "humidity": self.current_humidity
        }

    def handle_message(self, message):
        if message.get("type") == "adjust_temperature":
            self.adjust_temperature(message["target_temperature"])
        elif message.get("type") == "adjust_humidity":
            self.adjust_humidity(message["target_humidity"])
        elif message.get("type") == "get_status":
            return self.get_climate_status()