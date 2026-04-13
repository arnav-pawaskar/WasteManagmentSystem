#!/usr/bin/env python3
"""
Test suite for Inter-Fog Communication Module
"""

import sys
import os
import unittest
from datetime import datetime

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contracts.message_types import ZoneState, SpilloverRequest, SpilloverResponse, BinTelemetry
from modules.inter_fog_comm import PeerDiscovery, GossipProtocol, SpilloverManager, InterFogCommunicator

class TestPeerDiscovery(unittest.TestCase):
    
    def setUp(self):
        self.peer_discovery = PeerDiscovery(zone_id=1)
        self.test_zone_state = ZoneState(zone_id=2, active_bins=5, truck_count=1, timestamp=datetime.now())
    
    def test_register_peer(self):
        """Test peer registration"""
        self.peer_discovery.register_peer(self.test_zone_state)
        
        self.assertEqual(len(self.peer_discovery.peer_registry), 1)
        self.assertIn(2, self.peer_discovery.peer_registry)
        self.assertEqual(self.peer_discovery.peer_registry[2].zone_id, 2)
    
    def test_discover_peers(self):
        """Test peer discovery"""
        self.peer_discovery.register_peer(self.test_zone_state)
        peers = self.peer_discovery.discover_peers()
        
        self.assertEqual(len(peers), 1)
        self.assertEqual(peers[0].zone_id, 2)
    
    def test_create_zone_state(self):
        """Test zone state creation"""
        zone_state = self.peer_discovery.create_zone_state(8, 2)
        
        self.assertEqual(zone_state.zone_id, 1)
        self.assertEqual(zone_state.active_bins, 8)
        self.assertEqual(zone_state.truck_count, 2)

class TestGossipProtocol(unittest.TestCase):
    
    def setUp(self):
        self.gossip_protocol = GossipProtocol(zone_id=1)
        self.test_state = ZoneState(2, 5, 1, datetime.now())
    
    def test_update_local_state(self):
        """Test local state update"""
        local_state = ZoneState(1, 10, 2, datetime.now())
        self.gossip_protocol.update_local_state(local_state)
        
        self.assertEqual(self.gossip_protocol.current_state.zone_id, 1)
        self.assertEqual(self.gossip_protocol.current_state.active_bins, 10)
    
    def test_receive_gossip(self):
        """Test gossip message reception"""
        self.gossip_protocol.receive_gossip(2, self.test_state, "msg_123")
        
        self.assertIn(2, self.gossip_protocol.peer_states)
        self.assertEqual(self.gossip_protocol.peer_states[2].active_bins, 5)
    
    def test_find_least_loaded_zone(self):
        """Test finding least loaded zone"""
        # Add multiple peers
        state1 = ZoneState(2, 8, 1, datetime.now())
        state2 = ZoneState(3, 3, 1, datetime.now())
        state3 = ZoneState(4, 12, 1, datetime.now())
        
        self.gossip_protocol.receive_gossip(2, state1)
        self.gossip_protocol.receive_gossip(3, state2)
        self.gossip_protocol.receive_gossip(4, state3)
        
        least_loaded = self.gossip_protocol.find_least_loaded_zone()
        self.assertEqual(least_loaded, 3)  # Zone 3 has 3 active bins

class TestSpilloverManager(unittest.TestCase):
    
    def setUp(self):
        self.spillover_manager = SpilloverManager(zone_id=1, overload_threshold=5)
        self.current_state = ZoneState(1, 8, 1, datetime.now())
        self.overflowing_bins = [
            BinTelemetry("bin_1", 1, 10.0, 10.0, 85.0, datetime.now()),
            BinTelemetry("bin_2", 1, 20.0, 20.0, 90.0, datetime.now()),
            BinTelemetry("bin_3", 1, 15.0, 25.0, 95.0, datetime.now()),
        ]
        self.peer_zones = {
            2: ZoneState(2, 2, 1, datetime.now()),
            3: ZoneState(3, 4, 1, datetime.now()),
        }
    
    def test_check_overload(self):
        """Test overload detection"""
        self.assertTrue(self.spillover_manager.check_overload(self.current_state))
        
        normal_state = ZoneState(1, 3, 1, datetime.now())
        self.assertFalse(self.spillover_manager.check_overload(normal_state))
    
    def test_initiate_spillover(self):
        """Test spillover initiation"""
        request = self.spillover_manager.initiate_spillover(
            self.current_state, self.overflowing_bins, self.peer_zones
        )
        
        self.assertIsNotNone(request)
        self.assertEqual(request.sender_zone, 1)
        self.assertEqual(request.receiver_zone, 2)  # Least loaded
        self.assertGreater(len(request.bin_ids), 0)
    
    def test_receive_spillover_request(self):
        """Test spillover request handling"""
        request = SpilloverRequest(
            sender_zone=2,
            receiver_zone=1,
            bin_ids=["bin_1", "bin_2"],
            timestamp=datetime.now()
        )
        
        response = self.spillover_manager.receive_spillover_request(request, self.current_state)
        
        self.assertEqual(response.sender_zone, 1)
        self.assertEqual(response.receiver_zone, 2)
        self.assertFalse(response.accepted)  # Zone 1 is overloaded
    
    def test_spillover_statistics(self):
        """Test spillover statistics"""
        # Add some spillover history
        self.spillover_manager.spillover_history = [
            {
                "timestamp": datetime.now().isoformat(),
                "from_zone": 1,
                "to_zone": 2,
                "bin_count": 2,
                "bin_ids": ["bin_1", "bin_2"],
                "status": "completed"
            },
            {
                "timestamp": datetime.now().isoformat(),
                "from_zone": 1,
                "to_zone": 3,
                "bin_count": 1,
                "bin_ids": ["bin_3"],
                "status": "rejected"
            }
        ]
        
        stats = self.spillover_manager.get_spillover_statistics()
        
        self.assertEqual(stats["total_spillovers"], 2)
        self.assertEqual(stats["completed_spillovers"], 1)
        self.assertEqual(stats["rejected_spillovers"], 1)
        self.assertEqual(stats["success_rate"], 50.0)

class TestInterFogCommunicator(unittest.TestCase):
    
    def setUp(self):
        self.communicator = InterFogCommunicator(zone_id=1, overload_threshold=5)
    
    def test_update_state(self):
        """Test state update"""
        self.communicator.update_state(8, 2)
        
        self.assertEqual(self.communicator.current_state.zone_id, 1)
        self.assertEqual(self.communicator.current_state.active_bins, 8)
        self.assertEqual(self.communicator.current_state.truck_count, 2)
    
    def test_get_communication_status(self):
        """Test communication status reporting"""
        self.communicator.update_state(5, 1)
        status = self.communicator.get_communication_status()
        
        self.assertEqual(status["zone_id"], 1)
        self.assertIn("peer_discovery", status)
        self.assertIn("gossip_protocol", status)
        self.assertIn("spillover_manager", status)
        self.assertIn("message_router", status)
        self.assertIn("current_state", status)

if __name__ == '__main__':
    unittest.main()
