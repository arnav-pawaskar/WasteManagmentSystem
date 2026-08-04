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
        self.max_history = 200          # bounded: this runs for the life of the node

        # Peers already tried during the current overload episode. Algorithm 1 walks
        # the peer list in load order; a rejection advances to the next candidate
        # rather than re-asking the same peer forever.
        self.attempted_peers: set = set()

        # Callbacks for spillover events
        self.spillover_request_callbacks: List[Callable[[SpilloverRequest], None]] = []
        self.spillover_response_callbacks: List[Callable[[SpilloverResponse], None]] = []
        self.spillover_completed_callbacks: List[Callable[[int, List[str]], None]] = []
        # Receiver side: fired when this zone accepts responsibility for bins.
        self.spillover_adopted_callbacks: List[Callable[[int, List[BinTelemetry]], None]] = []
    
    def add_spillover_request_callback(self, callback: Callable[[SpilloverRequest], None]):
        """Add callback for spillover requests"""
        self.spillover_request_callbacks.append(callback)
    
    def add_spillover_response_callback(self, callback: Callable[[SpilloverResponse], None]):
        """Add callback for spillover responses"""
        self.spillover_response_callbacks.append(callback)
    
    def add_spillover_completed_callback(self, callback: Callable[[int, List[str]], None]):
        """Add callback for completed spillovers (sender side: release the bins)"""
        self.spillover_completed_callbacks.append(callback)

    def add_spillover_adopted_callback(self, callback: Callable[[int, List['BinTelemetry']], None]):
        """Add callback for adopted spillovers (receiver side: take the bins)"""
        self.spillover_adopted_callbacks.append(callback)

    def _notify_spillover_adopted(self, sender_zone: int, bins: List[BinTelemetry]):
        """Notify that this zone has taken ownership of transferred bins"""
        for callback in self.spillover_adopted_callbacks:
            try:
                callback(sender_zone, bins)
            except Exception as e:
                print(f"Error in spillover adopted callback: {e}")

    def _record(self, entry: Dict):
        """Append to history, keeping it bounded"""
        self.spillover_history.append(entry)
        if len(self.spillover_history) > self.max_history:
            del self.spillover_history[:-self.max_history]
    
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
        """
        Initiate spillover to the least loaded peer (Algorithm 1).

        At most one request is outstanding at a time. Peers that have already
        rejected during this overload episode are skipped, so the sender walks the
        peer list in load order instead of re-asking the same zone on every state
        update.
        """
        if current_state is None or not self.check_overload(current_state):
            # No longer overloaded: the episode is over, so forget past rejections.
            self.attempted_peers.clear()
            return None

        # One outstanding request at a time. Without this, every update_state call
        # emits a duplicate request for the same bins.
        if self.pending_spillovers:
            return None

        if not peer_zones:
            print(f"Zone {self.zone_id}: No peers available for spillover")
            return None

        # Candidate peers: not self, not already tried, not themselves overloaded.
        candidates = [
            z for z, state in peer_zones.items()
            if z != self.zone_id
            and z not in self.attempted_peers
            and not state.is_overloaded(self.overload_threshold)
        ]
        if not candidates:
            print(f"Zone {self.zone_id}: No peer with spare capacity for spillover")
            return None

        target_zone = min(candidates, key=lambda z: peer_zones[z].active_bins)

        # Transfer only as many bins as the peer can absorb without itself tipping
        # over the threshold; otherwise spillover just relocates the hotspot.
        excess_bins = current_state.active_bins - self.overload_threshold
        peer_capacity = self.overload_threshold - peer_zones[target_zone].active_bins
        bins_to_transfer = min(excess_bins, peer_capacity, len(overflowing_bins))

        if bins_to_transfer <= 0:
            return None

        # Select the lowest-priority bins; overflowing_bins arrives priority-sorted.
        bins_for_spillover = list(overflowing_bins[-bins_to_transfer:])
        bin_ids = [bin_telemetry.bin_id for bin_telemetry in bins_for_spillover]

        request = SpilloverRequest(
            sender_zone=self.zone_id,
            receiver_zone=target_zone,
            bin_ids=bin_ids,
            timestamp=datetime.now(),
            bins=bins_for_spillover,
        )

        self.pending_spillovers[target_zone] = request
        self.attempted_peers.add(target_zone)

        print(f"Zone {self.zone_id}: Initiating spillover to Zone {target_zone} - {len(bin_ids)} bins")
        self._notify_spillover_request(request)

        return request
    
    def receive_spillover_request(self, request: SpilloverRequest, 
                                 current_state: ZoneState) -> SpilloverResponse:
        """Process incoming spillover request"""
        if request.receiver_zone != self.zone_id:
            raise ValueError("Invalid spillover request receiver")

        # An unknown local state means we cannot vouch for having capacity, so
        # refuse rather than accepting work we may not be able to service.
        if current_state is None:
            can_accept = False
        else:
            # Accept only if taking these bins keeps us at or below threshold.
            projected = current_state.active_bins + len(request.bin_ids)
            can_accept = projected <= self.overload_threshold

        response = SpilloverResponse(
            sender_zone=self.zone_id,
            receiver_zone=request.sender_zone,
            accepted=can_accept,
            bin_ids=request.bin_ids if can_accept else [],
            timestamp=datetime.now()
        )

        print(f"Zone {self.zone_id}: {'Accepted' if can_accept else 'Rejected'} spillover request from Zone {request.sender_zone}")

        if can_accept:
            # Take ownership. Without this the transfer is only ever recorded.
            adopted = [b for b in request.bins if b.bin_id in set(request.bin_ids)]
            self._record({
                "timestamp": datetime.now().isoformat(),
                "from_zone": request.sender_zone,
                "to_zone": self.zone_id,
                "bin_count": len(adopted),
                "bin_ids": list(request.bin_ids),
                "status": "adopted",
            })
            self._notify_spillover_adopted(request.sender_zone, adopted)

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

            self._record({
                "timestamp": datetime.now().isoformat(),
                "from_zone": self.zone_id,
                "to_zone": response.sender_zone,
                "bin_count": len(response.bin_ids),
                "bin_ids": response.bin_ids,
                "status": "completed"
            })

            # The episode resolved; a later overload starts a fresh peer walk.
            self.attempted_peers.clear()

            # Sender side releases the bins it just handed off.
            self._notify_spillover_completed(response.sender_zone, response.bin_ids)
        else:
            print(f"Zone {self.zone_id}: Spillover to Zone {response.sender_zone} rejected")

            self._record({
                "timestamp": datetime.now().isoformat(),
                "from_zone": self.zone_id,
                "to_zone": response.sender_zone,
                "bin_count": len(original_request.bin_ids),
                "bin_ids": original_request.bin_ids,
                "status": "rejected"
            })
            # attempted_peers deliberately retains this zone, so the next
            # initiate_spillover advances to the next candidate (Algorithm 1).

        # Remove from pending
        del self.pending_spillovers[response.sender_zone]
    
    def get_spillover_statistics(self) -> Dict:
        """Get spillover statistics"""
        completed = [s for s in self.spillover_history if s["status"] == "completed"]
        rejected = [s for s in self.spillover_history if s["status"] == "rejected"]
        adopted = [s for s in self.spillover_history if s["status"] == "adopted"]

        # Success rate is over requests this zone *sent*; adoptions are inbound and
        # would otherwise inflate the denominator.
        outbound = len(completed) + len(rejected)

        return {
            "total_spillovers": len(self.spillover_history),
            "completed_spillovers": len(completed),
            "rejected_spillovers": len(rejected),
            "adopted_spillovers": len(adopted),
            "success_rate": len(completed) / outbound * 100 if outbound else 0,
            "pending_spillovers": len(self.pending_spillovers),
            "bins_transferred": sum(s["bin_count"] for s in completed),
            "bins_adopted": sum(s["bin_count"] for s in adopted),
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
