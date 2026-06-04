import sys
import FMOFP.Utils.common.fetching as fetching
import math
import xml.etree.ElementTree as ET
from FMOFP.Utils.logger.sys_logger import get_logger

logger = get_logger()

class Unit:
    def __init__(self, id, type, affiliation, position, capabilities):
        self.id = id
        self.type = type
        self.affiliation = affiliation
        self.position = position
        self.capabilities = capabilities
        self.status = "Operational"

class OrderOfBattle:
    def __init__(self):
        self.logger = logger("OrderOfBattle")
        self.friendly_forces = {}
        self.enemy_forces = {}
        self.neutral_forces = {}

    def add_unit(self, unit):
        if unit.affiliation == "Friendly":
            self.friendly_forces[unit.id] = unit
        elif unit.affiliation == "Enemy":
            self.enemy_forces[unit.id] = unit
        elif unit.affiliation == "Neutral":
            self.neutral_forces[unit.id] = unit
        else:
            self.logger.warning(f"Unknown affiliation for unit {unit.id}")
        self.logger.info(f"Added {unit.affiliation} unit {unit.id} of type {unit.type}")

    def remove_unit(self, unit_id):
        for force in [self.friendly_forces, self.enemy_forces, self.neutral_forces]:
            if unit_id in force:
                del force[unit_id]
                self.logger.info(f"Removed unit {unit_id}")
                return
        self.logger.warning(f"Unit {unit_id} not found")

    def update_unit_position(self, unit_id, new_position):
        for force in [self.friendly_forces, self.enemy_forces, self.neutral_forces]:
            if unit_id in force:
                force[unit_id].position = new_position
                self.logger.info(f"Updated position of unit {unit_id} to {new_position}")
                return
        self.logger.warning(f"Unit {unit_id} not found")

    def update_unit_status(self, unit_id, new_status):
        for force in [self.friendly_forces, self.enemy_forces, self.neutral_forces]:
            if unit_id in force:
                force[unit_id].status = new_status
                self.logger.info(f"Updated status of unit {unit_id} to {new_status}")
                return
        self.logger.warning(f"Unit {unit_id} not found")

    def get_unit_info(self, unit_id):
        for force in [self.friendly_forces, self.enemy_forces, self.neutral_forces]:
            if unit_id in force:
                unit = force[unit_id]
                return {
                    "id": unit.id,
                    "type": unit.type,
                    "affiliation": unit.affiliation,
                    "position": unit.position,
                    "capabilities": unit.capabilities,
                    "status": unit.status
                }
        self.logger.warning(f"Unit {unit_id} not found")
        return None

    def get_forces_in_area(self, center, radius):
        forces = []
        for force in [self.friendly_forces, self.enemy_forces, self.neutral_forces]:
            for unit in force.values():
                distance = math.sqrt(
                    (unit.position[0] - center[0])**2 +
                    (unit.position[1] - center[1])**2 +
                    (unit.position[2] - center[2])**2
                )
                if distance <= radius:
                    forces.append(unit)
        return forces

    def handle_message(self, message):
        if message.get("type") == "add_unit":
            unit = Unit(**message.get("unit_data"))
            self.add_unit(unit)
        elif message.get("type") == "remove_unit":
            self.remove_unit(message.get("unit_id"))
        elif message.get("type") == "update_unit_position":
            self.update_unit_position(message.get("unit_id"), message.get("new_position"))
        elif message.get("type") == "update_unit_status":
            self.update_unit_status(message.get("unit_id"), message.get("new_status"))
        elif message.get("type") == "get_unit_info":
            return self.get_unit_info(message.get("unit_id"))
        elif message.get("type") == "get_forces_in_area":
            return self.get_forces_in_area(message.get("center"), message.get("radius"))

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
    oob = OrderOfBattle()
    friendly_unit = Unit("F001", "Fighter", "Friendly", (34.0522, -118.2437, 10000), ["Air-to-Air", "Air-to-Ground"])
    enemy_unit = Unit("E001", "SAM Site", "Enemy", (34.0522, -118.2437, 0), ["Surface-to-Air"])
    oob.add_unit(friendly_unit)
    oob.add_unit(enemy_unit)
    logger.info(oob.get_unit_info("F001"))
    logger.info(oob.get_forces_in_area((34.0522, -118.2437, 5000), 10000))
    oob.update_unit_position("F001", (34.0523, -118.2438, 11000))
    oob.update_unit_status("E001", "Destroyed")
    logger.info(oob.get_unit_info("E001"))