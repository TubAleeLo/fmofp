import Utils.common.fetching as fetching
import xml.etree.ElementTree as ET
from FMOFP.Utils.logger.sys_logger import get_logger

logger = get_logger()


class FlightManagementFitness:
    def __init__(self):
        pass
        
        tree = ET.parse("Systems/fmFitness/fmfConfig.xml")
        config = tree.getroot()
        
        self.components = []
        for comp in config.find("components"):
            name = comp.find("name").text
            desc = comp.find("description").text
            self.components.append({"name": name, "description": desc})
            
        self.thresholds = {
            "warning": {
                "cpu": int(config.find("thresholds/warning/cpu").text),
                "memory": int(config.find("thresholds/warning/memory").text)
            },
            "critical": {
                "cpu": int(config.find("thresholds/critical/cpu").text),
                "memory": int(config.find("thresholds/critical/memory").text)
            }
        }
        
        self.redundancy = {
            "component": config.find("redundancy/component").text,
            "backup": config.find("redundancy/backup").text
        }
        
    def monitor_components(self):
        # Simulate monitoring components
        # Get actual component data from other systems
        logger.info("Monitoring flight management components")
        
    def check_thresholds(self, component, metrics):
        # Check CPU and memory usage against thresholds
        cpu_usage = metrics.get("cpu", 0)
        mem_usage = metrics.get("memory", 0)
        
        status = "OK"
        if cpu_usage == self.thresholds["critical"]["cpu"] or \
           mem_usage == self.thresholds["critical"]["memory"]:
            status = "CRITICAL"
        elif cpu_usage == self.thresholds["warning"]["cpu"] or \
             mem_usage == self.thresholds["warning"]["memory"]:
            status = "WARNING"
            
        logger.info(f"{component} status: {status}") 
        
        # Take appropriate actions based on status
        
    def handle_redundancy(self, component):
        if component == self.redundancy["component"]:
            logger.info(f"Activating backup {self.redundancy['backup']} for {component}")
            # Failover logic
            
    def run(self):
        while True:
            self.monitor_components()
            
            # Simulate getting metrics from components
            for component in self.components:
                metrics = {
                    "cpu": 75, # Replace with actual CPU usage
                    "memory": 80 # Replace with actual memory usage  
                }
                self.check_thresholds(component["name"], metrics)
                
            # Sleep for configured interval before checking again
                  
if __name__ == "__main__":
    fmf = FlightManagementFitness()
    fmf.run()