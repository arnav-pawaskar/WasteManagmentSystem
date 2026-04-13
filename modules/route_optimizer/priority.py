from typing import List, Dict
from contracts.message_types import BinTelemetry

class BinPriorityManager:
    """Manages bin priority levels for route optimization"""
    
    def __init__(self):
        self.priority_weights = {
            'critical': 3.0,    # > 95% fill
            'high': 2.0,        # 85-95% fill
            'medium': 1.5,      # 80-85% fill
            'low': 1.0          # 75-80% fill (if included)
        }
    
    def get_bin_priority(self, bin_telemetry: BinTelemetry) -> str:
        """Determine priority level based on fill level"""
        fill_level = bin_telemetry.fill_level
        
        if fill_level >= 95.0:
            return 'critical'
        elif fill_level >= 85.0:
            return 'high'
        elif fill_level >= 80.0:
            return 'medium'
        else:
            return 'low'
    
    def get_priority_score(self, bin_telemetry: BinTelemetry) -> float:
        """Calculate priority score for a bin"""
        priority = self.get_bin_priority(bin_telemetry)
        base_score = self.priority_weights[priority]
        
        # Add time-based urgency (bins overflowing longer get higher priority)
        # This is a simplified version - in real implementation, track overflow duration
        time_factor = 1.0  # Could be based on how long bin has been overflowing
        
        return base_score * time_factor
    
    def sort_bins_by_priority(self, bins: List[BinTelemetry]) -> List[BinTelemetry]:
        """Sort bins by priority (highest first)"""
        return sorted(bins, key=self.get_priority_score, reverse=True)
    
    def get_priority_distribution(self, bins: List[BinTelemetry]) -> Dict[str, int]:
        """Get distribution of bins by priority level"""
        distribution = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}
        
        for bin_telemetry in bins:
            if bin_telemetry.fill_level >= 80.0:  # Only count overflowing bins
                priority = self.get_bin_priority(bin_telemetry)
                distribution[priority] += 1
        
        return distribution
    
    def filter_by_priority(self, bins: List[BinTelemetry], 
                          min_priority: str = 'medium') -> List[BinTelemetry]:
        """Filter bins by minimum priority level"""
        priority_order = ['low', 'medium', 'high', 'critical']
        min_index = priority_order.index(min_priority)
        
        filtered_bins = []
        for bin_telemetry in bins:
            if bin_telemetry.fill_level >= 80.0:  # Only consider overflowing bins
                priority = self.get_bin_priority(bin_telemetry)
                if priority_order.index(priority) >= min_index:
                    filtered_bins.append(bin_telemetry)
        
        return filtered_bins
