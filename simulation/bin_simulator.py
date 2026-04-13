import random
import time
import threading
from datetime import datetime
from typing import List, Dict, Callable
from contracts.message_types import BinTelemetry

class BinSimulator:
    """Simulates smart bins with stochastic fill level growth"""
    
    def __init__(self, zones: int = 3, bins_per_zone: int = 15, update_interval: int = 5):
        self.zones = zones
        self.bins_per_zone = bins_per_zone
        self.update_interval = update_interval
        self.bins: Dict[str, BinTelemetry] = {}
        self.running = False
        self.telemetry_callbacks: List[Callable[[BinTelemetry], None]] = []
        self.overflowing_bin_ids: set = set()
        
        # Initialize bins
        self._initialize_bins()
    
    def _initialize_bins(self):
        """Create bins with random positions"""
        for zone_id in range(1, self.zones + 1):
            for bin_num in range(1, self.bins_per_zone + 1):
                bin_id = f"bin_{zone_id}_{bin_num}"
                
                # Random position within zone (simplified grid layout)
                x = (zone_id - 1) * 100 + random.uniform(0, 80)
                y = random.uniform(0, 80)
                
                # Initial fill level (0-30%)
                fill_level = random.uniform(0, 30)
                
                bin_telemetry = BinTelemetry(
                    bin_id=bin_id,
                    zone_id=zone_id,
                    x=x,
                    y=y,
                    fill_level=fill_level,
                    timestamp=datetime.now()
                )
                
                self.bins[bin_id] = bin_telemetry
    
    def add_telemetry_callback(self, callback: Callable[[BinTelemetry], None]):
        """Add callback to receive telemetry updates"""
        self.telemetry_callbacks.append(callback)
    
    def _notify_telemetry(self, telemetry: BinTelemetry):
        """Notify all registered callbacks with new telemetry"""
        for callback in self.telemetry_callbacks:
            try:
                callback(telemetry)
            except Exception as e:
                print(f"Error in telemetry callback: {e}")
    
    def update_fill_levels(self):
        """Update fill levels for all bins using stochastic model"""
        overflow_threshold = 80.0
        
        for bin_id, bin_telemetry in self.bins.items():
            was_overflowing = bin_id in self.overflowing_bin_ids
            
            # Stochastic fill level growth: random(1, 5)
            fill_increase = random.uniform(1, 5)
            bin_telemetry.fill_level = min(100.0, bin_telemetry.fill_level + fill_increase)
            bin_telemetry.timestamp = datetime.now()
            
            # Only notify on first overflow crossing
            if bin_telemetry.is_overflowing(overflow_threshold) and not was_overflowing:
                self.overflowing_bin_ids.add(bin_id)
                print(f"ALERT: {bin_id} overflow detected! Fill level: {bin_telemetry.fill_level:.1f}%")
                self._notify_telemetry(bin_telemetry)
    
    def get_bin(self, bin_id: str) -> BinTelemetry:
        """Get specific bin telemetry"""
        return self.bins.get(bin_id)
    
    def get_bins_by_zone(self, zone_id: int) -> List[BinTelemetry]:
        """Get all bins in a specific zone"""
        return [bin_telemetry for bin_telemetry in self.bins.values() 
                if bin_telemetry.zone_id == zone_id]
    
    def get_overflowing_bins(self, zone_id: int = None, threshold: float = 80.0) -> List[BinTelemetry]:
        """Get all overflowing bins, optionally filtered by zone"""
        bins = self.bins.values()
        if zone_id:
            bins = [bin_telemetry for bin_telemetry in bins 
                   if bin_telemetry.zone_id == zone_id]
        
        return [bin_telemetry for bin_telemetry in bins 
                if bin_telemetry.is_overflowing(threshold)]
    
    def empty_bin(self, bin_id: str):
        """Empty a bin (reset fill level to 0)"""
        if bin_id in self.bins:
            self.bins[bin_id].fill_level = 0.0
            self.bins[bin_id].timestamp = datetime.now()
            self.overflowing_bin_ids.discard(bin_id)
            print(f"Bin {bin_id} emptied")
    
    def start_simulation(self):
        """Start the continuous simulation"""
        if self.running:
            print("Simulation already running")
            return
        
        self.running = True
        print(f"Starting bin simulation with {self.zones} zones, {self.bins_per_zone} bins per zone")
        print(f"Update interval: {self.update_interval} seconds")
        
        def simulation_loop():
            while self.running:
                self.update_fill_levels()
                time.sleep(self.update_interval)
        
        self.simulation_thread = threading.Thread(target=simulation_loop, daemon=True)
        self.simulation_thread.start()
    
    def stop_simulation(self):
        """Stop the simulation"""
        self.running = False
        print("Bin simulation stopped")
    
    def get_statistics(self) -> Dict:
        """Get current simulation statistics"""
        total_bins = len(self.bins)
        overflowing_bins = len(self.get_overflowing_bins())
        avg_fill_level = sum(bin.fill_level for bin in self.bins.values()) / total_bins
        
        zone_stats = {}
        for zone_id in range(1, self.zones + 1):
            zone_bins = self.get_bins_by_zone(zone_id)
            zone_overflowing = len([bin for bin in zone_bins if bin.is_overflowing()])
            zone_avg_fill = sum(bin.fill_level for bin in zone_bins) / len(zone_bins)
            
            zone_stats[f"zone_{zone_id}"] = {
                "total_bins": len(zone_bins),
                "overflowing_bins": zone_overflowing,
                "avg_fill_level": zone_avg_fill
            }
        
        return {
            "total_bins": total_bins,
            "overflowing_bins": overflowing_bins,
            "avg_fill_level": avg_fill_level,
            "zone_stats": zone_stats
        }
