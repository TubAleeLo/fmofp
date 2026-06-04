import Utils.common.fetching as fetching
import xml.etree.ElementTree as ET
from FMOFP.Utils.logger.sys_logger import get_logger

logger = get_logger()

class AirframeSystemManager:
    def __init__(self):

        
        tree = ET.parse("Systems/airframeSystemManagement/asmConfig.xml")
        config = tree.getroot()
        
        self.subsystems = []
        for subsys in config.findall("subsystems/subsystem"):
            name = subsys.find("name").text
            desc = subsys.find("description").text
            self.subsystems.append({"name": name, "description": desc})
            
        self.sensors = []
        for sensor in config.findall("sensors/sensor"):
            sensor_id = int(sensor.find("id").text)
            type = sensor.find("type").text
            location = sensor.find("location").text
            self.sensors.append({"id": sensor_id, "type": type, "location": location})
            
    def monitor_airframe(self):
        # Simulate getting sensor data
        for sensor in self.sensors:
            value = 25 # Replace with actual sensor reading
            logger.info(f"Sensor {sensor['id']} ({sensor['location']}) - {sensor['type']}: {value}")
            
        # Check sensor values, update subsystem status
        
    def control_landing_gear(self, command):
        if command == "deploy":
            logger.info("Deploying landing gear")
            # Activate landing gear deployment sequence
        elif command == "retract":
            logger.info("Retracting landing gear") 
            # Activate landing gear retraction sequence
            
    def run(self):
        while True:
            self.monitor_airframe()
            
            # Simulate getting landing gear command           
            self.control_landing_gear("deploy")
               
if __name__ == "__main__":
    manager = AirframeSystemManager()
    manager.run()