"""Shared core: mirrors the notebook's self-contained re-implementation."""
import math, random, time, os, gc, platform, itertools
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional

@dataclass
class BinTelemetry:
    bin_id: str
    zone_id: int
    x: float
    y: float
    fill_level: float
    timestamp: float
    def is_overflowing(self, threshold: float = 80.0) -> bool:
        return self.fill_level >= threshold

@dataclass
class RoutePlan:
    truck_id: str
    zone_id: int
    route_bins: List[str]
    route_distance: float


def _d(x1, y1, x2, y2):
    return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)


def path_length(start, pts):
    """Open-path length from start through pts in order."""
    tot = 0.0
    cur = start
    for p in pts:
        tot += _d(cur[0], cur[1], p[0], p[1])
        cur = p
    return tot


class RouteOptimizer:
    def __init__(self, overflow_threshold: float = 80.0):
        self.overflow_threshold = overflow_threshold

    @staticmethod
    def _dist(x1, y1, x2, y2) -> float:
        return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)

    def overflowing(self, bins):
        return [b for b in bins if b.is_overflowing(self.overflow_threshold)]

    def nearest_neighbour_route(self, bins, start=(50.0, 50.0), truck_id="truck_1", zone_id=1):
        overflowing = [b for b in bins if b.is_overflowing(self.overflow_threshold)]
        if not overflowing:
            return RoutePlan(truck_id, zone_id, [], 0.0)
        remaining = overflowing[:]
        route, total = [], 0.0
        cur = start
        while remaining:
            nearest = min(remaining, key=lambda b: self._dist(cur[0], cur[1], b.x, b.y))
            total += self._dist(cur[0], cur[1], nearest.x, nearest.y)
            route.append(nearest.bin_id)
            cur = (nearest.x, nearest.y)
            remaining.remove(nearest)
        return RoutePlan(truck_id, zone_id, route, total)

    def sequential_route(self, bins, start=(50.0, 50.0), truck_id="truck_1", zone_id=1):
        overflowing = [b for b in bins if b.is_overflowing(self.overflow_threshold)]
        if not overflowing:
            return RoutePlan(truck_id, zone_id, [], 0.0)
        route, total = [], 0.0
        cur = start
        for b in overflowing:
            total += self._dist(cur[0], cur[1], b.x, b.y)
            route.append(b.bin_id)
            cur = (b.x, b.y)
        return RoutePlan(truck_id, zone_id, route, total)


class BinSimulator:
    def __init__(self, zones: int, bins_per_zone: int, seed: Optional[int] = None):
        self.zones = zones
        self.bins_per_zone = bins_per_zone
        self.rng = random.Random(seed)
        self.bins: List[BinTelemetry] = self._create_bins()

    def _create_bins(self):
        bins = []
        for z in range(1, self.zones + 1):
            for i in range(self.bins_per_zone):
                bins.append(BinTelemetry(
                    bin_id=f"bin_{z}_{i+1}", zone_id=z,
                    x=self.rng.uniform(0, 100), y=self.rng.uniform(0, 100),
                    fill_level=self.rng.uniform(10, 60), timestamp=0.0))
        return bins

    def step(self, t: int, burst_prob: float = 0.08, hot_zone: Optional[int] = None,
             hot_multiplier: float = 1.0):
        for b in self.bins:
            mult = hot_multiplier if (hot_zone is not None and b.zone_id == hot_zone) else 1.0
            inc = self.rng.uniform(1, 5) * mult
            if self.rng.random() < burst_prob:
                inc += self.rng.uniform(10, 20) * mult
            b.fill_level = min(100.0, b.fill_level + inc)
            b.timestamp = t

    def bins_by_zone(self, zone_id: int):
        return [b for b in self.bins if b.zone_id == zone_id]


def env_info():
    import numpy as np
    return {
        "cpu": platform.processor() or "unknown",
        "machine": platform.machine(),
        "system": f"{platform.system()} {platform.release()}",
        "python": platform.python_version(),
        "numpy": np.__version__,
    }
