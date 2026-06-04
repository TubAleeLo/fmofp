import sys
import FMOFP.Utils.common.fetching as fetching
from FMOFP.local_messaging.Messaging import Messaging
from FMOFP.Utils.logger.sys_logger import sys_logger

class OxygenControl:
    def __init__(self):
        self.messaging = Messaging()
        self.logger = sys_logger("OxygenControl")
        self.oxygen_level = 21.0  # Normal atmospheric oxygen level
        self.oxygen_generation_rate = 1.0  # L/min

    def generate_oxygen(self):
        self.logger.info(f"Generating oxygen at {self.oxygen_generation_rate} L/min")
        # Simulating oxygen generation
        self.oxygen_level += 0.1  # Increase oxygen level slightly
        if self.oxygen_level > 23.0:
            self.oxygen_level = 23.0  # Cap at 23% to prevent hyperoxia
        self.messaging.send_message("ECS", "Oxygen generated", {"new_oxygen_level": self.oxygen_level})

    def adjust_generation_rate(self, new_rate):
        self.logger.info(f"Adjusting oxygen generation rate from {self.oxygen_generation_rate} to {new_rate} L/min")
        self.oxygen_generation_rate = new_rate

    def get_oxygen_status(self):
        return {
            "oxygen_level": self.oxygen_level,
            "generation_rate": self.oxygen_generation_rate
        }

    def handle_message(self, message):
        if message.get("type") == "generate_oxygen":
            self.generate_oxygen()
        elif message.get("type") == "adjust_generation_rate":
            self.adjust_generation_rate(message["new_rate"])
        elif message.get("type") == "get_status":
            return self.get_oxygen_status()