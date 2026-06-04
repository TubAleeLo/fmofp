import sys
import random
import math
import xml.etree.ElementTree as ET
from FMOFP.Utils.logger.sys_logger import get_logger

logger = get_logger()

class Target:
    def __init__(self, id, type, position, priority):
        self.id = id
        self.type = type
        self.position = position
        self.priority = priority
        self.status = "Unengaged"

class Targeting:
    def __init__(self):
        self.logger = logger("Targeting")
        self.targets = {}
        self.engaged_targets = {}

    def add_target(self, target):
        self.targets[target.id] = target
        self.logger.info(f"Added target {target.id} of type {target.type}")

    def remove_target(self, target_id):
        if target_id in self.targets:
            del self.targets[target_id]
            self.logger.info(f"Removed target {target_id}")
        else:
            self.logger.warning(f"Target {target_id} not found")

    def prioritize_targets(self):
        return sorted(self.targets.values(), key=lambda t: t.priority, reverse=True)

    def acquire_target(self, target_id):
        if target_id in self.targets:
            target = self.targets[target_id]
            target.status = "Acquired"
            self.logger.info(f"Acquired target {target_id}")
            return target
        else:
            self.logger.warning(f"Target {target_id} not found")
            return None

    def track_target(self, target_id):
        if target_id in self.targets:
            target = self.targets[target_id]
            # Simulate target movement
            target.position = (
                target.position[0] + random.uniform(-0.001, 0.001),
                target.position[1] + random.uniform(-0.001, 0.001),
                target.position[2] + random.uniform(-10, 10)
            )
            self.logger.info(f"Tracking target {target_id} at position {target.position}")
            return target.position
        else:
            self.logger.warning(f"Target {target_id} not found")
            return None

    def engage_target(self, target_id, weapon_system):
        if target_id in self.targets and target_id not in self.engaged_targets:
            target = self.targets[target_id]
            target.status = "Engaged"
            self.engaged_targets[target_id] = weapon_system
            self.logger.info(f"Engaged target {target_id} with {weapon_system}")
            return True
        else:
            self.logger.warning(f"Unable to engage target {target_id}")
            return False

    def disengage_target(self, target_id):
        if target_id in self.engaged_targets:
            target = self.targets[target_id]
            target.status = "Disengaged"
            del self.engaged_targets[target_id]
            self.logger.info(f"Disengaged from target {target_id}")
            return True
        else:
            self.logger.warning(f"Target {target_id} was not engaged")
            return False

    def get_target_status(self, target_id):
        if target_id in self.targets:
            target = self.targets[target_id]
            return {
                "id": target.id,
                "type": target.type,
                "position": target.position,
                "priority": target.priority,
                "status": target.status
            }
        else:
            self.logger.warning(f"Target {target_id} not found")
            return None

    def handle_message(self, message):
        if message.get("type") == "add_target":
            target = Target(**message.get("target_data"))
            self.add_target(target)
        elif message.get("type") == "remove_target":
            self.remove_target(message.get("target_id"))
        elif message.get("type") == "acquire_target":
            return self.acquire_target(message.get("target_id"))
        elif message.get("type") == "track_target":
            return self.track_target(message.get("target_id"))
        elif message.get("type") == "engage_target":
            return self.engage_target(message.get("target_id"), message.get("weapon_system"))
        elif message.get("type") == "disengage_target":
            return self.disengage_target(message.get("target_id"))
        elif message.get("type") == "get_target_status":
            return self.get_target_status(message.get("target_id"))

    def _dict_to_xml(self, tag, d):
        elem = ET.Element(tag)
        for key, val in d.items():
            child = ET.Element(key)
            child.text = str(val)
            elem.append(child)
        return ET.tostring(elem, encoding='unicode')

    def _xml_to_dict(self, xml_string):
        root = ET.fromstring(xml_string)
        return {child.tag: child.text for child in root}

# Example usage
if __name__ == "__main__":
    targeting = Targeting()
    target = Target("T001", "Ground", (34.0522, -118.2437, 0), 5)
    targeting.add_target(target)
    logger.info(targeting.acquire_target("T001"))
    logger.info(targeting.track_target("T001"))
    logger.info(targeting.engage_target("T001", "Air-to-Ground Missile"))
    logger.info(targeting.get_target_status("T001"))
    logger.info(targeting.disengage_target("T001"))
