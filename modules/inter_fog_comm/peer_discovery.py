import threading
import time
from typing import Dict, List, Set, Callable
from datetime import datetime
from contracts.message_types import ZoneState

class PeerDiscovery:
    """Manages discovery of other fog nodes in the network"""
    
    def __init__(self, zone_id: int, broadcast_interval: int = 10):
        self.zone_id = zone_id
        self.broadcast_interval = broadcast_interval
        self.peer_registry: Dict[int, ZoneState] = {}
        self.running = False
        
        # Callbacks for peer events
        self.peer_discovered_callbacks: List[Callable[[ZoneState], None]] = []
        self.peer_lost_callbacks: List[Callable[[int], None]] = []
        
        # Heartbeat tracking
        self.peer_heartbeats: Dict[int, datetime] = {}
        self.heartbeat_timeout = 30  # seconds
    
    def add_peer_discovered_callback(self, callback: Callable[[ZoneState], None]):
        """Add callback for when a new peer is discovered"""
        self.peer_discovered_callbacks.append(callback)
    
    def add_peer_lost_callback(self, callback: Callable[[int], None]):
        """Add callback for when a peer is lost"""
        self.peer_lost_callbacks.append(callback)
    
    def _notify_peer_discovered(self, peer_state: ZoneState):
        """Notify all callbacks about discovered peer"""
        for callback in self.peer_discovered_callbacks:
            try:
                callback(peer_state)
            except Exception as e:
                print(f"Error in peer discovered callback: {e}")
    
    def _notify_peer_lost(self, zone_id: int):
        """Notify all callbacks about lost peer"""
        for callback in self.peer_lost_callbacks:
            try:
                callback(zone_id)
            except Exception as e:
                print(f"Error in peer lost callback: {e}")
    
    def register_peer(self, peer_state: ZoneState):
        """Register a new peer or update existing peer"""
        if peer_state.zone_id == self.zone_id:
            return  # Don't register self
        
        self.peer_registry[peer_state.zone_id] = peer_state
        self.peer_heartbeats[peer_state.zone_id] = datetime.now()
        
        print(f"Zone {self.zone_id}: Discovered peer Zone {peer_state.zone_id}")
        self._notify_peer_discovered(peer_state)
    
    def create_zone_state(self, active_bins: int, truck_count: int) -> ZoneState:
        """Create current zone state for broadcasting"""
        return ZoneState(
            zone_id=self.zone_id,
            active_bins=active_bins,
            truck_count=truck_count,
            timestamp=datetime.now()
        )
    
    def broadcast_presence(self, zone_state: ZoneState):
        """Broadcast zone presence to network (simulated)"""
        # In real implementation, this would send network messages
        # For simulation, we'll use a shared registry approach
        print(f"Zone {self.zone_id}: Broadcasting presence - {zone_state.active_bins} active bins")
        
        # This would be replaced with actual network broadcast
        # For now, other zones will call register_peer directly
    
    def discover_peers(self) -> List[ZoneState]:
        """Get list of all discovered peers"""
        return list(self.peer_registry.values())
    
    def get_peer_by_zone(self, zone_id: int) -> ZoneState:
        """Get specific peer by zone ID"""
        return self.peer_registry.get(zone_id)
    
    def update_peer_heartbeat(self, zone_id: int):
        """Update heartbeat timestamp for a peer"""
        if zone_id in self.peer_heartbeats:
            self.peer_heartbeats[zone_id] = datetime.now()
    
    def check_peer_health(self):
        """Check for inactive peers and remove them"""
        current_time = datetime.now()
        inactive_peers = []
        
        for zone_id, last_heartbeat in self.peer_heartbeats.items():
            if (current_time - last_heartbeat).seconds > self.heartbeat_timeout:
                inactive_peers.append(zone_id)
        
        for zone_id in inactive_peers:
            print(f"Zone {self.zone_id}: Lost peer Zone {zone_id} (timeout)")
            del self.peer_registry[zone_id]
            del self.peer_heartbeats[zone_id]
            self._notify_peer_lost(zone_id)
    
    def start_discovery_service(self):
        """Start the peer discovery service"""
        if self.running:
            print("Peer discovery service already running")
            return
        
        self.running = True
        print(f"Zone {self.zone_id}: Starting peer discovery service")
        
        def discovery_loop():
            while self.running:
                self.check_peer_health()
                time.sleep(5)  # Check health every 5 seconds
        
        self.discovery_thread = threading.Thread(target=discovery_loop, daemon=True)
        self.discovery_thread.start()
    
    def stop_discovery_service(self):
        """Stop the peer discovery service"""
        self.running = False
        print(f"Zone {self.zone_id}: Peer discovery service stopped")
    
    def get_peer_statistics(self) -> Dict:
        """Get statistics about discovered peers"""
        return {
            "total_peers": len(self.peer_registry),
            "peer_zones": list(self.peer_registry.keys()),
            "peer_states": {
                zone_id: {
                    "active_bins": state.active_bins,
                    "truck_count": state.truck_count,
                    "last_seen": self.peer_heartbeats.get(zone_id, datetime.min).isoformat()
                }
                for zone_id, state in self.peer_registry.items()
            }
        }
