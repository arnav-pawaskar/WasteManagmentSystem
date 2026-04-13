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
        self.priority_manager = BinPriorityManager()
        self.test_bins = [
            BinTelemetry("bin_1", 1, 10.0, 10.0, 96.0, datetime.now()),  # critical
            BinTelemetry("bin_2", 1, 20.0, 20.0, 87.0, datetime.now()),  # high
            BinTelemetry("bin_3", 1, 15.0, 25.0, 82.0, datetime.now()),  # medium
            BinTelemetry("bin_4", 1, 30.0, 15.0, 77.0, datetime.now()),  # low (not overflowing)
        ]
    
    def test_priority_classification(self):
        """Test bin priority classification"""
        critical = self.priority_manager.get_bin_priority(self.test_bins[0])
        high = self.priority_manager.get_bin_priority(self.test_bins[1])
        medium = self.priority_manager.get_bin_priority(self.test_bins[2])
        
        self.assertEqual(critical, 'critical')
        self.assertEqual(high, 'high')
        self.assertEqual(medium, 'medium')
    
    def test_priority_sorting(self):
        """Test sorting bins by priority"""
        sorted_bins = self.priority_manager.sort_bins_by_priority(self.test_bins)
        
        # Should be in order: critical, high, medium
        self.assertEqual(self.priority_manager.get_bin_priority(sorted_bins[0]), 'critical')
        self.assertEqual(self.priority_manager.get_bin_priority(sorted_bins[1]), 'high')
        self.assertEqual(self.priority_manager.get_bin_priority(sorted_bins[2]), 'medium')
    
    def test_priority_distribution(self):
        """Test priority distribution calculation"""
        distribution = self.priority_manager.get_priority_distribution(self.test_bins)
        
        self.assertEqual(distribution['critical'], 1)
        self.assertEqual(distribution['high'], 1)
        self.assertEqual(distribution['medium'], 1)
        self.assertEqual(distribution['low'], 0)  # bin_4 is not overflowing

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
