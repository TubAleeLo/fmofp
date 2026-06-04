import Utils.common.fetching as fetching
import xml.etree.ElementTree as ET
from FMOFP.Utils.logger.sys_logger import get_logger

logger = get_logger()

class ElectricalPowerController:
    def __init__(self):
        tree = ET.parse("Systems/electricalPower/epConfig.xml")
        config = tree.getroot()
        
        self.generators = []
        for gen in config.findall("generators/generator"):
            gen_id = int(gen.find("id").text)
            desc = gen.find("description").text
            capacity = int(gen.find("capacity").text)
            self.generators.append({"id": gen_id, "description": desc, "capacity": capacity})
            
        self.distribution = {}
        for bus in config.findall("distribution/bus"):
            bus_id = int(bus.find("id").text)
            desc = bus.find("description").text
            supply_order = [int(gen.text) for gen in bus.find("supplyOrder")]
            battery = bus.find("supplyOrder/battery").text
            self.distribution[bus_id] = {"description": desc, "supply_order": supply_order, "battery": battery}
            
        self.batteries = {}
        for batt in config.findall("batteries/battery"):
            batt_id = batt.find("id").text
            desc = batt.find("description").text
            capacity = int(batt.find("capacity").text)
            self.batteries[batt_id] = {"description": desc, "capacity": capacity}
            
    def monitor_generators(self):
        # Simulate monitoring generator status
        for gen in self.generators:
            status = "OK" # In real system, get actual generator status
            logger.info(f"Generator {gen['id']}: {status}")
            
    def manage_distribution(self):
        for bus_id, bus in self.distribution.items():
            supplying_generator = None
            for gen_id in bus["supply_order"]:
                gen = next((g for g in self.generators if g["id"] == gen_id), None)
                if gen:
                    supplying_generator = gen
                    break
                    
            if supplying_generator:
                logger.info(f"Bus {bus_id} supplied by generator {supplying_generator['id']}")
            else:
                batt = self.batteries.get(bus["battery"], None)
                if batt:
                    logger.info(f"Bus {bus_id} supplied by {batt['description']}")
                else:
                    logger.warning(f"No power source for bus {bus_id}!")
                    
    def run(self):
        while True:
            self.monitor_generators()
            self.manage_distribution()
            
if __name__ == "__main__":
    controller = ElectricalPowerController()
    controller.run()