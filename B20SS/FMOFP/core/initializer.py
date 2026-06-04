"""
Initializer singleton for managing shared system resources
"""
import os
import sys
import threading
import traceback
import asyncio
from PyQt6.QtWidgets import QApplication
from Utils.logger.sys_logger import get_logger
from Utils.common.system_state_manager import SystemStateManager
from Utils.common.system_states import SystemState
from qasync import QEventLoop

logger = get_logger()

class SingletonMeta(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
        return cls._instances[cls]

class Initializer(metaclass=SingletonMeta):
    def __init__(self):
        self.initialized = False
        self._app = None
        self._loop = None
        self._state_manager = None
        self._shutdown_started = False

    def initialize(self):
        if not self.initialized:
            try:
                # Log system information
                logger.info(f"Current working directory: {os.getcwd()}")
                logger.info(f"Main thread ID: {threading.get_ident()}")
                
                # Initialize Qt application (singleton)
                if not QApplication.instance():
                    self._app = QApplication(sys.argv)
                else:
                    self._app = QApplication.instance()
                
                # Create event loop that works with Qt (singleton)
                if not self._loop:
                    self._loop = QEventLoop(self._app)
                    asyncio.set_event_loop(self._loop)
                
                # Initialize SystemStateManager
                self._state_manager = SystemStateManager()
                self._state_manager.initialize()
                
                # Set up state transition handler
                self._state_manager.add_state_change_handler(self._handle_state_change)
                
                self.initialized = True
                logger.info("System initialization completed successfully.")
            except Exception as e:
                logger.error(f"Error during system initialization: {str(e)}")
                raise

    def _handle_state_change(self, old_state, new_state):
        """Handle system state transitions"""
        logger.info(f"System state transition: {old_state} -> {new_state}")
        
        if new_state == SystemState.SHUTDOWN:
            self._initiate_shutdown()
        elif new_state == SystemState.ERROR:
            self._handle_error_state()

    def _initiate_shutdown(self):
        """Initiate graceful shutdown sequence"""
        if self._shutdown_started:
            return
            
        self._shutdown_started = True
        logger.info("Initiating graceful shutdown sequence")
        
        try:
            # Stop the event loop if it's running
            if self._loop and self._loop.is_running():
                self._loop.call_soon_threadsafe(self._loop.stop)
                
            # Clean up resources
            self.cleanup()
        except Exception as e:
            logger.error(f"Error during shutdown: {str(e)}")

    def _handle_error_state(self):
        """Handle transition to error state"""
        logger.error("System entered ERROR state")
        self._initiate_shutdown()

    def get_app(self):
        return self._app

    def get_loop(self):
        return self._loop

    def get_state_manager(self):
        return self._state_manager

    def cleanup(self):
        """Clean up resources"""
        if not self._shutdown_started:
            self._shutdown_started = True
            
        try:
            logger.info("Starting cleanup sequence")
            
            # Stop the event loop
            if self._loop and self._loop.is_running():
                self._loop.stop()
                
            # Close the event loop
            if self._loop and not self._loop.is_closed():
                # Run any pending callbacks
                pending = asyncio.all_tasks(self._loop)
                if pending:
                    logger.info(f"Cleaning up {len(pending)} pending tasks")
                    self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                    
                self._loop.close()
                logger.info("Event loop closed")
                
            # Clean up Qt application
            if self._app:
                self._app.quit()
                logger.info("Qt application quit")
                
            logger.info("Cleanup completed successfully")
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")

# Singleton instance
_initializer = None

def get_initializer():
    global _initializer
    if _initializer is None:
        _initializer = Initializer()
    return _initializer
