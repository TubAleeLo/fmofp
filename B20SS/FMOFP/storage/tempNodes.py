# tempNodes.py
#    THIS is to be renamed - flags.py
#    class rename -    class flags


import threading
from xml.etree import ElementTree as ET
from Systems.comms.messaging_service import MessagingService, Message

from FMOFP.Utils.logger.sys_logger import get_logger

logger = get_logger()

class BaseNode:
    def __init__(self, name, value):
        self.name = name
        self.value = value
        self.children = {}
        self.lock = threading.Lock()
        self.messaging_service = MessagingService()

    def add_child(self, child_node):
        with self.lock:
            self.children[child_node.name] = child_node
            logger.info(f"Added child {child_node.name} to {self.name}")

    def get_child(self, name):
        with self.lock:
            return self.children.get(name)

    def remove_child(self, name):
        with self.lock:
            if name in self.children:
                del self.children[name]
                logger.info(f"Removed child {name} from {self.name}")

    async def save_to_db(self):
        with self.lock:
            message = Message(
                sender=self.name,
                receiver="DatabaseManager",
                content={"action": "save_node", "node": self.__dict__}
            )
            await self.messaging_service.publish("database_topic", message)
            logger.info(f"Sent save message for node {self.name} to database")

    async def load_from_db(self, name):
        with self.lock:
            message = Message(
                sender=self.name,
                receiver="DatabaseManager",
                content={"action": "load_node", "name": name}
            )
            self.messaging_service.subscribe("database_topic_response", self._handle_load_response)
            await self.messaging_service.publish("database_topic", message)

    def _handle_load_response(self, xml_str):
        response = Message.from_xml(ET.fromstring(xml_str))
        if response.content.get("status") == "success":
            node_data = response.content.get("node")
            self.name = node_data['name']
            self.value = node_data['value']
            self.children = node_data['children']
            logger.info(f"Loaded node {self.name} from database")

    def __repr__(self):
        return f"BaseNode(name={self.name}, value={self.value})"


class LinkedListNode:
    def __init__(self, data):
        self.data = data
        self.next = None

    def __repr__(self):
        return f"LinkedListNode(data={self.data})"


class LinkedList:
    def __init__(self):
        self.head = None
        self.lock = threading.Lock()
        self.messaging_service = MessagingService()

    def append(self, data):
        new_node = LinkedListNode(data)
        with self.lock:
            if not self.head:
                self.head = new_node
                return
            last_node = self.head
            while last_node.next:
                last_node = last_node.next
            last_node.next = new_node

    def prepend(self, data):
        new_node = LinkedListNode(data)
        with self.lock:
            new_node.next = self.head
            self.head = new_node

    def delete_with_value(self, data):
        with self.lock:
            if not self.head:
                return
            if self.head.data == data:
                self.head = self.head.next
                return
            current_node = self.head
            while current_node.next:
                if current_node.next.data == data:
                    current_node.next = current_node.next.next
                    return
                current_node = current_node.next

    def find(self, data):
        with self.lock:
            current_node = self.head
            while current_node:
                if current_node.data == data:
                    return current_node
                current_node = current_node.next
            return None

    def reverse(self):
        with self.lock:
            prev = None
            current = self.head
            while current:
                next_node = current.next
                current.next = prev
                prev = current
                current = next_node
            self.head = prev

    def __repr__(self):
        nodes = []
        current_node = self.head
        while current_node:
            nodes.append(repr(current_node))
            current_node = current_node.next
        return " -> ".join(nodes)


class StateNode(BaseNode):
    def __init__(self, name, value):
        super().__init__(name, value)

    def set_state(self, state):
        with self.lock:
            self.value = state
            logger.info(f"Set state of {self.name} to {state}")

    def get_state(self):
        with self.lock:
            if self.name == None:
                logger.warning(f"State of {self.value} is None")
                return self.value
            return self.value
