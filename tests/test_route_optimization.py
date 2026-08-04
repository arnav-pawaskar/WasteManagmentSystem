#!/usr/bin/env python3
"""
Test suite for Route Optimization Module
"""

import sys
import os
import unittest
from datetime import datetime

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contracts.message_types import BinTelemetry
from modules.route_optimizer import RouteOptimizer, BinPriorityManager, RouteManager

class TestRouteOptimizer(unittest.TestCase):
    
    def setUp(self):
        self.optimizer = RouteOptimizer()
        self.test_bins = [
            BinTelemetry("bin_1", 1, 10.0, 10.0, 85.0, datetime.now()),
            BinTelemetry("bin_2", 1, 20.0, 20.0, 90.0, datetime.now()),
            BinTelemetry("bin_3", 1, 15.0, 25.0, 78.0, datetime.now()),  # Not overflowing
            BinTelemetry("bin_4", 1, 30.0, 15.0, 95.0, datetime.now()),
        ]
    
    def test_distance_calculation(self):
        """Test Euclidean distance calculation"""
        bin1, bin2 = self.test_bins[0], self.test_bins[1]
        distance = self.optimizer.calculate_distance(bin1, bin2)
        expected = ((20.0-10.0)**2 + (20.0-10.0)**2)**0.5
        self.assertAlmostEqual(distance, expected, places=2)
    
    def test_compute_route_with_overflowing_bins(self):
        """Test route computation with overflowing bins"""
        route = self.optimizer.compute_route(self.test_bins, (0.0, 0.0), "truck_1", 1)
        
        # Should only include overflowing bins (bin_1, bin_2, bin_4)
        self.assertEqual(len(route.route_bins), 3)
        self.assertIn("bin_1", route.route_bins)
        self.assertIn("bin_2", route.route_bins)
        self.assertIn("bin_4", route.route_bins)
        self.assertNotIn("bin_3", route.route_bins)
        self.assertGreater(route.route_distance, 0)
    
    def test_compute_route_no_overflowing_bins(self):
        """Test route computation with no overflowing bins"""
        non_overflowing_bins = [
            BinTelemetry("bin_1", 1, 10.0, 10.0, 70.0, datetime.now()),
            BinTelemetry("bin_2", 1, 20.0, 20.0, 75.0, datetime.now()),
        ]
        
        route = self.optimizer.compute_route(non_overflowing_bins, (0.0, 0.0), "truck_1", 1)
        
        self.assertEqual(len(route.route_bins), 0)
        self.assertEqual(route.route_distance, 0.0)
    
    def test_replan_on_new_overflow(self):
        """Test route replanning when new bin overflows"""
        initial_route = self.optimizer.compute_route(self.test_bins[:2], (0.0, 0.0), "truck_1", 1)
        
        new_overflow_bin = BinTelemetry("bin_5", 1, 25.0, 30.0, 88.0, datetime.now())
        updated_route = self.optimizer.replan_on_overflow(initial_route, new_overflow_bin, self.test_bins)
        
        # Should include the new overflowing bin
        self.assertIn("bin_5", updated_route.route_bins)

class TestBinPriorityManager(unittest.TestCase):
    
    def setUp(self):
        # Tiers per Section IV-B: Critical >=90, High 80-90, Medium 60-80, Low <60
        self.priority_manager = BinPriorityManager()
        self.test_bins = [
            BinTelemetry("bin_1", 1, 10.0, 10.0, 96.0, datetime.now()),  # critical
            BinTelemetry("bin_2", 1, 20.0, 20.0, 87.0, datetime.now()),  # high
            BinTelemetry("bin_3", 1, 15.0, 25.0, 72.0, datetime.now()),  # medium
            BinTelemetry("bin_4", 1, 30.0, 15.0, 41.0, datetime.now()),  # low
        ]

    def test_priority_classification(self):
        """Test bin priority classification against the paper's tiers"""
        got = [self.priority_manager.get_bin_priority(b) for b in self.test_bins]
        self.assertEqual(got, ['critical', 'high', 'medium', 'low'])

    def test_tier_boundaries_are_inclusive_below(self):
        """A bin exactly on a boundary belongs to the higher tier"""
        cases = [(90.0, 'critical'), (89.9, 'high'), (80.0, 'high'),
                 (79.9, 'medium'), (60.0, 'medium'), (59.9, 'low')]
        for fill, expected in cases:
            b = BinTelemetry("b", 1, 0.0, 0.0, fill, datetime.now())
            self.assertEqual(self.priority_manager.get_bin_priority(b), expected,
                             f"fill_level {fill}")

    def test_priority_sorting(self):
        """Test sorting bins by priority"""
        sorted_bins = self.priority_manager.sort_bins_by_priority(self.test_bins)

        self.assertEqual(
            [self.priority_manager.get_bin_priority(b) for b in sorted_bins],
            ['critical', 'high', 'medium', 'low'])

    def test_sorting_breaks_ties_by_fill_level(self):
        """Within a tier, fuller bins sort first"""
        bins = [
            BinTelemetry("a", 1, 0.0, 0.0, 82.0, datetime.now()),
            BinTelemetry("b", 1, 0.0, 0.0, 88.0, datetime.now()),
            BinTelemetry("c", 1, 0.0, 0.0, 85.0, datetime.now()),
        ]
        order = [b.bin_id for b in self.priority_manager.sort_bins_by_priority(bins)]
        self.assertEqual(order, ["b", "c", "a"])

    def test_only_critical_and_high_are_routable(self):
        """Section IV-B: Medium and Low are deferred"""
        routable = self.priority_manager.get_routable_bins(self.test_bins)
        self.assertEqual([b.bin_id for b in routable], ["bin_1", "bin_2"])

    def test_spare_capacity_promotes_medium_but_never_low(self):
        routable = self.priority_manager.get_routable_bins(self.test_bins,
                                                           spare_capacity=5)
        self.assertEqual([b.bin_id for b in routable], ["bin_1", "bin_2", "bin_3"])

    def test_priority_distribution(self):
        """Distribution spans all four tiers"""
        distribution = self.priority_manager.get_priority_distribution(self.test_bins)

        self.assertEqual(distribution['critical'], 1)
        self.assertEqual(distribution['high'], 1)
        self.assertEqual(distribution['medium'], 1)
        self.assertEqual(distribution['low'], 1)

class TestRouteManager(unittest.TestCase):
    
    def setUp(self):
        self.route_manager = RouteManager(zone_id=1, truck_count=2)
        self.test_bins = [
            BinTelemetry("bin_1", 1, 10.0, 10.0, 85.0, datetime.now()),
            BinTelemetry("bin_2", 1, 20.0, 20.0, 90.0, datetime.now()),
            BinTelemetry("bin_3", 1, 15.0, 25.0, 95.0, datetime.now()),
            BinTelemetry("bin_4", 1, 30.0, 15.0, 88.0, datetime.now()),
        ]
    
    def test_update_overflowing_bins(self):
        """Test updating overflowing bins list"""
        self.route_manager.update_overflowing_bins(self.test_bins)
        
        # All bins are overflowing
        self.assertEqual(len(self.route_manager.overflowing_bins), 4)
    
    def test_plan_routes(self):
        """Test route planning"""
        self.route_manager.update_overflowing_bins(self.test_bins)
        routes = self.route_manager.plan_routes(self.test_bins)
        
        # Should create routes for both trucks
        self.assertEqual(len(routes), 2)
        self.assertTrue(all(route.zone_id == 1 for route in routes))
    
    def test_zone_status(self):
        """Test zone status reporting"""
        self.route_manager.update_overflowing_bins(self.test_bins)
        status = self.route_manager.get_zone_status()
        
        self.assertEqual(status['zone_id'], 1)
        self.assertEqual(status['total_overflowing_bins'], 4)
        self.assertEqual(status['truck_count'], 2)

if __name__ == '__main__':
    unittest.main()
