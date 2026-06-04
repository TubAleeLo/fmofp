import Utils.common.fetching as fetching
import xml.etree.ElementTree as ET
from FMOFP.Utils.logger.sys_logger import get_logger

logger = get_logger()

class BuiltInTestController:
    def __init__(self):


        
        tree = ET.parse("Systems/builtInTestSystems/bitsConfig.xml")
        config = tree.getroot()
        
        self.self_tests = []
        for test in config.findall("selfTests/test"):
            test_id = test.find("id").text
            desc = test.find("description").text
            system = test.find("system").text
            components = [c.text for c in test.findall("components/component")]
            self.self_tests.append({"id": test_id, "description": desc, "system": system, "components": components})
            
        self.periodic_tests = []
        for test in config.findall("periodicTests/test"):
            test_id = test.find("id").text 
            desc = test.find("description").text
            systems = [s.text for s in test.findall("systems/system")]  
            interval = int(test.find("interval").text)
            self.periodic_tests.append({"id": test_id, "description": desc, "systems": systems, "interval": interval})
            
        self.interface_tests = []
        for test in config.findall("interfaceTests/test"):
            test_id = test.find("id").text
            desc = test.find("description").text
            system1 = test.find("system1").text
            system2 = test.find("system2").text
            components = [c.text for c in test.findall("components/component")]
            self.interface_tests.append({"id": test_id, "description": desc, "system1": system1, "system2": system2, "components": components})
            
    def run_self_tests(self):
        for test in self.self_tests:
            logger.info(f"Running {test['description']}:")
            for comp in test["components"]:
                status = "OK" # Simulate component test status
                logger.info(f"  {comp.capitalize()}: {status}")
                
    def run_periodic_tests(self):
        for test in self.periodic_tests:
            logger.info(f"Running {test['description']}:")
            for system in test["systems"]:
                status = "OK" # Simulate system test status
                logger.info(f"  {system.capitalize()}: {status}")
                
    def run_interface_tests(self):
        for test in self.interface_tests:
            logger.info(f"Running {test['description']}:")
            for comp in test["components"]:
                status = "OK" # Simulate interface test status
                logger.info(f"  {comp.capitalize()}: {status}")
                
    def run(self):
        logger.info("Initiating Built-In Tests")
        self.run_self_tests()
        logger.info("Power-On Self Tests complete")
        
        self.run_periodic_tests() 
        self.run_interface_tests()
        
        logger.info("All tests passed!")
        
if __name__ == "__main__":
    controller = BuiltInTestController()
    controller.run()