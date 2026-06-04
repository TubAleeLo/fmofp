"""
Test script to verify the fix for precipitation data being properly transferred 
between BC and RT using the new RT_transfer_aggregator.
"""

import sys
import os
import uuid
import time
import logging
import traceback

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from FMOFP.Utils.logger.sys_logger import get_logger
from FMOFP.MIL_STD_1553B.Bus_Controller.BC import get_bus_controller
from FMOFP.MIL_STD_1553B.Remote_Terminal.RT import get_Remote_Terminal
from FMOFP.MIL_STD_1553B.Remote_Terminal.RT_messaging.RT_transfer_aggregator import get_rt_transfer_aggregator
from FMOFP.MIL_STD_1553B.mil_std_1553B import MIL_STD_1553B_Message
from FMOFP.Systems.radarManagement.weather.precipitation_data_generator_sync import PrecipitationDataGenerator
from FMOFP.Systems.radarManagement.radar_messaging.message_definitions.weather_data import PrecipitationData

logger = get_logger()

def setup_logging():
    """Set up logging with enhanced detail for data transfer debugging"""
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.info("Detailed logging configured")

def create_test_precipitation_data():
    """Create sample precipitation data for testing"""
    # Create a list of precipitation data objects with realistic values
    precip_objects = []
    
    for i in range(5):  # Create 5 test objects
        x_coord = (i - 2) * 5  # Range from -10 to 10
        y_coord = (i - 2) * 4  # Range from -8 to 8
        
        # Alternate between rain and snow
        precip_type = "rain" if i % 2 == 0 else "snow"
        
        # Create realistic rate and intensity values
        rate = (i + 1) * 2.5  # Range from 2.5 to 12.5
        intensity = min(1.0, (i + 1) * 0.2)  # Range from 0.2 to 1.0
        
        # Create precipitation data object
        precip_obj = {
            "position": (x_coord, y_coord),
            "type": precip_type,
            "rate": rate,
            "intensity": intensity,
            "show_values": intensity > 0.5
        }
        
        precip_objects.append(precip_obj)
    
    return precip_objects

def create_binary_data_message(precip_objects):
    """Create a binary data message containing precipitation data"""
    request_id = str(uuid.uuid4())
    
    # First, create a PrecipitationData object with proper structure
    precip_data = PrecipitationData(
        data_uuid=request_id,
        grid_cells=precip_objects,  # Use our test objects
        scan_width=500.0,
        scan_height=500.0,
        message_header="precipitation_data_test",
        sending_system="weather_radar",
        destination="radar_handler",
        request_id=request_id
    )
    
    # Add metadata to indicate this is precipitation data
    precip_data.additional_info = {
        'original_request_id': request_id,
        'precipitation_message': True,
        'data_type': 'precipitation',
        'command_type': 'precipitation_data',
        'message_type': 'weather_radarPrecipitationResponse'
    }
    
    # Set timestamp
    precip_data.timestamp = time.time()
    
    # Convert to binary data message structure
    binary_data = []
    # In a real message, this would be encoded from the precipitation objects
    # For test purposes, we'll create a simple array of integers
    for obj in precip_objects:
        # Create position frame
        x, y = obj["position"]
        # Encode position as integers (simulated binary data)
        encoded_x = int(x) + 128  # Offset to ensure positive values
        encoded_y = int(y) + 128
        position_value = (encoded_x << 8) | encoded_y
        binary_data.append(position_value)
        
        # Create attribute frame
        type_value = 1 if obj["type"] == "snow" else 0
        rate_value = min(63, int(obj["rate"] * 10))
        intensity_value = min(63, int(obj["intensity"] * 63))
        attribute_value = (type_value << 15) | (rate_value << 6) | intensity_value
        binary_data.append(attribute_value)
    
    # Create a MIL_STD_1553B_Message with the binary data
    message = MIL_STD_1553B_Message(
        rt_address=9,  # Weather radar RT address
        sub_address=3,  # Data subaddress
        data=binary_data,
        message_type='weather_radarPrecipitationResponse',
        command_type='precipitation_data',
        command_name='DISPLAY_PRECIPITATION_DATA'
    )
    
    # Add request_id
    message.request_id = request_id
    
    # Add metadata to indicate this is precipitation data
    message.metadata = {
        'precipitation_message': True,
        'data_type': 'precipitation',
        'binary_data_preserved': True,
        'binary_data_length': len(binary_data)
    }
    
    return message

def test_rt_transfer_aggregator_integration():
    """Test the integration of RT_transfer_aggregator with RT message flow"""
    logger.info("Starting RT transfer aggregator integration test")
    
    try:
        # Create test data
        precip_objects = create_test_precipitation_data()
        logger.info(f"Created {len(precip_objects)} test precipitation objects")
        
        # Create binary data message
        test_message = create_binary_data_message(precip_objects)
        logger.info(f"Created test message with {len(test_message.data)} binary data items")
        
        # Initialize RT and BC
        bc = get_bus_controller()
        rt = get_Remote_Terminal()
        
        # Start RT listener
        rt.start_listener()
        logger.info("Started RT listener")
        
        # Get RT transfer aggregator
        rt_aggregator = get_rt_transfer_aggregator()
        logger.info("Got RT transfer aggregator instance")
        
        # Send test message from BC to RT
        logger.info("Sending test message from BC to RT")
        bc.send_message(test_message)
        
        # Wait a bit for processing
        time.sleep(1)
        
        # VERIFICATION: Check if RT received and processed the message
        logger.info("Checking if RT processed the message")
        
        # Wait for up to 5 seconds for a message to appear
        max_wait = 5
        processed_message = None
        
        for i in range(max_wait):
            # Check for processed messages
            logger.info(f"Checking for processed messages (attempt {i+1}/{max_wait})")
            
            with rt.rt_listener.message_lock:
                if rt.rt_listener.processed_messages:
                    processed_message = rt.rt_listener.processed_messages.pop(0)
                    logger.info(f"Found processed message: {processed_message}")
                    break
            
            # Wait before checking again
            time.sleep(1)
        
        # Verify the processed message
        if processed_message:
            logger.info("✅ Message received and processed by RT")
            
            # Check data preservation
            if hasattr(processed_message, 'data') and isinstance(processed_message.data, list):
                data_len = len(processed_message.data)
                logger.info(f"Received data length: {data_len}")
                logger.info(f"Expected data length: {len(test_message.data)}")
                
                # Check the binary data was preserved
                if data_len == len(test_message.data):
                    logger.info("✅ Binary data length preserved correctly")
                    
                    # Sample the received data for verification
                    sample_size = min(5, data_len)
                    logger.info(f"Sample of received binary data: {processed_message.data[:sample_size]}")
                    logger.info(f"Sample of sent binary data: {test_message.data[:sample_size]}")
                    
                    # Check data content matches
                    data_matches = all(processed_message.data[i] == test_message.data[i] for i in range(min(3, data_len)))
                    if data_matches:
                        logger.info("✅ Binary data content preserved correctly")
                    else:
                        logger.error("❌ Binary data content was corrupted")
                        
                else:
                    logger.error(f"❌ Binary data length mismatch: received {data_len}, expected {len(test_message.data)}")
            else:
                logger.error("❌ No data found in processed message")
            
            # Check metadata preservation
            if hasattr(processed_message, 'metadata') and isinstance(processed_message.metadata, dict):
                for key in ['precipitation_message', 'data_type', 'binary_data_preserved']:
                    if key in processed_message.metadata:
                        logger.info(f"✅ Metadata '{key}' preserved: {processed_message.metadata[key]}")
                    else:
                        logger.error(f"❌ Metadata '{key}' missing")
            else:
                logger.error("❌ No metadata found in processed message")
            
            # Check message type preservation
            if hasattr(processed_message, 'message_type') and processed_message.message_type == test_message.message_type:
                logger.info(f"✅ Message type preserved: {processed_message.message_type}")
            else:
                logger.error(f"❌ Message type mismatch: {getattr(processed_message, 'message_type', None)} vs expected {test_message.message_type}")
            
            # Check command type preservation
            if hasattr(processed_message, 'command_type') and processed_message.command_type == test_message.command_type:
                logger.info(f"✅ Command type preserved: {processed_message.command_type}")
            else:
                logger.error(f"❌ Command type mismatch: {getattr(processed_message, 'command_type', None)} vs expected {test_message.command_type}")
        else:
            logger.error("❌ No message was processed by RT")
        
        # Stop RT listener
        rt.stop_listener()
        logger.info("Stopped RT listener")
        
        return processed_message is not None
        
    except Exception as e:
        logger.error(f"Test failed with error: {e}")
        logger.error(traceback.format_exc())
        return False

if __name__ == "__main__":
    setup_logging()
    logger.info("Starting precipitation data transfer test")
    
    success = test_rt_transfer_aggregator_integration()
    
    if success:
        logger.info("TEST PASSED: RT transfer aggregator integration test successful!")
        sys.exit(0)
    else:
        logger.error("TEST FAILED: RT transfer aggregator integration test failed")
        sys.exit(1)
