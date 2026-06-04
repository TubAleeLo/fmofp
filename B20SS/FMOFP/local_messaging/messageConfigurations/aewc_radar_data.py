"""
AEWC Radar Data Message Configuration

This module defines message structures for AEWC (Airborne Early Warning and Control) radar data communications.
"""

import datetime
from typing import Dict, Any, Optional, List, Union

from .base_message import BaseMessage, register_message_type


class aewc_radarTrackRequest(BaseMessage):
    """
    Request for track data from AEWC radar.
    """
    
    def __init__(self, message_header="data_request", sending_system=None, destination=None, 
                 request_uuid=None, track_parameters=None):
        """
        Initialize an AEWC radar track request message.
        
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
    def deserialize(cls, data: Dict[str, Any]) -> 'aewc_radarTrackRequest':
        """
        Deserialize a dictionary to an AEWC radar track request.
        
        Args:
            data: Dictionary containing serialized data
            
        Returns:
            An AEWC radar track request instance
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


class aewc_radarSectorScanRequest(BaseMessage):
    """
    Request for sector scan from AEWC radar.
    """
    
    def __init__(self, message_header="data_request", sending_system=None, destination=None, 
                 request_uuid=None, sector_parameters=None):
        """
        Initialize an AEWC radar sector scan request message.
        
        Args:
            message_header: Message header type
            sending_system: System sending the message
            destination: Target system for the message
            request_uuid: Unique identifier for the request
            sector_parameters: Dictionary of sector scan parameters
        """
        super().__init__(message_header, sending_system, destination, request_uuid)
        
        self.sector_parameters = sector_parameters or {}
        self.command_type = "sector_scan"
        
    def serialize(self) -> Dict[str, Any]:
        """Serialize the message to a dictionary."""
        data = super().serialize()
        data.update({
            "sector_parameters": self.sector_parameters,
            "command_type": self.command_type
        })
        return data
        
    @classmethod
    def deserialize(cls, data: Dict[str, Any]) -> 'aewc_radarSectorScanRequest':
        """
        Deserialize a dictionary to an AEWC radar sector scan request.
        
        Args:
            data: Dictionary containing serialized data
            
        Returns:
            An AEWC radar sector scan request instance
        """
        instance = cls(
            message_header=data.get('message_header', 'data_request'),
            sending_system=data.get('sending_system'),
            destination=data.get('destination'),
            request_uuid=data.get('request_uuid'),
            sector_parameters=data.get('sector_parameters', {})
        )
        
        if 'command_type' in data:
            instance.command_type = data['command_type']
            
        # Transfer metadata if present
        if 'metadata' in data:
            instance.metadata = data['metadata']
            
        return instance


class aewc_radarTrackResponse(BaseMessage):
    """
    Response with track data from AEWC radar.
    """
    
    def __init__(self, message_header="data_response", sending_system=None, destination=None, 
                 request_uuid=None, track_data=None):
        """
        Initialize an AEWC radar track response message.
        
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
    def deserialize(cls, data: Dict[str, Any]) -> 'aewc_radarTrackResponse':
        """
        Deserialize a dictionary to an AEWC radar track response.
        
        Args:
            data: Dictionary containing serialized data
            
        Returns:
            An AEWC radar track response instance
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


class aewc_radarSectorScanResponse(BaseMessage):
    """
    Response with sector scan data from AEWC radar.
    """
    
    def __init__(self, message_header="data_response", sending_system=None, destination=None, 
                 request_uuid=None, sector_data=None):
        """
        Initialize an AEWC radar sector scan response message.
        
        Args:
            message_header: Message header type
            sending_system: System sending the message
            destination: Target system for the message
            request_uuid: Unique identifier for the request
            sector_data: Sector scan data
        """
        super().__init__(message_header, sending_system, destination, request_uuid)
        
        self.sector_data = sector_data or {}
        self.command_type = "sector_scan"
        
    def serialize(self) -> Dict[str, Any]:
        """Serialize the message to a dictionary."""
        data = super().serialize()
        data.update({
            "sector_data": self.sector_data,
            "command_type": self.command_type
        })
        return data
        
    @classmethod
    def deserialize(cls, data: Dict[str, Any]) -> 'aewc_radarSectorScanResponse':
        """
        Deserialize a dictionary to an AEWC radar sector scan response.
        
        Args:
            data: Dictionary containing serialized data
            
        Returns:
            An AEWC radar sector scan response instance
        """
        instance = cls(
            message_header=data.get('message_header', 'data_response'),
            sending_system=data.get('sending_system'),
            destination=data.get('destination'),
            request_uuid=data.get('request_uuid'),
            sector_data=data.get('sector_data', {})
        )
        
        if 'command_type' in data:
            instance.command_type = data['command_type']
            
        # Transfer metadata if present
        if 'metadata' in data:
            instance.metadata = data['metadata']
            
        return instance


# Register message types
register_message_type("aewc_radarTrackRequest", aewc_radarTrackRequest)
register_message_type("aewc_radarSectorScanRequest", aewc_radarSectorScanRequest)
register_message_type("aewc_radarTrackResponse", aewc_radarTrackResponse)
register_message_type("aewc_radarSectorScanResponse", aewc_radarSectorScanResponse)
