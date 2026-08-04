from typing import List, Dict, Optional
from contracts.message_types import BinTelemetry

# Priority tiers as defined in Section IV-B of the paper.
#   Critical  >= 90%
#   High      80-90%
#   Medium    60-80%
#   Low       < 60%
# Only Critical and High clear the 80% overflow threshold and are routed in the
# current cycle; Medium and Low are deferred unless spare truck capacity exists.
CRITICAL_THRESHOLD = 90.0
HIGH_THRESHOLD = 80.0
MEDIUM_THRESHOLD = 60.0

PRIORITY_ORDER = ['low', 'medium', 'high', 'critical']

# Tiers eligible for routing in the current collection cycle.
ROUTABLE_PRIORITIES = ('critical', 'high')


class BinPriorityManager:
    """Manages bin priority levels for route optimization"""

    def __init__(self):
        self.priority_weights = {
            'critical': 3.0,    # >= 90% fill
            'high': 2.0,        # 80-90% fill
            'medium': 1.5,      # 60-80% fill
            'low': 1.0          # < 60% fill
        }

    def get_bin_priority(self, bin_telemetry: BinTelemetry) -> str:
        """Determine priority level based on fill level"""
        fill_level = bin_telemetry.fill_level

        if fill_level >= CRITICAL_THRESHOLD:
            return 'critical'
        elif fill_level >= HIGH_THRESHOLD:
            return 'high'
        elif fill_level >= MEDIUM_THRESHOLD:
            return 'medium'
        else:
            return 'low'

    def get_priority_score(self, bin_telemetry: BinTelemetry) -> float:
        """
        Calculate priority score for a bin.

        Fill level breaks ties within a tier, so sorting is stable and total rather
        than leaving every bin in a tier mutually incomparable.
        """
        base_score = self.priority_weights[self.get_bin_priority(bin_telemetry)]
        return base_score * 100.0 + bin_telemetry.fill_level

    def sort_bins_by_priority(self, bins: List[BinTelemetry]) -> List[BinTelemetry]:
        """Sort bins by priority (highest first)"""
        return sorted(bins, key=self.get_priority_score, reverse=True)

    def is_routable(self, bin_telemetry: BinTelemetry) -> bool:
        """True if this bin is eligible for the current collection cycle"""
        return self.get_bin_priority(bin_telemetry) in ROUTABLE_PRIORITIES

    def get_routable_bins(self, bins: List[BinTelemetry],
                          spare_capacity: int = 0) -> List[BinTelemetry]:
        """
        Bins to service this cycle, highest priority first.

        Critical and High tiers are always routed. Medium bins are deferred unless
        `spare_capacity` slots remain, per Section IV-B; Low bins are never routed.
        """
        ordered = self.sort_bins_by_priority(bins)
        routable = [b for b in ordered if self.is_routable(b)]

        if spare_capacity > 0:
            deferred = [b for b in ordered
                        if self.get_bin_priority(b) == 'medium']
            routable.extend(deferred[:spare_capacity])

        return routable

    def get_priority_distribution(self, bins: List[BinTelemetry]) -> Dict[str, int]:
        """Get distribution of bins across all four priority tiers"""
        distribution = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}

        for bin_telemetry in bins:
            distribution[self.get_bin_priority(bin_telemetry)] += 1

        return distribution

    def filter_by_priority(self, bins: List[BinTelemetry],
                           min_priority: str = 'high') -> List[BinTelemetry]:
        """Filter bins at or above a minimum priority level"""
        min_index = PRIORITY_ORDER.index(min_priority)

        return [b for b in bins
                if PRIORITY_ORDER.index(self.get_bin_priority(b)) >= min_index]
