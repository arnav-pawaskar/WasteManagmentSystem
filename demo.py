#!/usr/bin/env python3
"""
Demo script for Fog-Based Smart Waste Management System
Showcases all three modules working together
"""

import time
import threading
from datetime import datetime
from simulation.bin_simulator import BinSimulator
from simulation.fog_node_simulator import FogNodeSimulator

def run_basic_demo():
    """Run a basic demo of the system"""
    print("Starting Basic Demo - Fog-Based Smart Waste Management System")
    print("=" * 70)
    
    # Configuration
    zones = 3
    bins_per_zone = 15
    trucks_per_zone = 1
    demo_duration = 120  # 2 minutes
    
    # Initialize components
    bin_simulator = BinSimulator(zones, bins_per_zone, update_interval=3)
    fog_simulator = FogNodeSimulator(zones, trucks_per_zone, bin_simulator=bin_simulator)
    
    # Setup callback for bin overflow
    def handle_overflow(bin_telemetry):
        print(f"\n[OVERFLOW] {bin_telemetry.bin_id} - {bin_telemetry.fill_level:.1f}%")
        fog_simulator.handle_bin_overflow(bin_telemetry)
    
    bin_simulator.add_telemetry_callback(handle_overflow)
    
    # Initialize system
    all_bins = []
    for zone_id in range(1, zones + 1):
        zone_bins = bin_simulator.get_bins_by_zone(zone_id)
        all_bins.extend(zone_bins)
    
    fog_simulator.initialize_with_bins(all_bins)
    fog_simulator.elect_leader(1)
    
    print(f"System initialized: {len(all_bins)} bins across {zones} zones")
    print(f"Each zone has {trucks_per_zone} truck(s)")
    print(f"Demo duration: {demo_duration} seconds")
    print("\nStarting simulation...\n")
    
    # Start simulations
    bin_simulator.start_simulation()
    fog_simulator.start_simulation()
    
    # Start message delivery simulation
    def message_delivery():
        while bin_simulator.running:
            # Simulate message delivery between fog nodes
            for zone_id, node in fog_simulator.fog_nodes.items():
                pending_messages = node.communicator.message_router.get_pending_messages()
                
                for message in pending_messages:
                    target_zone = message["receiver"]
                    target_node = fog_simulator.fog_nodes.get(target_zone)
                    
                    if target_node:
                        delivered = target_node.communicator.message_router.receive_message(message)
                        if delivered:
                            node.communicator.message_router.mark_message_delivered(message["id"])
                            print(f"[MESSAGE] {message['type']} from Zone {message['sender']} to Zone {target_zone}")
            
            time.sleep(2)
    
    message_thread = threading.Thread(target=message_delivery, daemon=True)
    message_thread.start()
    
    # Run demo
    start_time = datetime.now()
    
    try:
        while (datetime.now() - start_time).seconds < demo_duration:
            # Print status every 20 seconds
            if (datetime.now() - start_time).seconds % 20 == 0:
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] System Status:")
                
                # Bin statistics
                bin_stats = bin_simulator.get_statistics()
                print(f"  Bins: {bin_stats['total_bins']} total, {bin_stats['overflowing_bins']} overflowing")
                print(f"  Avg fill: {bin_stats['avg_fill_level']:.1f}%")
                
                # Fog node statistics
                for zone_id, node in fog_simulator.fog_nodes.items():
                    status = node.get_node_status()
                    leader_status = " (LEADER)" if status["is_leader"] else ""
                    print(f"  Zone {zone_id}{leader_status}: {status['zone_status']['total_overflowing_bins']} overflowing, "
                          f"{status['zone_status']['active_routes']} active routes")
            
            time.sleep(1)
    
    except KeyboardInterrupt:
        print("\nDemo interrupted by user")
    
    finally:
        # Stop simulations
        bin_simulator.stop_simulation()
        fog_simulator.stop_simulation()
        
        # Print final statistics
        elapsed = datetime.now() - start_time
        print(f"\nDemo completed after {elapsed}")
        
        print("\nFinal System Status:")
        fog_simulator.print_system_status()
        
        # Show module integration
        print("\nModule Integration Summary:")
        print("1. Route Optimization: Generated optimal truck routes using Nearest Neighbour algorithm")
        print("2. Inter-Fog Communication: Enabled peer discovery, state gossip, and load balancing")
        print("3. Election Module: Leader election coordinated cross-zone decisions")
        print("\nKey Features Demonstrated:")
        print("- Distributed fog computing architecture")
        print("- Dynamic route planning based on bin overflow")
        print("- Load balancing through spillover between zones")
        print("- Leader-based coordination")
        print("- Real-time telemetry processing")

def run_scenario_demo():
    """Run a specific scenario demo"""
    print("Scenario Demo: High Load Situation")
    print("=" * 50)
    
    # Create a high-load scenario
    zones = 3
    bins_per_zone = 20  # More bins
    trucks_per_zone = 1
    
    bin_simulator = BinSimulator(zones, bins_per_zone, update_interval=2)
    fog_simulator = FogNodeSimulator(zones, trucks_per_zone, bin_simulator=bin_simulator)
    
    # Setup callback
    def handle_overflow(bin_telemetry):
        print(f"[OVERFLOW] {bin_telemetry.bin_id} - {bin_telemetry.fill_level:.1f}%")
        fog_simulator.handle_bin_overflow(bin_telemetry)
    
    bin_simulator.add_telemetry_callback(handle_overflow)
    
    # Initialize
    all_bins = []
    for zone_id in range(1, zones + 1):
        zone_bins = bin_simulator.get_bins_by_zone(zone_id)
        all_bins.extend(zone_bins)
    
    fog_simulator.initialize_with_bins(all_bins)
    fog_simulator.elect_leader(1)
    
    print(f"High-load scenario: {len(all_bins)} bins, rapid fill rate")
    print("Watch for spillover events and load balancing...\n")
    
    # Start simulations
    bin_simulator.start_simulation()
    fog_simulator.start_simulation()
    
    # Message delivery
    def message_delivery():
        while bin_simulator.running:
            for zone_id, node in fog_simulator.fog_nodes.items():
                pending_messages = node.communicator.message_router.get_pending_messages()
                
                for message in pending_messages:
                    target_zone = message["receiver"]
                    target_node = fog_simulator.fog_nodes.get(target_zone)
                    
                    if target_node:
                        delivered = target_node.communicator.message_router.receive_message(message)
                        if delivered:
                            node.communicator.message_router.mark_message_delivered(message["id"])
                            
                            # Highlight spillover events
                            if message["type"] == "spillover_request":
                                print(f"[SPILLOVER] Zone {message['sender']} requesting help from Zone {target_zone}")
                            elif message["type"] == "spillover_response":
                                data = message["data"]
                                status = "ACCEPTED" if data.accepted else "REJECTED"
                                print(f"[SPILLOVER] Zone {target_zone} {status} request from Zone {message['sender']}")
            
            time.sleep(1)
    
    message_thread = threading.Thread(target=message_delivery, daemon=True)
    message_thread.start()
    
    # Run for shorter duration
    try:
        time.sleep(60)  # 1 minute
    except KeyboardInterrupt:
        pass
    
    # Stop and show results
    bin_simulator.stop_simulation()
    fog_simulator.stop_simulation()
    
    print("\nScenario Results:")
    print("Spillover Statistics:")
    for zone_id, node in fog_simulator.fog_nodes.items():
        spillover_stats = node.communicator.spillover_manager.get_spillover_statistics()
        print(f"  Zone {zone_id}: {spillover_stats['total_spillovers']} spillovers, "
              f"{spillover_stats['success_rate']:.1f}% success rate")

def main():
    """Main demo entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Fog-Based Smart Waste Management System Demo')
    parser.add_argument('--scenario', choices=['basic', 'high-load'], default='basic',
                       help='Demo scenario to run (default: basic)')
    
    args = parser.parse_args()
    
    if args.scenario == 'basic':
        run_basic_demo()
    elif args.scenario == 'high-load':
        run_scenario_demo()
    
    print("\nDemo completed! The system demonstrated:")
    print("1. Route Optimization Module: Optimal truck routing using Nearest Neighbour")
    print("2. Inter-Fog Communication Module: Peer discovery and load balancing")
    print("3. Election Module: Leader election for coordination")
    print("4. Integration: All modules working together in a distributed fog architecture")

if __name__ == "__main__":
    main()
