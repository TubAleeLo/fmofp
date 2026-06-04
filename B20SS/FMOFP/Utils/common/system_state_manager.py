# system_state_manager.py
from Utils.common.system_states import SystemState, userCLIStates
import threading

from typing import Callable
from storage.tempNodes import StateNode
from Utils.common.system_states import SystemState

from FMOFP.Utils.logger.sys_logger import get_logger

logger = get_logger()

class SystemStateManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SystemStateManager, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        self._lock.acquire()
        try:
            self.system_state_node = None
            self.cli_state_node = None
            self._state_change_handlers = []
        finally:
            self._lock.release()

    def add_state_change_handler(self, handler: Callable[[SystemState, SystemState], None]):
        """Add a handler function that will be called when system state changes.
        
        Args:
            handler: Function that takes (old_state, new_state) as parameters
        """
        self._lock.acquire()
        try:
            self._state_change_handlers.append(handler)
            logger.debug(f"Added state change handler: {handler}")
        finally:
            self._lock.release()

    def set_state(self, state: SystemState):
        self._lock.acquire()
        try:
            old_state = None
            if self.system_state_node is None:
                self.system_state_node = StateNode("SystemState", state)
                logger.debug(f"Initialized system_state_node with state: {state}")
            else:
                old_state = self.system_state_node.get_state()
                self.system_state_node.set_state(state)
                logger.debug(f"Updated system_state_node to state: {state}")
            
            # Notify handlers of state change
            for handler in self._state_change_handlers:
                try:
                    handler(old_state, state)
                except Exception as e:
                    logger.error(f"Error in state change handler: {str(e)}")
        finally:
            self._lock.release()

    def get_state(self) -> SystemState:
        self._lock.acquire()
        try:
            if self.system_state_node is None:
                raise ValueError("System state has not been initialized.")
            state = self.system_state_node.get_state()
            return state
        finally:
            self._lock.release()

    def set_cli_state(self, state: userCLIStates):
        self._lock.acquire()
        try:
            if self.cli_state_node is None:
                self.cli_state_node = StateNode("CLIState", state)
                logger.debug(f"Initialized cli_state_node with state: {state}")
            else:
                self.cli_state_node.set_state(state)
                logger.debug(f"Updated cli_state_node to state: {state}")
        finally:
            self._lock.release()

    def get_cli_state(self) -> userCLIStates:
        self._lock.acquire()
        try:
            if self.cli_state_node is None:
                logger.warning("CLI state has not been initialized. Returning default state.")
                return userCLIStates.NOT_ACCEPTING_COMMANDS  # Default state
            state = self.cli_state_node.get_state()
            return state
        finally:
            self._lock.release()
            
    def initialize(self):
        self._lock.acquire()
        try:
            if self.cli_state_node is None:
                self.cli_state_node = StateNode("CLIState", userCLIStates.NOT_ACCEPTING_COMMANDS)
                logger.debug("Initialized cli_state_node with default state.")
        finally:
            self._lock.release()

def get_system_state_manager() -> SystemStateManager:
    return SystemStateManager()
