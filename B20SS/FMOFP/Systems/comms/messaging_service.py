# messaging_service.py
# This is a remote messaging service.  NEEDS to be refactored to be specific this this system.  Each system should have its own local version of this service.
#       TODO: update with message types and topics specific to the system
#
# This is a messaging service that uses asyncio and XML-based messages to publish and subscribe to messages.
# MessageBroker manages message topics and subscribers
# MessagingService provides methods for publishing and subscribing to messages
# SensorDataMessage represents a sensor data message and provides methods for converting the message to and from XML.
# 


import asyncio
import xml.etree.ElementTree as ET
from typing import Any, Callable, Dict
from FMOFP.Utils.logger.sys_logger import get_logger

logger = get_logger()

class Message:
    def __init__(self, sender, receiver, content):
        self.sender = sender
        self.receiver = receiver
        self.content = content

    def __repr__(self):
        return f"Message(sender={self.sender}, receiver={self.receiver}, content={self.content})"

class MessageBroker:
    def __init__(self):
        self.topics = {}
        self.subscribers = {}

    def subscribe(self, topic, callback):
        if topic not in self.subscribers:
            self.subscribers[topic] = []
        self.subscribers[topic].append(callback)

    def unsubscribe(self, topic, callback):
        if topic in self.subscribers:
            self.subscribers[topic].remove(callback)

    async def publish(self, topic, message):
        if topic in self.subscribers:
            await asyncio.gather(*[callback(message) for callback in self.subscribers[topic]])

class MessagingService:
    def __init__(self):
        self.broker = MessageBroker()

    def subscribe(self, topic, callback):
        self.broker.subscribe(topic, callback)

    def unsubscribe(self, topic, callback):
        self.broker.unsubscribe(topic, callback)

    async def publish(self, topic, message):
        if hasattr(message, 'to_xml'):
            # Handle XML messages
            await self.broker.publish(topic, ET.tostring(message.to_xml()))
        else:
            # Handle dictionary messages directly
            await self.broker.publish(topic, message)

    async def run(self):
        """Run the messaging service."""
        try:
            while True:
                await asyncio.sleep(0.1)  # More responsive sleep
        except Exception as e:
            logger.error(f"Error in messaging service: {e}")
            raise

async def sample_publisher(service):
    topic = "sensor_data"
    message = SensorDataMessage(temperature=25.5, pressure=1010.2)
    await service.publish(topic, message)
    logger.info(f"Published to {topic}: {message.to_xml()}")

async def sample_subscriber(service):
    topic = "sensor_data"
    service.subscribe(topic, lambda xml_str: logger.info(f"Received from {topic}: {SensorDataMessage.from_xml(ET.fromstring(xml_str))}"))

class SensorDataMessage:
    def __init__(self, temperature: float, pressure: float):
        self.temperature = temperature
        self.pressure = pressure

    def to_xml(self):
        root = ET.Element("sensor_data")
        temp = ET.SubElement(root, "temperature")
        temp.text = str(self.temperature)
        pressure = ET.SubElement(root, "pressure")
        pressure.text = str(self.pressure)
        return root

    @classmethod
    def from_xml(cls, xml_root):
        temperature = float(xml_root.find("temperature").text)
        pressure = float(xml_root.find("pressure").text)
        return cls(temperature, pressure)

    def __str__(self):
        return f"SensorDataMessage(temperature={self.temperature}, pressure={self.pressure})"

async def main():
    service = MessagingService()

    publisher_task = asyncio.create_task(sample_publisher(service))
    subscriber_task = asyncio.create_task(sample_subscriber(service))

    await service.run()

if __name__ == "__main__":
    asyncio.run(main())
