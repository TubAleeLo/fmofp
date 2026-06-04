import Utils.common.fetching as fetching
import xml.etree.ElementTree as ET
from FMOFP.Utils.logger.sys_logger import get_logger

logger = get_logger()

class HydraulicSystemController:
    def __init__(self):


        
        tree = ET.parse("Systems/hydraulics/hydrConfig.xml")
        config = tree.getroot()
        
        self.primary_system = {
            "id": int(config.find("primarySystem/id").text),
            "description": config.find("primarySystem/description").text,
            "components": []
        }
        for comp in config.findall("primarySystem/components/component"):
            name = comp.find("name").text
            desc = comp.find("description").text
            self.primary_system["components"].append({"name": name, "description": desc})
            
        self.backup_system = {
            "id": int(config.find("backupSystem/id").text),
            "description": config.find("backupSystem/description").text,
            "components": []
        }
        for comp in config.findall("backupSystem/components/component"):
            name = comp.find("name").text
            desc = comp.find("description").text  
            self.backup_system["components"].append({"name": name, "description": desc})
            
        self.pressure_thresholds = {
            "nominal": int(config.find("nominalPressure").text),
            "warning": int(config.find("warningThreshold").text),
            "critical": int(config.find("criticalThreshold").text)
        }
        
        self.active_system = self.primary_system
        
    def monitor_pressure(self):
        # Simulate getting pressure data
        current_pressure = 2800
        
        status = "OK"
        if current_pressure == self.pressure_thresholds["critical"]:
            status = "CRITICAL"
            self.activate_backup()
        elif current_pressure == self.pressure_thresholds["warning"]:
            status = "WARNING"
            
        logger.info(f"Hydraulic pressure: {current_pressure} psi, Status: {status}")
        
    def activate_backup(self):
        logger.info("Activating backup hydraulic system")
        self.active_system = self.backup_system
        
    def run(self):
        while True:
            self.monitor_pressure()
            
if __name__ == "__main__":
    controller = HydraulicSystemController() 
    controller.run()