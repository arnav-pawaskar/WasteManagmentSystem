#!/usr/bin/env python3
"""
Fog-Based Smart Waste Management System
Main entry point for the complete system simulation
"""

import time
import signal
import sys
from datetime import datetime
from simulation.bin_simulator import BinSimulator
from simulation.fog_node_simulator import FogNodeSimulator

class SmartWasteManagementSystem:
    """Main system orchestrator"""
    
    def __init__(self, zones: int = 3, bins_per_zone: int = 15, 
                 trucks_per_zone: int = 1, update_interval: int = 5):
        self.zones = zones
        self.bins_per_zone = bins_per_zone
        self.trucks_per_zone = trucks_per_zone
        self.update_interval = update_interval
        
        # Initialize components
        self.bin_simulator = BinSimulator(zones, bins_per_zone, update_interval)
        self.fog_simulator = FogNodeSimulator(zones, trucks_per_zone, bin_simulator=self.bin_simulator)
        
        # System state
        self.running = False
        self.start_time = None
        
        # Setup callbacks
        self._setup_callbacks()
        
        # Signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _setup_callbacks(self):
        """Setup callbacks between components"""
        # Bin simulator overflow callback
        self.bin_simulator.add_telemetry_callback(self._handle_bin_overflow)
    
    def _handle_bin_overflow(self, bin_telemetry):
        """Handle bin overflow from bin simulator"""
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] OVERFLOW ALERT: {bin_telemetry.bin_id} - {bin_telemetry.fill_level:.1f}%")
        self.fog_simulator.handle_bin_overflow(bin_telemetry)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        print(f"\nReceived signal {signum}, shutting down gracefully...")
        self.shutdown()
        sys.exit(0)
    
    def initialize(self):
        """Initialize the system"""
        print("Initializing Fog-Based Smart Waste Management System")
        print(f"Configuration: {self.zones} zones, {self.bins_per_zone} bins per zone")
        print(f"Trucks per zone: {self.trucks_per_zone}, Update interval: {self.update_interval}s")
        
        # Initialize bins
        all_bins = []
        for zone_id in range(1, self.zones + 1):
            zone_bins = self.bin_simulator.get_bins_by_zone(zone_id)
            all_bins.extend(zone_bins)
        
        # Initialize fog nodes
        self.fog_simulator.initialize_with_bins(all_bins)
        
        print(f"System initialized with {len(all_bins)} total bins")
        
        # Elect a leader (Zone 1 by default for demo)
        self.fog_simulator.elect_leader(1)
        print("Zone 1 elected as leader")
    
    def start(self):
        """Start the system"""
        if self.running:
            return
        
        self.running = True
        self.start_time = datetime.now()
        
        print(f"\n{'='*60}")
        print("STARTING FOG-BASED SMART WASTE MANAGEMENT SYSTEM")
        print(f"{'='*60}")
        print(f"Started at: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Start bin simulation
        self.bin_simulator.start_simulation()
        
        # Start fog node simulation
        self.fog_simulator.start_simulation()
        
        # Start status monitoring
        self._start_status_monitoring()
        
        print("System started successfully!")
        print("Press Ctrl+C to stop the simulation")
    
    def _start_status_monitoring(self):
        """Start periodic status monitoring"""
        def monitor_loop():
            while self.running:
                try:
                    self._print_system_status()
                    time.sleep(30)  # Print status every 30 seconds
                except Exception as e:
                    print(f"Error in status monitoring: {e}")
                    time.sleep(10)
        
        self.monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        self.monitor_thread.start()
    
    def _print_system_status(self):
        """Print current system status"""
        elapsed = datetime.now() - self.start_time if self.start_time else None
        
        print(f"\n{'='*60}")
        print(f"SYSTEM STATUS - {elapsed}")
        print(f"{'='*60}")
        
        # Print bin statistics
        bin_stats = self.bin_simulator.get_statistics()
        print(f"Bin Statistics:")
        print(f"  Total Bins: {bin_stats['total_bins']}")
        print(f"  Overflowing: {bin_stats['overflowing_bins']}")
        print(f"  Avg Fill Level: {bin_stats['avg_fill_level']:.1f}%")
        
        # Print fog node status
        self.fog_simulator.print_system_status()
    
    def shutdown(self):
        """Shutdown the system"""
        if not self.running:
            return
        
        print("\nShutting down system...")
        
        self.running = False
        
        # Stop simulations
        self.bin_simulator.stop_simulation()
        self.fog_simulator.stop_simulation()
        
        # Print final statistics
        if self.start_time:
            elapsed = datetime.now() - self.start_time
            print(f"\nSystem ran for: {elapsed}")
        
        print("System shutdown complete")
    
    def run_demo(self, duration: int = 300):
        """Run a timed demo"""
        print(f"Running demo for {duration} seconds...")
        
        self.start()
        
        try:
            time.sleep(duration)
        except KeyboardInterrupt:
            pass
        
        self.shutdown()

def main():
    """Main entry point"""
    import argparse
    import threading
    
    parser = argparse.ArgumentParser(description='Fog-Based Smart Waste Management System')
    parser.add_argument('--zones', type=int, default=3, help='Number of zones (default: 3)')
    parser.add_argument('--bins-per-zone', type=int, default=15, help='Bins per zone (default: 15)')
    parser.add_argument('--trucks-per-zone', type=int, default=1, help='Trucks per zone (default: 1)')
    parser.add_argument('--update-interval', type=int, default=5, help='Bin update interval in seconds (default: 5)')
    parser.add_argument('--demo-duration', type=int, default=300, help='Demo duration in seconds (default: 300)')
    parser.add_argument('--interactive', action='store_true', help='Run in interactive mode')
    
    args = parser.parse_args()
    
    # Create and initialize system
    system = SmartWasteManagementSystem(
        zones=args.zones,
        bins_per_zone=args.bins_per_zone,
        trucks_per_zone=args.trucks_per_zone,
        update_interval=args.update_interval
    )
    
    system.initialize()
    
    if args.interactive:
        # Interactive mode
        system.start()
        
        print("\nInteractive mode - Commands:")
        print("  status - Print system status")
        print("  stats  - Print detailed statistics")
        print("  leader <zone> - Elect new leader")
        print("  quit   - Exit system")
        
        try:
            while system.running:
                try:
                    cmd = input("\n> ").strip().lower()
                    
                    if cmd == 'quit' or cmd == 'exit':
                        break
                    elif cmd == 'status':
                        system._print_system_status()
                    elif cmd == 'stats':
                        system._print_detailed_statistics()
                    elif cmd.startswith('leader'):
                        parts = cmd.split()
                        if len(parts) == 2:
                            try:
                                zone_id = int(parts[1])
                                if 1 <= zone_id <= args.zones:
                                    system.fog_simulator.elect_leader(zone_id)
                                    print(f"Zone {zone_id} elected as leader")
                                else:
                                    print(f"Invalid zone ID. Must be 1-{args.zones}")
                            except ValueError:
                                print("Invalid zone ID")
                        else:
                            print("Usage: leader <zone_id>")
                    else:
                        print("Unknown command. Try: status, stats, leader <zone>, quit")
                
                except EOFError:
                    break
                except KeyboardInterrupt:
                    break
        
        finally:
            system.shutdown()
    
    else:
        # Demo mode
        system.run_demo(args.demo_duration)

if __name__ == "__main__":
    import threading
    main()
