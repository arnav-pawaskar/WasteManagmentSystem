import threading
import time
from typing import Dict, List, Callable
from datetime import datetime
from contracts.message_types import ZoneState

class GossipProtocol:
    """Implements gossip protocol for sharing zone state between fog nodes"""
    
    def __init__(self, zone_id: int, gossip_interval: int = 15):
        self.zone_id = zone_id
        self.gossip_interval = gossip_interval
        self.running = False
        
        # State management
        self.current_state: ZoneState = None
        self.peer_states: Dict[int, ZoneState] = {}
        
        # Callbacks for state updates
        self.state_update_callbacks: List[Callable[[ZoneState], None]] = []
        
        # Gossip history to prevent loops
        self.gossip_history: Dict[str, datetime] = {}
        self.history_cleanup_interval = 300  # 5 minutes
    
    def add_state_update_callback(self, callback: Callable[[ZoneState], None]):
        """Add callback for state updates"""
        self.state_update_callbacks.append(callback)
    
    def _notify_state_update(self, state: ZoneState):
        """Notify all callbacks about state update"""
        for callback in self.state_update_callbacks:
            try:
                callback(state)
            except Exception as e:
                print(f"Error in state update callback: {e}")
    
    def update_local_state(self, state: ZoneState):
        """Update local zone state"""
        self.current_state = state
        print(f"Zone {self.zone_id}: Updated local state - {state.active_bins} active bins")
    
    def receive_gossip(self, sender_zone: int, state: ZoneState, message_id: str = None):
        """Receive gossip message from another zone"""
        if sender_zone == self.zone_id:
            return  # Ignore own messages
        
        # Check if we've seen this message before (to prevent loops)
        if message_id and message_id in self.gossip_history:
            return
        
        # Add to history
        if message_id:
            self.gossip_history[message_id] = datetime.now()
        
        # Update peer state
        old_state = self.peer_states.get(sender_zone)
        self.peer_states[sender_zone] = state
        
        print(f"Zone {self.zone_id}: Received gossip from Zone {sender_zone} - {state.active_bins} active bins")
        
        # Notify about state change
        self._notify_state_update(state)
        
        # Continue gossip (with probability to prevent flooding)
        if random.random() < 0.7:  # 70% chance to continue gossip
            self._forward_gossip(sender_zone, state, message_id)
    
    def _forward_gossip(self, original_sender: int, state: ZoneState, message_id: str = None):
        """Forward gossip to other peers"""
        # In real implementation, this would send to actual network peers
        # For simulation, this is handled by the fog node simulator
        pass
    
    def share_zone_state(self):
        """Share current zone state with peers"""
        if not self.current_state:
            return
        
        message_id = f"gossip_{self.zone_id}_{datetime.now().timestamp()}"
        print(f"Zone {self.zone_id}: Sharing zone state with peers - {self.current_state.active_bins} active bins")
        
        # In real implementation, this would broadcast to network
        # For simulation, this is handled by the fog node simulator
        return message_id
    
    def get_peer_states(self) -> Dict[int, ZoneState]:
        """Get all known peer states"""
        return self.peer_states.copy()
    
    def get_state_by_zone(self, zone_id: int) -> ZoneState:
        """Get specific peer state"""
        return self.peer_states.get(zone_id)
    
    def get_load_statistics(self) -> Dict:
        """Get load statistics across all zones"""
        all_states = {self.zone_id: self.current_state} if self.current_state else {}
        all_states.update(self.peer_states)
        
        if not all_states:
            return {}
        
        active_bins = [state.active_bins for state in all_states.values()]
        truck_counts = [state.truck_count for state in all_states.values()]
        
        return {
            "total_zones": len(all_states),
            "total_active_bins": sum(active_bins),
            "total_trucks": sum(truck_counts),
            "avg_active_bins_per_zone": sum(active_bins) / len(active_bins) if active_bins else 0,
            "max_active_bins": max(active_bins) if active_bins else 0,
            "min_active_bins": min(active_bins) if active_bins else 0,
            "zone_details": {
                zone_id: {
                    "active_bins": state.active_bins,
                    "truck_count": state.truck_count,
                    "last_update": state.timestamp.isoformat()
                }
                for zone_id, state in all_states.items()
            }
        }
    
    def find_least_loaded_zone(self, exclude_zones: List[int] = None) -> int:
        """Find the zone with the least load"""
        exclude_zones = exclude_zones or []
        exclude_zones.append(self.zone_id)  # Exclude self
        
        candidate_zones = {
            zone_id: state.active_bins 
            for zone_id, state in self.peer_states.items()
            if zone_id not in exclude_zones
        }
        
        if not candidate_zones:
            return None
        
        return min(candidate_zones, key=candidate_zones.get)
    
    def find_most_loaded_zone(self, exclude_zones: List[int] = None) -> int:
        """Find the zone with the most load"""
        exclude_zones = exclude_zones or []
        exclude_zones.append(self.zone_id)  # Exclude self
        
        candidate_zones = {
            zone_id: state.active_bins 
            for zone_id, state in self.peer_states.items()
            if zone_id not in exclude_zones
        }
        
        if not candidate_zones:
            return None
        
        return max(candidate_zones, key=candidate_zones.get)
    
    def cleanup_old_history(self):
        """Clean up old gossip history entries"""
        current_time = datetime.now()
        expired_messages = []
        
        for message_id, timestamp in self.gossip_history.items():
            if (current_time - timestamp).seconds > self.history_cleanup_interval:
                expired_messages.append(message_id)
        
        for message_id in expired_messages:
            del self.gossip_history[message_id]
    
    def start_gossip_service(self):
        """Start the gossip service"""
        if self.running:
            print("Gossip service already running")
            return
        
        self.running = True
        print(f"Zone {self.zone_id}: Starting gossip service")
        
        def gossip_loop():
            while self.running:
                self.share_zone_state()
                self.cleanup_old_history()
                time.sleep(self.gossip_interval)
        
        self.gossip_thread = threading.Thread(target=gossip_loop, daemon=True)
        self.gossip_thread.start()
    
    def stop_gossip_service(self):
        """Stop the gossip service"""
        self.running = False
        print(f"Zone {self.zone_id}: Gossip service stopped")

# Add missing import
import random
