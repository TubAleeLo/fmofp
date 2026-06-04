import Utils.common.fetching as fetching
import xml.etree.ElementTree as ET
from FMOFP.Utils.logger.sys_logger import get_logger

logger = get_logger()

class FuelSystemController:
    def __init__(self):

        
        tree = ET.parse("Systems/fuelSystems/fuelConfig.xml")
        config = tree.getroot()
        
        self.tanks = []
        for tank in config.findall("tanks/tank"):
            tank_id = int(tank.find("id").text)
            desc = tank.find("description").text
            capacity = int(tank.find("capacity").text)
            self.tanks.append({"id": tank_id, "description": desc, "capacity": capacity})
            
        self.refuel_ports = []
        for port in config.findall("refueling/port"):
            port_id = int(port.find("id").text)
            desc = port.find("description").text
            for tank_id in [int(t.text) for t in port.find("tanks")]:
                self.refuel_ports.append({"id": port_id, "description": desc, "tank": self.get_tank(tank_id)})
                
        self.feed_lines = []
        for line in config.findall("feedLines/line"):
            from_tank = self.get_tank(int(line.find("fromTank").text))
            to_engine = int(line.find("toEngine").text)
            self.feed_lines.append({"from": from_tank, "to": to_engine})
                
    def get_tank(self, tank_id):
        return next((t for t in self.tanks if t["id"] == tank_id), None) 
               
    def monitor_fuel_levels(self):
        for tank in self.tanks:
            current_level = 85 # Simulate current fuel level
            logger.info(f"{tank['description']} - {current_level}% full ({int(current_level * tank['capacity'] / 100)} gal)") 
               
    def perform_refuel(self):
        for port in self.refuel_ports:
            logger.info(f"Refueling from {port['description']}")
            # Simulate refuel sequence
               
    def control_feed_lines(self, command):
        if command == "open":
            for line in self.feed_lines:
                logger.info(f"Opening feed line from {line['from']['description']} to engine {line['to']}")
                # Open feed line valve
        elif command == "close":
            logger.info("Closing all feed line valves")
            # Close all feed line valves
            
    def run(self):
        self.monitor_fuel_levels()
        self.perform_refuel()
        self.control_feed_lines("open")
        
if __name__ == "__main__":
    controller = FuelSystemController()
    controller.run()