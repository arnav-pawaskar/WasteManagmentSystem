from typing import List, Dict, Optional
from datetime import datetime
from contracts.message_types import BinTelemetry, RoutePlan
from .routing import RouteOptimizer
from .priority import BinPriorityManager

class RouteManager:
    """Manages route planning and execution for a fog node"""
    
    def __init__(self, zone_id: int, truck_count: int = 1):
        self.zone_id = zone_id
        self.truck_count = truck_count
        self.route_optimizer = RouteOptimizer()
        self.priority_manager = BinPriorityManager()
        
        # Route management
        self.active_routes: Dict[str, RoutePlan] = {}
        self.route_history: List[RoutePlan] = []
        self.overflowing_bins: List[BinTelemetry] = []
        
        # Truck positions (simplified - in real system would track actual positions)
        self.truck_positions: Dict[str, tuple] = {}
        for i in range(truck_count):
            truck_id = f"truck_{zone_id}_{i+1}"
            self.truck_positions[truck_id] = (50.0, 50.0)  # Default center position
    
    def update_overflowing_bins(self, bins: List[BinTelemetry]):
        """Update the list of overflowing bins"""
        self.overflowing_bins = [bin_telemetry for bin_telemetry in bins 
                                if bin_telemetry.is_overflowing()]
        
        # Sort by priority
        self.overflowing_bins = self.priority_manager.sort_bins_by_priority(
            self.overflowing_bins)
    
    def plan_routes(self, all_bins: List[BinTelemetry]) -> List[RoutePlan]:
        """Plan routes for all trucks in the zone"""
        self.update_overflowing_bins(all_bins)
        
        if not self.overflowing_bins:
            print(f"Zone {self.zone_id}: No overflowing bins to service")
            return []
        
        # Simple assignment: divide bins among trucks
        routes = []
        bins_per_truck = len(self.overflowing_bins) // self.truck_count
        
        for i, truck_id in enumerate(self.truck_positions.keys()):
            start_idx = i * bins_per_truck
            end_idx = start_idx + bins_per_truck if i < self.truck_count - 1 else len(self.overflowing_bins)
            
            truck_bins = self.overflowing_bins[start_idx:end_idx]
            
            if truck_bins:
                route_plan = self.route_optimizer.compute_route(
                    truck_bins, 
                    self.truck_positions[truck_id],
                    truck_id,
                    self.zone_id
                )
                
                routes.append(route_plan)
                self.active_routes[truck_id] = route_plan
        
        print(f"Zone {self.zone_id}: Generated {len(routes)} routes for {len(self.overflowing_bins)} overflowing bins")
        return routes
    
    def replan_route_on_new_overflow(self, new_bin: BinTelemetry, all_bins: List[BinTelemetry]):
        """Replan routes when a new bin starts overflowing"""
        if new_bin.zone_id != self.zone_id:
            return
        
        print(f"Zone {self.zone_id}: New overflow detected for {new_bin.bin_id}, replanning routes...")
        
        # Add new bin to overflowing list
        if new_bin not in self.overflowing_bins:
            self.overflowing_bins.append(new_bin)
            self.overflowing_bins = self.priority_manager.sort_bins_by_priority(
                self.overflowing_bins)
        
        # Replan all routes
        self.plan_routes(all_bins)
    
    def complete_route(self, truck_id: str):
        """Mark a route as completed and move to history"""
        if truck_id in self.active_routes:
            completed_route = self.active_routes[truck_id]
            self.route_history.append(completed_route)
            del self.active_routes[truck_id]
            
            # Update truck position to last bin in route (simplified)
            if completed_route.route_bins:
                # In real implementation, would track actual position
                pass
            
            print(f"Zone {self.zone_id}: Route completed for {truck_id}")
    
    def get_zone_status(self) -> Dict:
        """Get current zone routing status"""
        priority_dist = self.priority_manager.get_priority_distribution(
            self.overflowing_bins)
        
        return {
            "zone_id": self.zone_id,
            "total_overflowing_bins": len(self.overflowing_bins),
            "active_routes": len(self.active_routes),
            "completed_routes": len(self.route_history),
            "priority_distribution": priority_dist,
            "truck_count": self.truck_count
        }
    
    def get_route_details(self, truck_id: str) -> Optional[RoutePlan]:
        """Get details of a specific route"""
        return self.active_routes.get(truck_id)
    
    def empty_bins_in_route(self, truck_id: str):
        """Mark all bins in a route as emptied"""
        if truck_id in self.active_routes:
            route = self.active_routes[truck_id]
            print(f"Zone {self.zone_id}: Emptying {len(route.route_bins)} bins for {truck_id}")
            
            # Remove emptied bins from overflowing list
            bin_ids_to_remove = set(route.route_bins)
            self.overflowing_bins = [bin_telemetry for bin_telemetry in self.overflowing_bins 
                                   if bin_telemetry.bin_id not in bin_ids_to_remove]
            
            self.complete_route(truck_id)
    
    def get_statistics(self) -> Dict:
        """Get routing statistics"""
        total_distance = sum(route.route_distance for route in self.active_routes.values())
        total_bins_serviced = sum(len(route.route_bins) for route in self.route_history)
        
        return {
            "zone_id": self.zone_id,
            "current_active_routes": len(self.active_routes),
            "total_distance_today": total_distance,
            "total_bins_serviced": total_bins_serviced,
            "overflowing_bins_pending": len(self.overflowing_bins),
            "efficiency_score": self._calculate_efficiency_score()
        }
    
    def _calculate_efficiency_score(self) -> float:
        """Calculate routing efficiency score (simplified)"""
        if not self.route_history:
            return 100.0
        
        # Efficiency based on average distance per bin
        total_distance = sum(route.route_distance for route in self.route_history)
        total_bins = sum(len(route.route_bins) for route in self.route_history)
        
        if total_bins == 0:
            return 100.0
        
        avg_distance_per_bin = total_distance / total_bins
        # Lower average distance is better (normalized to 0-100)
        efficiency = max(0, 100 - (avg_distance_per_bin / 2))  # Assuming 200 units as max reasonable distance
        
        return round(efficiency, 2)
