"""
Persistent Operation Tracking Utility

Provides a mechanism to track operations that should only happen once,
even across application restarts and module reloads.
"""

import os
import threading
from datetime import datetime
from typing import Callable, Optional, Any, Dict

from FMOFP.Utils.logger.sys_logger import get_logger

logger = get_logger()

# Create tracking directory if it doesn't exist
TRACKING_DIR = os.path.join('FMOFP', 'tracking')
os.makedirs(TRACKING_DIR, exist_ok=True)

# Thread safety for file operations
_file_lock = threading.Lock()

def track_operation(operation_name: str, identifier: str, perform_operation_fn: Callable) -> Any:
    """Track and execute operations that should only happen once.

    Args:
        operation_name: Type of operation (e.g., 'init', 'config', 'setup')
        identifier: Unique identifier for this specific operation
        perform_operation_fn: Function to call if operation hasn't been done
        
    Returns:
        Result from perform_operation_fn or None if already performed
    """
    # Create a safe filename from the operation details
    safe_id = identifier.replace('.', '_').replace('/', '_').replace('\\', '_')
    track_file = os.path.join(TRACKING_DIR, f"{operation_name}_{safe_id}.lock")
    
    # Thread-safe check if this operation has already been performed
    with _file_lock:
        if os.path.exists(track_file):
            logger.debug(f"Operation {operation_name} for {identifier} already performed - skipping")
            return None
        
        # Perform the operation
        logger.info(f"Performing {operation_name} for {identifier}")
        result = perform_operation_fn()
        
        # Mark operation as completed
        try:
            # Create a temporary file and then rename it to ensure atomic operation
            temp_file = track_file + '.tmp'
            with open(temp_file, 'w') as f:
                f.write(str(datetime.now()))
            os.replace(temp_file, track_file)
        except Exception as e:
            logger.error(f"Error creating tracking file {track_file}: {e}")
        
        return result

def is_operation_completed(operation_name: str, identifier: str) -> bool:
    """Check if an operation has already been completed.

    Args:
        operation_name: Type of operation (e.g., 'init', 'config', 'setup')
        identifier: Unique identifier for this specific operation
        
    Returns:
        bool: True if the operation has been completed, False otherwise
    """
    # Create a safe filename from the operation details
    safe_id = identifier.replace('.', '_').replace('/', '_').replace('\\', '_')
    track_file = os.path.join(TRACKING_DIR, f"{operation_name}_{safe_id}.lock")
    
    # Thread-safe check if this operation has already been performed
    with _file_lock:
        return os.path.exists(track_file)

def mark_operation_completed(operation_name: str, identifier: str) -> bool:
    """Mark an operation as completed without executing a function.

    Args:
        operation_name: Type of operation (e.g., 'init', 'config', 'setup')
        identifier: Unique identifier for this specific operation
        
    Returns:
        bool: True if the operation was marked as completed, False if it was already completed
    """
    # Create a safe filename from the operation details
    safe_id = identifier.replace('.', '_').replace('/', '_').replace('\\', '_')
    track_file = os.path.join(TRACKING_DIR, f"{operation_name}_{safe_id}.lock")
    
    # Thread-safe check if this operation has already been performed
    with _file_lock:
        if os.path.exists(track_file):
            logger.debug(f"Operation {operation_name} for {identifier} already marked as completed")
            return False
        
        # Mark operation as completed
        try:
            # Create a temporary file and then rename it to ensure atomic operation
            temp_file = track_file + '.tmp'
            with open(temp_file, 'w') as f:
                f.write(str(datetime.now()))
            os.replace(temp_file, track_file)
            logger.info(f"Marked operation {operation_name} for {identifier} as completed")
            return True
        except Exception as e:
            logger.error(f"Error creating tracking file {track_file}: {e}")
            return False

def clear_operation_tracking(operation_name: Optional[str] = None, identifier: Optional[str] = None) -> None:
    """Clear operation tracking files.
    
    Args:
        operation_name: Optional specific operation to clear
        identifier: Optional specific identifier to clear
    """
    with _file_lock:
        if operation_name and identifier:
            # Clear specific operation
            safe_id = identifier.replace('.', '_').replace('/', '_').replace('\\', '_')
            track_file = os.path.join(TRACKING_DIR, f"{operation_name}_{safe_id}.lock")
            if os.path.exists(track_file):
                os.remove(track_file)
                logger.info(f"Cleared tracking for operation {operation_name} with identifier {identifier}")
        elif operation_name:
            # Clear all operations of a specific type
            count = 0
            for filename in os.listdir(TRACKING_DIR):
                if filename.startswith(f"{operation_name}_") and filename.endswith(".lock"):
                    os.remove(os.path.join(TRACKING_DIR, filename))
                    count += 1
            logger.info(f"Cleared tracking for {count} operations of type {operation_name}")
        else:
            # Clear all operations
            count = 0
            for filename in os.listdir(TRACKING_DIR):
                if filename.endswith(".lock"):
                    os.remove(os.path.join(TRACKING_DIR, filename))
                    count += 1
            logger.info(f"Cleared tracking for all {count} operations")





# What will happen if the program is stopped like in debugging, will the tracking file be deleted?
# Will the files be maintain until the program is stopped?  Will it clear them out on startup?
# This should be callable to check if the operation has been completed or not.  If it has been completed, then it should not be called again.
