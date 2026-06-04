import Utils.common.fetching as fetching
import xml.etree.ElementTree as ET
from FMOFP.Utils.logger.sys_logger import get_logger

logger = get_logger()

class FlightDataMonitoring:
    def __init__(self):

        
        tree = ET.parse("Systems/flightDataMonitoring/fdmsConfig.xml")
        config = tree.getroot()
        
        self.recorders = []
        for recorder in config.findall("recorders/recorder"):
            rec_id = int(recorder.find("id").text)
            desc = recorder.find("description").text
            rec_type = recorder.find("type").text
            parameters = [{"name": p.find("name").text, "units": p.find("units").text} for p in recorder.findall("parameters/parameter")]
            self.recorders.append({"id": rec_id, "description": desc, "type": rec_type, "parameters": parameters})
            
        self.storage = []
        for card in config.findall("storage/memoryCards/card"):
            slot = int(card.find("slot").text)
            desc = card.find("description").text
            capacity = int(card.find("capacity").text)
            contents = card.find("contents").text 
            self.storage.append({"slot": slot, "description": desc, "capacity": capacity, "contents": contents})
            
    def collect_data(self):
        for recorder in self.recorders:
            logger.info(f"Recording {recorder['description']} Data:")
            for param in recorder["parameters"]:
                value = 123 # Simulate parameter value
                logger.info(f"  {param['name']}: {value} {param['units']}")
                
    def eject_storage(self, slot):
        card = next((c for c in self.storage if c["slot"] == slot), None)
        if card:
            logger.info(f"Ejecting {card['description']}")
            # Simulate ejecting storage card
            logger.info(f"  Contents: {card['contents'].upper()} data")
            logger.info(f"  Capacity: {card['capacity']} GB") 
        else:
            logger.warning(f"No storage card in slot {slot}")
        
    def run(self):
        self.collect_data()
        
        self.eject_storage(1) 
        self.eject_storage(2)
        
if __name__ == "__main__":
    fdm = FlightDataMonitoring()
    fdm.run()