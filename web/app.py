#!/usr/bin/env python3
"""
Flask backend for Fog-Based Smart Waste Management System Web UI
Provides REST API endpoints for real-time monitoring and control
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
import threading
import time
import json
from datetime import datetime
from simulation.bin_simulator import BinSimulator
from simulation.fog_node_simulator import FogNodeSimulator

app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app)

# Global system instance
system_instance = None

class SmartWasteSystem:
    """Wrapper class for the complete system with web API"""
    
    def __init__(self, zones=3, bins_per_zone=15, trucks_per_zone=1, update_interval=3):
        self.zones = zones
        self.bins_per_zone = bins_per_zone
        self.trucks_per_zone = trucks_per_zone
        self.update_interval = update_interval
        
        # Initialize components
        self.bin_simulator = BinSimulator(zones, bins_per_zone, update_interval)
        self.fog_simulator = FogNodeSimulator(zones, trucks_per_zone, bin_simulator=self.bin_simulator)
        
        # Event log for UI
        self.event_log = []
        self.max_log_entries = 100
        
        # Setup callbacks
        self._setup_callbacks()
        
        # Initialize bins
        all_bins = []
        for zone_id in range(1, zones + 1):
            zone_bins = self.bin_simulator.get_bins_by_zone(zone_id)
            all_bins.extend(zone_bins)
        self.fog_simulator.initialize_with_bins(all_bins)
        
        self.running = False
    
    def _setup_callbacks(self):
        """Setup callbacks for event logging"""
        def handle_overflow(bin_telemetry):
            self._log_event("OVERFLOW", f"Bin {bin_telemetry.bin_id} reached {bin_telemetry.fill_level:.1f}%", {
                "bin_id": bin_telemetry.bin_id,
                "zone_id": bin_telemetry.zone_id,
                "fill_level": bin_telemetry.fill_level
            })
            self.fog_simulator.handle_bin_overflow(bin_telemetry)
        
        self.bin_simulator.add_telemetry_callback(handle_overflow)
    
    def _log_event(self, event_type, message, data=None):
        """Add event to log"""
        event = {
            "timestamp": datetime.now().isoformat(),
            "type": event_type,
            "message": message,
            "data": data or {}
        }
        self.event_log.append(event)
        if len(self.event_log) > self.max_log_entries:
            self.event_log.pop(0)
    
    def start(self):
        """Start the system"""
        if self.running:
            return
        
        self.running = True
        self.bin_simulator.start_simulation()
        self.fog_simulator.start_simulation()
        self._log_event("SYSTEM", "System started")
    
    def stop(self):
        """Stop the system"""
        self.running = False
        self.bin_simulator.stop_simulation()
        self.fog_simulator.stop_simulation()
        self._log_event("SYSTEM", "System stopped")
    
    def get_status(self):
        """Get complete system status"""
        bin_stats = self.bin_simulator.get_statistics()
        fog_status = self.fog_simulator.get_system_status()
        
        return {
            "running": self.running,
            "configuration": {
                "zones": self.zones,
                "bins_per_zone": self.bins_per_zone,
                "trucks_per_zone": self.trucks_per_zone,
                "update_interval": self.update_interval
            },
            "bin_statistics": bin_stats,
            "fog_nodes": fog_status,
            "election_status": self.fog_simulator.leader_manager.get_election_overview() if self.fog_simulator.leader_manager else {}
        }
    
    def get_bins_data(self):
        """Get all bin data for visualization"""
        bins_data = []
        for bin_id, bin_telemetry in self.bin_simulator.bins.items():
            bins_data.append({
                "bin_id": bin_id,
                "zone_id": bin_telemetry.zone_id,
                "x": bin_telemetry.x,
                "y": bin_telemetry.y,
                "fill_level": bin_telemetry.fill_level,
                "is_overflowing": bin_telemetry.is_overflowing(),
                "timestamp": bin_telemetry.timestamp.isoformat()
            })
        return bins_data
    
    def get_routes_data(self):
        """Get all active routes"""
        routes_data = []
        for zone_id, node in self.fog_simulator.fog_nodes.items():
            for truck_id, route in node.route_manager.active_routes.items():
                route_bins = []
                for bin_id in route.route_bins:
                    bin_telemetry = node.zone_bins[0] if node.zone_bins else None
                    for b in node.zone_bins:
                        if b.bin_id == bin_id:
                            bin_telemetry = b
                            break
                    if bin_telemetry:
                        route_bins.append({
                            "bin_id": bin_id,
                            "x": bin_telemetry.x,
                            "y": bin_telemetry.y
                        })
                
                routes_data.append({
                    "zone_id": zone_id,
                    "truck_id": truck_id,
                    "bins": route_bins,
                    "total_distance": route.route_distance,
                    "bin_count": len(route.route_bins)
                })
        return routes_data
    
    def get_network_topology(self):
        """Get fog node network topology"""
        nodes = []
        edges = []
        
        for zone_id, node in self.fog_simulator.fog_nodes.items():
            is_leader = node.is_leader
            election_status = node.get_election_status()
            
            nodes.append({
                "id": zone_id,
                "label": f"Zone {zone_id}",
                "is_leader": is_leader,
                "state": election_status.get("state", "UNKNOWN"),
                "active_bins": len(node.route_manager.overflowing_bins),
                "truck_count": node.truck_count,
                "routes_completed": node.routes_completed
            })
            
            # Add edges for peer connections
            for peer_id, peer_node in self.fog_simulator.fog_nodes.items():
                if zone_id != peer_id:
                    edges.append({
                        "from": zone_id,
                        "to": peer_id,
                        "type": "peer_connection"
                    })
        
        return {"nodes": nodes, "edges": edges}
    
    def get_events(self, limit=50):
        """Get recent events"""
        return self.event_log[-limit:]
    
    def trigger_election(self, initiator_zone=None):
        """Manually trigger leader election"""
        self.fog_simulator.elect_leader(initiator_zone)
        self._log_event("ELECTION", f"Leader election triggered by Zone {initiator_zone or 'auto'}")
        return {"status": "election_initiated"}
    
    def empty_bin(self, bin_id):
        """Manually empty a bin"""
        self.bin_simulator.empty_bin(bin_id)
        self._log_event("ACTION", f"Manually emptied bin {bin_id}")
        return {"status": "bin_emptied"}

# Flask API Endpoints

@app.route('/')
def index():
    """Serve the main UI page"""
    return render_template('index.html')

@app.route('/api/system/status', methods=['GET'])
def api_system_status():
    """Get system status"""
    if not system_instance:
        return jsonify({"error": "System not initialized"}), 500
    return jsonify(system_instance.get_status())

@app.route('/api/system/start', methods=['POST'])
def api_system_start():
    """Start the system"""
    global system_instance
    if not system_instance:
        system_instance = SmartWasteSystem()
    system_instance.start()
    return jsonify({"status": "started"})

@app.route('/api/system/stop', methods=['POST'])
def api_system_stop():
    """Stop the system"""
    if system_instance:
        system_instance.stop()
    return jsonify({"status": "stopped"})

@app.route('/api/system/config', methods=['POST'])
def api_system_config():
    """Configure and initialize the system"""
    global system_instance
    data = request.get_json() or {}
    
    zones = data.get('zones', 3)
    bins_per_zone = data.get('bins_per_zone', 15)
    trucks_per_zone = data.get('trucks_per_zone', 1)
    update_interval = data.get('update_interval', 3)
    
    if system_instance:
        system_instance.stop()
    
    system_instance = SmartWasteSystem(zones, bins_per_zone, trucks_per_zone, update_interval)
    system_instance.start()
    
    return jsonify({
        "status": "configured_and_started",
        "config": {
            "zones": zones,
            "bins_per_zone": bins_per_zone,
            "trucks_per_zone": trucks_per_zone,
            "update_interval": update_interval
        }
    })

@app.route('/api/bins', methods=['GET'])
def api_bins():
    """Get all bin data"""
    if not system_instance:
        return jsonify({"error": "System not initialized"}), 500
    return jsonify(system_instance.get_bins_data())

@app.route('/api/routes', methods=['GET'])
def api_routes():
    """Get all active routes"""
    if not system_instance:
        return jsonify({"error": "System not initialized"}), 500
    return jsonify(system_instance.get_routes_data())

@app.route('/api/network', methods=['GET'])
def api_network():
    """Get network topology"""
    if not system_instance:
        return jsonify({"error": "System not initialized"}), 500
    return jsonify(system_instance.get_network_topology())

@app.route('/api/events', methods=['GET'])
def api_events():
    """Get recent events"""
    if not system_instance:
        return jsonify([])
    limit = request.args.get('limit', 50, type=int)
    return jsonify(system_instance.get_events(limit))

@app.route('/api/election/trigger', methods=['POST'])
def api_trigger_election():
    """Manually trigger leader election"""
    if not system_instance:
        return jsonify({"error": "System not initialized"}), 500
    data = request.get_json() or {}
    initiator = data.get('initiator_zone')
    return jsonify(system_instance.trigger_election(initiator))

@app.route('/api/bin/<bin_id>/empty', methods=['POST'])
def api_empty_bin(bin_id):
    """Manually empty a specific bin"""
    if not system_instance:
        return jsonify({"error": "System not initialized"}), 500
    return jsonify(system_instance.empty_bin(bin_id))

if __name__ == '__main__':
    # Initialize system with defaults
    system_instance = SmartWasteSystem()
    
    # Start the Flask server
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
