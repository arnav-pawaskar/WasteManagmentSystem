from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime
from enum import Enum

@dataclass
class BinTelemetry:
    """Represents simulated bin data"""
    bin_id: str
    zone_id: int
    x: float
    y: float
    fill_level: float
    timestamp: datetime
    
    def is_overflowing(self, threshold: float = 80.0) -> bool:
        """Check if bin is overflowing"""
        return self.fill_level >= threshold

@dataclass
class ZoneState:
    """Represents the load of a fog node"""
    zone_id: int
    active_bins: int
    truck_count: int
    timestamp: datetime
    
    def is_overloaded(self, threshold: int = 10) -> bool:
        """Check if zone is overloaded"""
        return self.active_bins > threshold

@dataclass
class RoutePlan:
    """Output from route optimization"""
    truck_id: str
    zone_id: int
    route_bins: List[str]
    route_distance: float
    
    def __post_init__(self):
        """Calculate route distance if not provided"""
        if self.route_distance == 0 and self.route_bins:
            # Will be calculated by route optimizer
            pass

class MessageType(Enum):
    """Message types for election algorithm"""
    INVITATION = "INVITATION"
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    LEADER = "LEADER"

@dataclass
class ElectionMessage:
    """Used by invitation election algorithm"""
    sender_id: str
    receiver_id: str
    message_type: MessageType
    timestamp: datetime

@dataclass
class SpilloverRequest:
    """Request to transfer bins to another zone"""
    sender_zone: int
    receiver_zone: int
    bin_ids: List[str]
    timestamp: datetime

@dataclass
class SpilloverResponse:
    """Response to spillover request"""
    sender_zone: int
    receiver_zone: int
    accepted: bool
    bin_ids: List[str]
    timestamp: datetime
