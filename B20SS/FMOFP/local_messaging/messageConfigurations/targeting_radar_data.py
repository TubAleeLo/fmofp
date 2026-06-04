"""
Targeting Radar Data Message Configuration

This module defines message structures for targeting radar data communications.
"""

import datetime
from typing import Dict, Any, Optional, List, Union

from .base_message import BaseMessage, register_message_type


class targeting_radarTrackRequest(BaseMessage):
    """
    Request for track data from targeting radar.
    """
    
    def __init__(self, message_header="data_request", sending_system=None, destination=None, 
                 request_uuid=None, track_parameters=None):
        """
        Initialize a targeting radar track request message.
        
        Args:
            message_header: Message header type
            sending_system: System sending the message
            destination: Target system for the message
            request_uuid: Unique identifier for the request
            track_parameters: Dictionary of track parameters
        """
        super().__init__(message_header, sending_system, destination, request_uuid)
        
        self.track_parameters = track_parameters or {}
        self.command_type = "track_data"
        
    def serialize(self) -> Dict[str, Any]:
        """Serialize the message to a dictionary."""
        data = super().serialize()
        data.update({
            "track_parameters": self.track_parameters,
            "command_type": self.command_type
        })
        return data
        
    @classmethod
    def deserialize(cls, data: Dict[str, Any]) -> 'targeting_radarTrackRequest':
        """
        Deserialize a dictionary to a targeting radar track request.
        
        Args:
            data: Dictionary containing serialized data
            
        Returns:
            A targeting radar track request instance
        """
        instance = cls(
            message_header=data.get('message_header', 'data_request'),
            sending_system=data.get('sending_system'),
            destination=data.get('destination'),
            request_uuid=data.get('request_uuid'),
            track_parameters=data.get('track_parameters', {})
        )
        
        if 'command_type' in data:
            instance.command_type = data['command_type']
            
        # Transfer metadata if present
        if 'metadata' in data:
            instance.metadata = data['metadata']
            
        return instance


class targeting_radarLockRequest(BaseMessage):
    """
    Request to lock onto a target using targeting radar.
    """
    
    def __init__(self, message_header="data_request", sending_system=None, destination=None, 
                 request_uuid=None, lock_parameters=None):
        """
        Initialize a targeting radar lock request message.
        
        Args:
            message_header: Message header type
            sending_system: System sending the message
            destination: Target system for the message
            request_uuid: Unique identifier for the request
            lock_parameters: Dictionary of lock parameters including track_id
        """
        super().__init__(message_header, sending_system, destination, request_uuid)
        
        self.lock_parameters = lock_parameters or {}
        self.command_type = "lock_request"
        
    def serialize(self) -> Dict[str, Any]:
        """Serialize the message to a dictionary."""
        data = super().serialize()
        data.update({
            "lock_parameters": self.lock_parameters,
            "command_type": self.command_type
        })
        return data
        
    @classmethod
    def deserialize(cls, data: Dict[str, Any]) -> 'targeting_radarLockRequest':
        """
        Deserialize a dictionary to a targeting radar lock request.
        
        Args:
            data: Dictionary containing serialized data
            
        Returns:
            A targeting radar lock request instance
        """
        instance = cls(
            message_header=data.get('message_header', 'data_request'),
            sending_system=data.get('sending_system'),
            destination=data.get('destination'),
            request_uuid=data.get('request_uuid'),
            lock_parameters=data.get('lock_parameters', {})
        )
        
        if 'command_type' in data:
            instance.command_type = data['command_type']
            
        # Transfer metadata if present
        if 'metadata' in data:
            instance.metadata = data['metadata']
            
        return instance


class targeting_radarTrackResponse(BaseMessage):
    """
    Response with track data from targeting radar.
    """
    
    def __init__(self, message_header="data_response", sending_system=None, destination=None, 
                 request_uuid=None, track_data=None):
        """
        Initialize a targeting radar track response message.
        
        Args:
            message_header: Message header type
            sending_system: System sending the message
            destination: Target system for the message
            request_uuid: Unique identifier for the request
            track_data: Dictionary or list of dictionaries containing track data
        """
        super().__init__(message_header, sending_system, destination, request_uuid)
        
        self.track_data = track_data or []
        self.command_type = "track_data"
        
    def serialize(self) -> Dict[str, Any]:
        """Serialize the message to a dictionary."""
        data = super().serialize()
        data.update({
            "track_data": self.track_data,
            "command_type": self.command_type
        })
        return data
        
    @classmethod
    def deserialize(cls, data: Dict[str, Any]) -> 'targeting_radarTrackResponse':
        """
        Deserialize a dictionary to a targeting radar track response.
        
        Args:
            data: Dictionary containing serialized data
            
        Returns:
            A targeting radar track response instance
        """
        instance = cls(
            message_header=data.get('message_header', 'data_response'),
            sending_system=data.get('sending_system'),
            destination=data.get('destination'),
            request_uuid=data.get('request_uuid'),
            track_data=data.get('track_data', [])
        )
        
        if 'command_type' in data:
            instance.command_type = data['command_type']
            
        # Transfer metadata if present
        if 'metadata' in data:
            instance.metadata = data['metadata']
            
        return instance


class targeting_radarLockResponse(BaseMessage):
    """
    Response to a lock request from targeting radar.
    """
    
    def __init__(self, message_header="data_response", sending_system=None, destination=None, 
                 request_uuid=None, lock_status=None, lock_data=None):
        """
        Initialize a targeting radar lock response message.
        
        Args:
            message_header: Message header type
            sending_system: System sending the message
            destination: Target system for the message
            request_uuid: Unique identifier for the request
            lock_status: Status of the lock request (e.g., "success", "failed")
            lock_data: Additional data about the lock
        """
        super().__init__(message_header, sending_system, destination, request_uuid)
        
        self.lock_status = lock_status or "unknown"
        self.lock_data = lock_data or {}
        self.command_type = "lock_response"
        
    def serialize(self) -> Dict[str, Any]:
        """Serialize the message to a dictionary."""
        data = super().serialize()
        data.update({
            "lock_status": self.lock_status,
            "lock_data": self.lock_data,
            "command_type": self.command_type
        })
        return data
        
    @classmethod
    def deserialize(cls, data: Dict[str, Any]) -> 'targeting_radarLockResponse':
        """
        Deserialize a dictionary to a targeting radar lock response.
        
        Args:
            data: Dictionary containing serialized data
            
        Returns:
            A targeting radar lock response instance
        """
        instance = cls(
            message_header=data.get('message_header', 'data_response'),
            sending_system=data.get('sending_system'),
            destination=data.get('destination'),
            request_uuid=data.get('request_uuid'),
            lock_status=data.get('lock_status', 'unknown'),
            lock_data=data.get('lock_data', {})
        )
        
        if 'command_type' in data:
            instance.command_type = data['command_type']
            
        # Transfer metadata if present
        if 'metadata' in data:
            instance.metadata = data['metadata']
            
        return instance
    
    
# Register message types
register_message_type("targeting_radarTrackRequest", targeting_radarTrackRequest)
register_message_type("targeting_radarLockRequest", targeting_radarLockRequest)
register_message_type("targeting_radarTrackResponse", targeting_radarTrackResponse)
register_message_type("targeting_radarLockResponse", targeting_radarLockResponse)
