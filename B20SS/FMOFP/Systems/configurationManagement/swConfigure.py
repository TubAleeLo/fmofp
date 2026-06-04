import sys
import Utils.common.fetching as fetching
import xml.etree.ElementTree as ET
from FMOFP.Utils.logger.sys_logger import get_logger

logger = get_logger()

class SoftwareConfigManager:
    def __init__(self):
        pass
        
        tree = ET.parse("Systems/configurationManagement/swcmConfig.xml")
        config = tree.getroot()
        
        self.components = []
        for comp in config.findall("components/component"):
            name = comp.find("name").text
            desc = comp.find("description").text
            version = comp.find("currentVersion").text
            self.components.append({"name": name, "description": desc, "version": version})
            
        self.data_loads = []
        for load in config.findall("dataLoads/load"):
            load_id = load.find("id").text
            desc = load.find("description").text
            date = load.find("date").text
            status = load.find("status").text
            load_specs = []
            for spec in load.findall("loadSpecs"):
                comp_name = spec.find("component").text
                comp_ver = spec.find("version").text
                load_specs.append({"component": comp_name, "version": comp_ver})
            self.data_loads.append({"id": load_id, "description": desc, "date": date, "status": status, "specs": load_specs})
            
        self.update_sequence = [step.text for step in config.findall("updateSequence/step")]
        
    def display_component_status(self):
        logger.info("Current Software Versions:")
        for comp in self.components:
            logger.info(f"  {comp['description']}: {comp['version']}")
            
    def display_data_loads(self):
        logger.info("\nApproved Data Loads:")
        for load in self.data_loads:
            logger.info(f"  Load {load['id']} - {load['description']} ({load['date']})")
            logger.info(f"    Status: {load['status']}")
            logger.info("    Components:")
            for spec in load["specs"]:
                logger.info(f"      {spec['component']} - {spec['version']}")
                
    def perform_update(self, load_id):
        load = next((l for l in self.data_loads if l["id"] == str(load_id)), None)
        if load:
            logger.info(f"\nApplying data load {load['id']}")
            for step in self.update_sequence:
                logger.info(f"  {step}...")
                # Simulate update sequence
                
            logger.info("Software update completed successfully!")
            
            # Update current versions based on load specs 
            for comp in self.components:
                new_ver = next((s["version"] for s in load["specs"] if s["component"] == comp["name"]), None)
                if new_ver:
                    logger.info(f"  {comp['description']} updated to version {new_ver}")
                    comp["version"] = new_ver
                    
        else:
            logger.warning(f"Invalid data load ID: {load_id}")
        
    def run(self):
        self.display_component_status()
        self.display_data_loads()
        
        self.perform_update("20191015")
        
        self.display_component_status()
        
if __name__ == "__main__":
    manager = SoftwareConfigManager()
    manager.run()