from typing import Dict, List, Callable, Any
from datetime import datetime
import uuid
from contracts.message_types import ZoneState, SpilloverRequest, SpilloverResponse

class MessageRouter:
    """Routes messages between fog nodes"""
    
    def __init__(self, zone_id: int):
        self.zone_id = zone_id
        
        # Message handlers
        self.handlers: Dict[str, Callable] = {}
        self.message_queue: List[Dict] = []

        # Message tracking. Capped: a fog node runs indefinitely, and unbounded
        # per-message dicts were the main source of memory growth over long runs.
        self.sent_messages: Dict[str, Dict] = {}
        self.received_messages: Dict[str, Dict] = {}
        self.max_tracked = 1000
        self.total_sent = 0
        self.total_received = 0

    @staticmethod
    def _trim(store: Dict[str, Dict], limit: int):
        """Drop oldest entries once the store exceeds its cap (dicts keep insertion order)."""
        excess = len(store) - limit
        if excess > 0:
            for key in list(store)[:excess]:
                del store[key]
    
    def register_handler(self, message_type: str, handler: Callable):
        """Register a handler for a specific message type"""
        self.handlers[message_type] = handler
        print(f"Zone {self.zone_id}: Registered handler for {message_type}")
    
    def send_message(self, target_zone: int, message_type: str, 
                    message_data: Any, message_id: str = None) -> str:
        """Send a message to another zone"""
        if not message_id:
            message_id = f"msg_{self.zone_id}_{target_zone}_{uuid.uuid4().hex[:8]}"
        
        message = {
            "id": message_id,
            "sender": self.zone_id,
            "receiver": target_zone,
            "type": message_type,
            "data": message_data,
            "timestamp": datetime.now(),
            "status": "sent"
        }
        
        self.sent_messages[message_id] = message
        self.total_sent += 1
        self._trim(self.sent_messages, self.max_tracked)

        print(f"Zone {self.zone_id}: Sending {message_type} to Zone {target_zone}")
        
        # In real implementation, this would send over network
        # For simulation, we'll queue it for delivery
        self.message_queue.append(message)
        
        return message_id
    
    def receive_message(self, message: Dict) -> bool:
        """Process an incoming message"""
        if message["receiver"] != self.zone_id:
            return False
        
        message_id = message["id"]
        message_type = message["type"]
        
        # Check if already received
        if message_id in self.received_messages:
            return False
        
        # Record message
        message["status"] = "received"
        self.received_messages[message_id] = message
        self.total_received += 1
        self._trim(self.received_messages, self.max_tracked)

        print(f"Zone {self.zone_id}: Received {message_type} from Zone {message['sender']}")
        
        # Handle message
        if message_type in self.handlers:
            try:
                self.handlers[message_type](message["data"], message["sender"])
                return True
            except Exception as e:
                print(f"Zone {self.zone_id}: Error handling {message_type}: {e}")
                return False
        else:
            print(f"Zone {self.zone_id}: No handler for {message_type}")
            return False
    
    def get_pending_messages(self) -> List[Dict]:
        """Get all pending messages in queue"""
        return [msg for msg in self.message_queue if msg["status"] == "sent"]
    
    def mark_message_delivered(self, message_id: str):
        """Mark a message as delivered"""
        if message_id in self.sent_messages:
            self.sent_messages[message_id]["status"] = "delivered"
            
        # Remove from queue
        self.message_queue = [msg for msg in self.message_queue if msg["id"] != message_id]
    
    def get_message_statistics(self) -> Dict:
        """Get messaging statistics"""
        sent_stats = {}
        for msg in self.sent_messages.values():
            msg_type = msg["type"]
            if msg_type not in sent_stats:
                sent_stats[msg_type] = {"total": 0, "delivered": 0}
            sent_stats[msg_type]["total"] += 1
            if msg["status"] == "delivered":
                sent_stats[msg_type]["delivered"] += 1
        
        received_stats = {}
        for msg in self.received_messages.values():
            msg_type = msg["type"]
            if msg_type not in received_stats:
                received_stats[msg_type] = 0
            received_stats[msg_type] += 1
        
        return {
            "messages_sent": self.total_sent,
            "messages_received": self.total_received,
            "messages_tracked": len(self.sent_messages) + len(self.received_messages),
            "messages_pending": len(self.get_pending_messages()),
            "sent_by_type": sent_stats,
            "received_by_type": received_stats
        }

class InterFogCommunicator:
    """Main inter-fog communication coordinator"""
    
    def __init__(self, zone_id: int, overload_threshold: int = 10):
        self.zone_id = zone_id
        self.message_router = MessageRouter(zone_id)
        
        # Import other modules to avoid circular imports
        from .peer_discovery import PeerDiscovery
        from .gossip import GossipProtocol
        from .spillover import SpilloverManager
        
        self.peer_discovery = PeerDiscovery(zone_id)
        self.gossip_protocol = GossipProtocol(zone_id)
        self.spillover_manager = SpilloverManager(zone_id, overload_threshold)
        
        # Register message handlers
        self._register_handlers()
        
        # State tracking
        self.current_state: ZoneState = None
        self.overflowing_bins = []
    
    def _register_handlers(self):
        """Register message handlers with the router"""
        self.message_router.register_handler("zone_state", self._handle_zone_state)
        self.message_router.register_handler("spillover_request", self._handle_spillover_request)
        self.message_router.register_handler("spillover_response", self._handle_spillover_response)
        self.message_router.register_handler("peer_discovery", self._handle_peer_discovery)
    
    def _handle_zone_state(self, zone_state: ZoneState, sender_zone: int):
        """Handle incoming zone state gossip"""
        self.gossip_protocol.receive_gossip(sender_zone, zone_state)
        # Registering also refreshes the peer's heartbeat, so an active gossip
        # stream keeps a peer alive and a previously timed-out peer is readmitted.
        self.peer_discovery.register_peer(zone_state)
    
    def _handle_spillover_request(self, request: SpilloverRequest, sender_zone: int):
        """Handle incoming spillover request"""
        response = self.spillover_manager.receive_spillover_request(request, self.current_state)
        
        # Send response back
        self.message_router.send_message(
            sender_zone, 
            "spillover_response", 
            response
        )
    
    def _handle_spillover_response(self, response: SpilloverResponse, sender_zone: int):
        """Handle incoming spillover response"""
        self.spillover_manager.receive_spillover_response(response)
    
    def _handle_peer_discovery(self, peer_state: ZoneState, sender_zone: int):
        """Handle peer discovery message"""
        self.peer_discovery.register_peer(peer_state)
    
    def update_state(self, active_bins: int, truck_count: int, overflowing_bins = None):
        """Update current zone state"""
        self.current_state = ZoneState(
            zone_id=self.zone_id,
            active_bins=active_bins,
            truck_count=truck_count,
            timestamp=datetime.now()
        )
        
        if overflowing_bins is not None:
            self.overflowing_bins = overflowing_bins
        
        # Update gossip protocol
        self.gossip_protocol.update_local_state(self.current_state)

        # Push state to a random subset of peers (rumour-mongering, Section IV-C)
        self.gossip_to_peers(self.current_state)

        # Check for spillover needs
        self._check_spillover_needs()
    
    def _check_spillover_needs(self):
        """Check if spillover is needed and initiate if so"""
        if not self.current_state or not self.overflowing_bins:
            return
        
        peer_states = self.gossip_protocol.get_peer_states()
        request = self.spillover_manager.initiate_spillover(
            self.current_state, 
            self.overflowing_bins, 
            peer_states
        )
        
        if request:
            # Send spillover request
            self.message_router.send_message(
                request.receiver_zone,
                "spillover_request",
                request
            )
    
    def gossip_to_peers(self, message_data: Any):
        """
        Push zone state to a randomly chosen subset of peers.

        Targets are drawn from live peers plus the configured roster, so a peer that
        has timed out still receives state and can be rediscovered.
        """
        targets = self.gossip_protocol.select_gossip_targets(
            self.peer_discovery.presence_targets())

        for zone_id in targets:
            self.message_router.send_message(zone_id, "zone_state", message_data)

    def broadcast_to_peers(self, message_type: str, message_data: Any):
        """Send a message to every known peer (used for non-gossip traffic)"""
        for zone_id in self.peer_discovery.presence_targets():
            self.message_router.send_message(
                zone_id,
                message_type,
                message_data
            )
    
    def get_communication_status(self) -> Dict:
        """Get overall communication status"""
        return {
            "zone_id": self.zone_id,
            "peer_discovery": self.peer_discovery.get_peer_statistics(),
            "gossip_protocol": self.gossip_protocol.get_load_statistics(),
            "spillover_manager": self.spillover_manager.get_spillover_statistics(),
            "message_router": self.message_router.get_message_statistics(),
            "current_state": {
                "active_bins": self.current_state.active_bins if self.current_state else 0,
                "truck_count": self.current_state.truck_count if self.current_state else 0,
                "last_update": self.current_state.timestamp.isoformat() if self.current_state else None
            }
        }
    
    def start_services(self):
        """Start all communication services"""
        self.peer_discovery.start_discovery_service()
        self.gossip_protocol.start_gossip_service()
        print(f"Zone {self.zone_id}: All communication services started")
    
    def stop_services(self):
        """Stop all communication services"""
        self.peer_discovery.stop_discovery_service()
        self.gossip_protocol.stop_gossip_service()
        print(f"Zone {self.zone_id}: All communication services stopped")
