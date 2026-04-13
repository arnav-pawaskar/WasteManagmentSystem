import math
from typing import List, Tuple, Optional
from contracts.message_types import BinTelemetry, RoutePlan

class RouteOptimizer:
    """Computes optimal garbage truck routes using Nearest Neighbour algorithm"""
    
    def __init__(self):
        self.overflow_threshold = 80.0
    
    def calculate_distance(self, bin1: BinTelemetry, bin2: BinTelemetry) -> float:
        """Calculate Euclidean distance between two bins"""
        return math.sqrt((bin1.x - bin2.x)**2 + (bin1.y - bin2.y)**2)
    
    def calculate_distance_to_point(self, bin_telemetry: BinTelemetry, x: float, y: float) -> float:
        """Calculate Euclidean distance from bin to a specific point"""
        return math.sqrt((bin_telemetry.x - x)**2 + (bin_telemetry.y - y)**2)
    
    def find_nearest_unvisited_bin(self, current_position: Tuple[float, float], 
                                  bins: List[BinTelemetry], 
                                  visited_bins: set) -> Optional[BinTelemetry]:
        """Find the nearest unvisited bin from current position"""
        nearest_bin = None
        min_distance = float('inf')
        
        for bin_telemetry in bins:
            if bin_telemetry.bin_id not in visited_bins:
                distance = self.calculate_distance_to_point(bin_telemetry, 
                                                          current_position[0], 
                                                          current_position[1])
                if distance < min_distance:
                    min_distance = distance
                    nearest_bin = bin_telemetry
        
        return nearest_bin
    
    def compute_route(self, bins: List[BinTelemetry], 
                     truck_position: Tuple[float, float] = (0.0, 0.0),
                     truck_id: str = "truck_1",
                     zone_id: int = 1) -> RoutePlan:
        """
        Compute optimal route using Nearest Neighbour algorithm
        
        Args:
            bins: List of bins to visit
            truck_position: Starting position of the truck (x, y)
            truck_id: ID of the truck
            zone_id: Zone ID for the route
            
        Returns:
            RoutePlan with optimized route
        """
        if not bins:
            return RoutePlan(
                truck_id=truck_id,
                zone_id=zone_id,
                route_bins=[],
                route_distance=0.0
            )
        
        # Filter for overflowing bins
        overflowing_bins = [bin_telemetry for bin_telemetry in bins 
                           if bin_telemetry.is_overflowing(self.overflow_threshold)]
        
        if not overflowing_bins:
            return RoutePlan(
                truck_id=truck_id,
                zone_id=zone_id,
                route_bins=[],
                route_distance=0.0
            )
        
        # Nearest Neighbour algorithm
        route_bins = []
        visited_bins = set()
        current_position = truck_position
        total_distance = 0.0
        
        while len(visited_bins) < len(overflowing_bins):
            nearest_bin = self.find_nearest_unvisited_bin(current_position, 
                                                         overflowing_bins, 
                                                         visited_bins)
            
            if nearest_bin is None:
                break
            
            # Add distance to this bin
            distance_to_bin = self.calculate_distance_to_point(nearest_bin, 
                                                               current_position[0], 
                                                               current_position[1])
            total_distance += distance_to_bin
            
            # Add bin to route
            route_bins.append(nearest_bin.bin_id)
            visited_bins.add(nearest_bin.bin_id)
            current_position = (nearest_bin.x, nearest_bin.y)
        
        return RoutePlan(
            truck_id=truck_id,
            zone_id=zone_id,
            route_bins=route_bins,
            route_distance=total_distance
        )
    
    def replan_on_overflow(self, current_route: RoutePlan, 
                          new_overflowing_bin: BinTelemetry,
                          all_bins: List[BinTelemetry],
                          truck_position: Tuple[float, float] = (0.0, 0.0)) -> RoutePlan:
        """
        Replan route when a new bin overflows
        
        Args:
            current_route: Current route plan
            new_overflowing_bin: New bin that needs pickup
            all_bins: All available bins in the zone
            truck_position: Current truck position
            
        Returns:
            Updated RoutePlan
        """
        # Get all overflowing bins including the new one
        overflowing_bins = [bin_telemetry for bin_telemetry in all_bins 
                           if bin_telemetry.is_overflowing(self.overflow_threshold)]
        
        # If the new bin is already in the list, just return current route
        if new_overflowing_bin.bin_id in current_route.route_bins:
            return current_route
        
        # Recompute the entire route with all overflowing bins
        return self.compute_route(overflowing_bins, truck_position, 
                                current_route.truck_id, current_route.zone_id)
    
    def get_route_statistics(self, route_plan: RoutePlan) -> dict:
        """Get statistics about the computed route"""
        return {
            "truck_id": route_plan.truck_id,
            "zone_id": route_plan.zone_id,
            "total_bins": len(route_plan.route_bins),
            "total_distance": route_plan.route_distance,
            "average_distance_per_bin": route_plan.route_distance / len(route_plan.route_bins) if route_plan.route_bins else 0
        }
    
    def validate_route(self, route_plan: RoutePlan, bins: List[BinTelemetry]) -> bool:
        """Validate that all bins in route exist and are overflowing"""
        bin_dict = {bin_telemetry.bin_id: bin_telemetry for bin_telemetry in bins}
        
        for bin_id in route_plan.route_bins:
            if bin_id not in bin_dict:
                print(f"Validation Error: Bin {bin_id} not found")
                return False
            
            if not bin_dict[bin_id].is_overflowing(self.overflow_threshold):
                print(f"Validation Error: Bin {bin_id} is not overflowing")
                return False
        
        return True
