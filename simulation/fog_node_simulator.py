import threading
import time
from typing import List, Dict, Optional, Callable
from datetime import datetime
from contracts.message_types import BinTelemetry, ZoneState, RoutePlan
from modules.route_optimizer import RouteManager
from modules.inter_fog_comm import InterFogCommunicator
from modules.election_module import InvitationElection, LeaderManager, NodeState

class FogNode:
    """Simulates a single fog node with all three modules"""
    
    def __init__(self, zone_id: int, truck_count: int = 1, 
                 overload_threshold: int = 10,
                 bin_simulator = None):
        self.zone_id = zone_id
        self.truck_count = truck_count
        self.overload_threshold = overload_threshold
        self.bin_simulator = bin_simulator
        
        # Initialize modules
        self.route_manager = RouteManager(zone_id, truck_count)
        self.communicator = InterFogCommunicator(zone_id, overload_threshold)
        self.election: InvitationElection = None  # Set by FogNodeSimulator
        
        # Node state
        self.is_leader = False
        self.is_running = False
        self.zone_bins: List[BinTelemetry] = []
        
        # Statistics tracking
        self.routes_completed = 0
        self.bins_serviced = 0
        self.spillovers_handled = 0
        
        # Setup callbacks
        self._setup_callbacks()
    
    def _setup_callbacks(self):
        """Setup callbacks between modules"""
        # Route manager callbacks
        self.route_manager.overflow_callbacks = []
        
        # Communication callbacks
        self.communicator.spillover_manager.add_spillover_completed_callback(
            self._handle_spillover_completed
        )
    
    def _handle_spillover_completed(self, target_zone: int, bin_ids: List[str]):
        """Handle completed spillover"""
        self.spillovers_handled += len(bin_ids)
        print(f"Zone {self.zone_id}: Spillover completed - {len(bin_ids)} bins transferred to Zone {target_zone}")
    
    def initialize_bins(self, bins: List[BinTelemetry]):
        """Initialize bins for this zone"""
        self.zone_bins = [bin_telemetry for bin_telemetry in bins 
                         if bin_telemetry.zone_id == self.zone_id]
        print(f"Zone {self.zone_id}: Initialized with {len(self.zone_bins)} bins")
    
    def handle_bin_overflow(self, bin_telemetry: BinTelemetry):
        """Handle bin overflow event"""
        if bin_telemetry.zone_id != self.zone_id:
            return
        
        print(f"Zone {self.zone_id}: Handling overflow for {bin_telemetry.bin_id}")
        
        # Update route manager
        self.route_manager.replan_route_on_new_overflow(bin_telemetry, self.zone_bins)
        
        # Update communication state
        overflowing_bins = self.route_manager.overflowing_bins
        self.communicator.update_state(
            len(overflowing_bins),
            self.truck_count,
            overflowing_bins
        )
    
    def plan_routes(self) -> List[RoutePlan]:
        """Plan routes for current overflowing bins"""
        routes = self.route_manager.plan_routes(self.zone_bins)
        
        if routes:
            print(f"Zone {self.zone_id}: Generated {len(routes)} routes")
            for route in routes:
                print(f"  Truck {route.truck_id}: {len(route.route_bins)} bins, {route.route_distance:.1f} units")
        
        return routes
    
    def execute_route(self, truck_id: str):
        """Execute a route (simplified simulation)"""
        route = self.route_manager.get_route_details(truck_id)
        if not route:
            return
        
        print(f"Zone {self.zone_id}: Executing route for {truck_id}")
        
        # Simulate route execution time
        execution_time = len(route.route_bins) * 2  # 2 seconds per bin
        time.sleep(min(execution_time, 10))  # Cap at 10 seconds for demo
        
        # Complete the route and actually empty bins in the simulator
        for bin_id in route.route_bins:
            if self.bin_simulator:
                self.bin_simulator.empty_bin(bin_id)
        self.route_manager.empty_bins_in_route(truck_id)
        self.routes_completed += 1
        self.bins_serviced += len(route.route_bins)
        
        print(f"Zone {self.zone_id}: Route completed for {truck_id} - {len(route.route_bins)} bins serviced")
        
        # Update state
        overflowing_bins = self.route_manager.overflowing_bins
        self.communicator.update_state(
            len(overflowing_bins),
            self.truck_count,
            overflowing_bins
        )
    
    def update_zone_state(self):
        """Update and broadcast zone state"""
        overflowing_bins = self.route_manager.overflowing_bins
        self.communicator.update_state(
            len(overflowing_bins),
            self.truck_count,
            overflowing_bins
        )
    
    def set_leader(self, is_leader: bool):
        """Set leader status from election module"""
        self.is_leader = is_leader
        status = "LEADER" if is_leader else "FOLLOWER"
        print(f"Zone {self.zone_id}: Status changed to {status}")
    
    def get_election_status(self) -> dict:
        """Get election status for this node"""
        if self.election:
            return self.election.get_election_status()
        return {"node_id": str(self.zone_id), "state": "UNKNOWN", "leader_id": None}
    
    def get_node_status(self) -> Dict:
        """Get current node status"""
        zone_status = self.route_manager.get_zone_status()
        comm_status = self.communicator.get_communication_status()
        
        return {
            "zone_id": self.zone_id,
            "is_leader": self.is_leader,
            "total_bins": len(self.zone_bins),
            "zone_status": zone_status,
            "communication_status": comm_status,
            "election_status": self.get_election_status(),
            "statistics": {
                "routes_completed": self.routes_completed,
                "bins_serviced": self.bins_serviced,
                "spillovers_handled": self.spillovers_handled
            }
        }
    
    def start_node(self):
        """Start the fog node"""
        if self.is_running:
            return
        
        self.is_running = True
        print(f"Zone {self.zone_id}: Starting fog node")
        
        # Start communication services
        self.communicator.start_services()
        
        # Start node operation loop
        self.operation_thread = threading.Thread(target=self._operation_loop, daemon=True)
        self.operation_thread.start()
    
    def stop_node(self):
        """Stop the fog node"""
        self.is_running = False
        self.communicator.stop_services()
        print(f"Zone {self.zone_id}: Fog node stopped")
    
    def _operation_loop(self):
        """Main operation loop for the fog node"""
        while self.is_running:
            try:
                # Plan routes if there are overflowing bins
                if self.route_manager.overflowing_bins:
                    routes = self.plan_routes()
                    
                    # Execute routes (simplified - in real system would coordinate trucks)
                    for route in routes:
                        if self.is_running:  # Check if still running
                            self.execute_route(route.truck_id)
                
                # Update zone state periodically
                self.update_zone_state()
                
                # Sleep before next iteration
                time.sleep(5)
                
            except Exception as e:
                print(f"Zone {self.zone_id}: Error in operation loop: {e}")
                time.sleep(5)

class FogNodeSimulator:
    """Manages multiple fog nodes in a distributed simulation"""
    
    def __init__(self, num_zones: int = 3, trucks_per_zone: int = 1, bin_simulator = None):
        self.num_zones = num_zones
        self.trucks_per_zone = trucks_per_zone
        self.bin_simulator = bin_simulator
        self.fog_nodes: Dict[int, FogNode] = {}
        self.running = False
        self.leader_manager = LeaderManager()
        
        # Create fog nodes
        for zone_id in range(1, num_zones + 1):
            self.fog_nodes[zone_id] = FogNode(zone_id, trucks_per_zone, bin_simulator=bin_simulator)
        
        # Setup inter-node communication
        self._setup_inter_node_communication()
        
        # Setup election module
        self._setup_election()
    
    def _setup_inter_node_communication(self):
        """Setup communication between fog nodes"""
        # Connect message routers between nodes
        for zone_id, node in self.fog_nodes.items():
            for other_zone_id, other_node in self.fog_nodes.items():
                if zone_id != other_zone_id:
                    # Register peer discovery
                    zone_state = other_node.communicator.peer_discovery.create_zone_state(0, other_node.truck_count)
                    node.communicator.peer_discovery.register_peer(zone_state)
    
    def initialize_with_bins(self, bins: List[BinTelemetry]):
        """Initialize all fog nodes with bins"""
        for zone_id, node in self.fog_nodes.items():
            node.initialize_bins(bins)
    
    def handle_bin_overflow(self, bin_telemetry: BinTelemetry):
        """Handle bin overflow across all nodes"""
        target_node = self.fog_nodes.get(bin_telemetry.zone_id)
        if target_node:
            target_node.handle_bin_overflow(bin_telemetry)
    
    def simulate_message_delivery(self):
        """Simulate message delivery between nodes (for demo purposes)"""
        while self.running:
            try:
                # Process message queues for all nodes
                for zone_id, node in self.fog_nodes.items():
                    pending_messages = node.communicator.message_router.get_pending_messages()
                    
                    for message in pending_messages:
                        # Find target node
                        target_zone = message["receiver"]
                        target_node = self.fog_nodes.get(target_zone)
                        
                        if target_node:
                            # Deliver message
                            delivered = target_node.communicator.message_router.receive_message(message)
                            if delivered:
                                node.communicator.message_router.mark_message_delivered(message["id"])
                
                time.sleep(1)  # Process messages every second
                
            except Exception as e:
                print(f"Error in message delivery: {e}")
                time.sleep(1)
    
    def _setup_election(self):
        """Setup the election module for all nodes"""
        all_node_ids = [str(zid) for zid in self.fog_nodes.keys()]
        
        for zone_id, node in self.fog_nodes.items():
            node_id = str(zone_id)
            node.election = InvitationElection(node_id, all_node_ids)
            self.leader_manager.register_node(node_id, all_node_ids)
            
            # Wire election leader callback to node
            node.election.add_leader_elected_callback(
                lambda leader_id, n=node: n.set_leader(leader_id == str(n.zone_id))
            )
    
    def elect_leader(self, initiator_zone: int = None):
        """Run the invitation election algorithm"""
        self.leader_manager.start_election(str(initiator_zone) if initiator_zone else None)
        
        # Deliver messages until election completes
        for _ in range(20):
            self.leader_manager.deliver_messages()
            time.sleep(0.1)
        
        # Update leader status on all nodes
        if self.leader_manager.current_leader:
            leader_zone = int(self.leader_manager.current_leader)
            for zone_id, node in self.fog_nodes.items():
                node.set_leader(zone_id == leader_zone)
    
    def start_simulation(self):
        """Start the fog node simulation"""
        if self.running:
            return
        
        self.running = True
        print(f"Starting fog node simulation with {self.num_zones} zones")
        
        # Start all fog nodes
        for zone_id, node in self.fog_nodes.items():
            node.start_node()
        
        # Start message delivery simulation
        self.message_thread = threading.Thread(target=self.simulate_message_delivery, daemon=True)
        self.message_thread.start()
        
        # Start election heartbeat service
        self.leader_manager.start_heartbeat_service()
        
        # Run initial election
        self.elect_leader(self.num_zones)  # Highest zone initiates
    
    def stop_simulation(self):
        """Stop the fog node simulation"""
        self.running = False
        self.leader_manager.stop_heartbeat_service()
        
        # Stop all fog nodes
        for zone_id, node in self.fog_nodes.items():
            node.stop_node()
        
        print("Fog node simulation stopped")
    
    def get_system_status(self) -> Dict:
        """Get status of all fog nodes"""
        system_status = {
            "num_zones": self.num_zones,
            "trucks_per_zone": self.trucks_per_zone,
            "nodes": {},
            "system_totals": {
                "total_bins": 0,
                "total_overflowing": 0,
                "total_routes_completed": 0,
                "total_bins_serviced": 0,
                "total_spillovers": 0
            }
        }
        
        for zone_id, node in self.fog_nodes.items():
            node_status = node.get_node_status()
            system_status["nodes"][zone_id] = node_status
            
            # Update totals
            system_status["system_totals"]["total_bins"] += node_status["total_bins"]
            system_status["system_totals"]["total_overflowing"] += node_status["zone_status"]["total_overflowing_bins"]
            system_status["system_totals"]["total_routes_completed"] += node_status["statistics"]["routes_completed"]
            system_status["system_totals"]["total_bins_serviced"] += node_status["statistics"]["bins_serviced"]
            system_status["system_totals"]["total_spillovers"] += node_status["statistics"]["spillovers_handled"]
        
        return system_status
    
    def print_system_status(self):
        """Print formatted system status"""
        status = self.get_system_status()
        
        print("\n" + "="*60)
        print("FOG NODE SYSTEM STATUS")
        print("="*60)
        
        for zone_id, node_status in status["nodes"].items():
            leader_status = " (LEADER)" if node_status["is_leader"] else ""
            print(f"\nZone {zone_id}{leader_status}:")
            print(f"  Total Bins: {node_status['total_bins']}")
            print(f"  Overflowing: {node_status['zone_status']['total_overflowing_bins']}")
            print(f"  Active Routes: {node_status['zone_status']['active_routes']}")
            print(f"  Routes Completed: {node_status['statistics']['routes_completed']}")
            print(f"  Bins Serviced: {node_status['statistics']['bins_serviced']}")
            print(f"  Spillovers: {node_status['statistics']['spillovers_handled']}")
        
        print(f"\nSystem Totals:")
        totals = status["system_totals"]
        print(f"  Total Bins: {totals['total_bins']}")
        print(f"  Total Overflowing: {totals['total_overflowing']}")
        print(f"  Total Routes Completed: {totals['total_routes_completed']}")
        print(f"  Total Bins Serviced: {totals['total_bins_serviced']}")
        print(f"  Total Spillovers: {totals['total_spillovers']}")
        print("="*60)
