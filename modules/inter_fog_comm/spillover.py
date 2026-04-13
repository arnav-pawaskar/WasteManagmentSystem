from typing import List, Dict, Optional, Callable
from datetime import datetime
from contracts.message_types import ZoneState, SpilloverRequest, SpilloverResponse, BinTelemetry

class SpilloverManager:
    """Manages load balancing through bin spillover between zones"""
    
    def __init__(self, zone_id: int, overload_threshold: int = 10):
        self.zone_id = zone_id
        self.overload_threshold = overload_threshold
        
        # Spillover tracking
        self.pending_spillovers: Dict[int, SpilloverRequest] = {}
        self.spillover_history: List[Dict] = []
        
        # Callbacks for spillover events
        self.spillover_request_callbacks: List[Callable[[SpilloverRequest], None]] = []
        self.spillover_response_callbacks: List[Callable[[SpilloverResponse], None]] = []
        self.spillover_completed_callbacks: List[Callable[[int, List[str]], None]] = []
    
    def add_spillover_request_callback(self, callback: Callable[[SpilloverRequest], None]):
        """Add callback for spillover requests"""
        self.spillover_request_callbacks.append(callback)
    
    def add_spillover_response_callback(self, callback: Callable[[SpilloverResponse], None]):
        """Add callback for spillover responses"""
        self.spillover_response_callbacks.append(callback)
    
    def add_spillover_completed_callback(self, callback: Callable[[int, List[str]], None]):
        """Add callback for completed spillovers"""
        self.spillover_completed_callbacks.append(callback)
    
    def _notify_spillover_request(self, request: SpilloverRequest):
        """Notify about spillover request"""
        for callback in self.spillover_request_callbacks:
            try:
                callback(request)
            except Exception as e:
                print(f"Error in spillover request callback: {e}")
    
    def _notify_spillover_response(self, response: SpilloverResponse):
        """Notify about spillover response"""
        for callback in self.spillover_response_callbacks:
            try:
                callback(response)
            except Exception as e:
                print(f"Error in spillover response callback: {e}")
    
    def _notify_spillover_completed(self, target_zone: int, bin_ids: List[str]):
        """Notify about completed spillover"""
        for callback in self.spillover_completed_callbacks:
            try:
                callback(target_zone, bin_ids)
            except Exception as e:
                print(f"Error in spillover completed callback: {e}")
    
    def check_overload(self, current_state: ZoneState) -> bool:
        """Check if current zone is overloaded"""
        return current_state.is_overloaded(self.overload_threshold)
    
    def initiate_spillover(self, current_state: ZoneState, 
                          overflowing_bins: List[BinTelemetry],
                          peer_zones: Dict[int, ZoneState]) -> Optional[SpilloverRequest]:
        """Initiate spillover to least loaded peer"""
        if not self.check_overload(current_state):
            return None
        
        # Find least loaded peer
        if not peer_zones:
            print(f"Zone {self.zone_id}: No peers available for spillover")
            return None
        
        least_loaded_zone = min(peer_zones.keys(), 
                              key=lambda z: peer_zones[z].active_bins)
        
        # Calculate how many bins to transfer
        excess_bins = current_state.active_bins - self.overload_threshold
        bins_to_transfer = min(excess_bins, len(overflowing_bins))
        
        if bins_to_transfer <= 0:
            return None
        
        # Select bins to transfer (prioritize lowest priority)
        bins_for_spillover = overflowing_bins[-bins_to_transfer:]
        bin_ids = [bin_telemetry.bin_id for bin_telemetry in bins_for_spillover]
        
        request = SpilloverRequest(
            sender_zone=self.zone_id,
            receiver_zone=least_loaded_zone,
            bin_ids=bin_ids,
            timestamp=datetime.now()
        )
        
        self.pending_spillovers[least_loaded_zone] = request
        
        print(f"Zone {self.zone_id}: Initiating spillover to Zone {least_loaded_zone} - {len(bin_ids)} bins")
        self._notify_spillover_request(request)
        
        return request
    
    def receive_spillover_request(self, request: SpilloverRequest, 
                                 current_state: ZoneState) -> SpilloverResponse:
        """Process incoming spillover request"""
        if request.receiver_zone != self.zone_id:
            raise ValueError("Invalid spillover request receiver")
        
        # Check if we can accept the spillover
        can_accept = not current_state.is_overloaded(self.overload_threshold)
        
        response = SpilloverResponse(
            sender_zone=self.zone_id,
            receiver_zone=request.sender_zone,
            accepted=can_accept,
            bin_ids=request.bin_ids if can_accept else [],
            timestamp=datetime.now()
        )
        
        print(f"Zone {self.zone_id}: {'Accepted' if can_accept else 'Rejected'} spillover request from Zone {request.sender_zone}")
        self._notify_spillover_response(response)
        
        return response
    
    def receive_spillover_response(self, response: SpilloverResponse):
        """Process spillover response"""
        if response.receiver_zone != self.zone_id:
            raise ValueError("Invalid spillover response receiver")
        
        original_request = self.pending_spillovers.get(response.sender_zone)
        if not original_request:
            print(f"Zone {self.zone_id}: Received response for unknown spillover request")
            return
        
        if response.accepted:
            print(f"Zone {self.zone_id}: Spillover to Zone {response.sender_zone} accepted - {len(response.bin_ids)} bins")
            
            # Record successful spillover
            self.spillover_history.append({
                "timestamp": datetime.now().isoformat(),
                "from_zone": self.zone_id,
                "to_zone": response.sender_zone,
                "bin_count": len(response.bin_ids),
                "bin_ids": response.bin_ids,
                "status": "completed"
            })
            
            # Notify about completion
            self._notify_spillover_completed(response.sender_zone, response.bin_ids)
        else:
            print(f"Zone {self.zone_id}: Spillover to Zone {response.sender_zone} rejected")
            
            # Record rejected spillover
            self.spillover_history.append({
                "timestamp": datetime.now().isoformat(),
                "from_zone": self.zone_id,
                "to_zone": response.sender_zone,
                "bin_count": len(original_request.bin_ids),
                "bin_ids": original_request.bin_ids,
                "status": "rejected"
            })
        
        # Remove from pending
        del self.pending_spillovers[response.sender_zone]
    
    def get_spillover_statistics(self) -> Dict:
        """Get spillover statistics"""
        completed = [s for s in self.spillover_history if s["status"] == "completed"]
        rejected = [s for s in self.spillover_history if s["status"] == "rejected"]
        
        return {
            "total_spillovers": len(self.spillover_history),
            "completed_spillovers": len(completed),
            "rejected_spillovers": len(rejected),
            "success_rate": len(completed) / len(self.spillover_history) * 100 if self.spillover_history else 0,
            "pending_spillovers": len(self.pending_spillovers),
            "bins_transferred": sum(s["bin_count"] for s in completed),
            "recent_activity": self.spillover_history[-5:] if self.spillover_history else []
        }
    
    def get_pending_spillovers(self) -> Dict[int, SpilloverRequest]:
        """Get all pending spillover requests"""
        return self.pending_spillovers.copy()
    
    def cancel_spillover(self, target_zone: int):
        """Cancel a pending spillover request"""
        if target_zone in self.pending_spillovers:
            request = self.pending_spillovers[target_zone]
            del self.pending_spillovers[target_zone]
            
            print(f"Zone {self.zone_id}: Cancelled spillover to Zone {target_zone}")
            
            # Record cancellation
            self.spillover_history.append({
                "timestamp": datetime.now().isoformat(),
                "from_zone": self.zone_id,
                "to_zone": target_zone,
                "bin_count": len(request.bin_ids),
                "bin_ids": request.bin_ids,
                "status": "cancelled"
            })
    
    def get_spillover_recommendations(self, current_state: ZoneState,
                                    peer_zones: Dict[int, ZoneState]) -> List[Dict]:
        """Get recommendations for spillover targets"""
        if not self.check_overload(current_state):
            return []
        
        recommendations = []
        excess_bins = current_state.active_bins - self.overload_threshold
        
        for zone_id, peer_state in peer_zones.items():
            if not peer_state.is_overloaded(self.overload_threshold):
                # Calculate how many bins this peer can handle
                capacity = self.overload_threshold - peer_state.active_bins
                recommended_transfer = min(excess_bins, capacity)
                
                if recommended_transfer > 0:
                    recommendations.append({
                        "target_zone": zone_id,
                        "current_load": peer_state.active_bins,
                        "capacity": capacity,
                        "recommended_bins": recommended_transfer,
                        "priority": "high" if capacity >= excess_bins else "medium"
                    })
        
        # Sort by priority and capacity
        recommendations.sort(key=lambda x: (x["priority"] == "high", x["capacity"]), reverse=True)
        
        return recommendations
