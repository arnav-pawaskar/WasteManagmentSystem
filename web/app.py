#!/usr/bin/env python3
"""
FastAPI backend for Fog-Based Smart Waste Management System Web UI
Provides REST API endpoints for real-time monitoring and control.

Read-only endpoints are public. Control endpoints (start/stop/config/election/
empty bin) require the X-API-Key header to match the ADMIN_API_KEY env var.

Must run with a single worker: the simulation lives in the module-global
`system_instance`, so every extra worker would run its own separate simulation.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import secrets
import threading
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from simulation.bin_simulator import BinSimulator
from simulation.fog_node_simulator import FogNodeSimulator
from web.cloud_publisher import CloudPublisher

WEB_DIR = Path(__file__).resolve().parent

# Global system instance, swapped under _system_lock
system_instance = None
_system_lock = threading.Lock()

# Pushes snapshots to Supabase when SUPABASE_URL / SUPABASE_SECRET_KEY are set
cloud_publisher: Optional[CloudPublisher] = None

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
            # Offset-aware so browsers in another timezone than the server render it correctly
            "timestamp": datetime.now().astimezone().isoformat(),
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
        # Snapshot before iterating: simulation threads mutate these collections
        # concurrently with Flask request threads.
        for bin_id, bin_telemetry in list(self.bin_simulator.bins.items()):
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
        for zone_id, node in list(self.fog_simulator.fog_nodes.items()):
            # active_routes is mutated by the node's operation thread (routes are
            # added and deleted as trucks are dispatched), so iterating it live
            # raises "dictionary changed size during iteration" under load.
            zone_bins = {b.bin_id: b for b in list(node.zone_bins)}
            for truck_id, route in list(node.route_manager.active_routes.items()):
                route_bins = []
                for bin_id in list(route.route_bins):
                    bin_telemetry = zone_bins.get(bin_id)
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

        for zone_id, node in list(self.fog_simulator.fog_nodes.items()):
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

# ---------------------------------------------------------------------------
# API models and auth
# ---------------------------------------------------------------------------

class SystemConfig(BaseModel):
    """Simulation configuration. Bounds mirror the inputs in index.html and keep
    a public caller from sizing the simulation beyond what a 1 GB VM can hold."""
    zones: int = Field(3, ge=1, le=10)
    bins_per_zone: int = Field(15, ge=5, le=50)
    trucks_per_zone: int = Field(1, ge=1, le=5)
    update_interval: int = Field(3, ge=1, le=10)


class ElectionRequest(BaseModel):
    initiator_zone: Optional[int] = None


def require_admin(x_api_key: Optional[str] = Header(None)):
    """Guard control endpoints. Fails closed when no admin key is configured."""
    expected = os.environ.get("ADMIN_API_KEY", "")
    if not expected:
        raise HTTPException(status_code=503, detail="Admin key not configured on server")
    if not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


def _require_system() -> SmartWasteSystem:
    if not system_instance:
        raise HTTPException(status_code=503, detail="System not initialized")
    return system_instance


def _autostart_enabled() -> bool:
    return os.environ.get("AUTOSTART", "true").strip().lower() in ("1", "true", "yes")


def build_snapshot(event_limit: int = 30) -> Optional[dict]:
    """Everything the dashboard needs in one document (what /api/* return together)."""
    system = system_instance
    if not system:
        return None
    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "status": system.get_status(),
        "bins": system.get_bins_data(),
        "routes": system.get_routes_data(),
        "network": system.get_network_topology(),
        "events": system.get_events(event_limit),
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start a default simulation so the public dashboard is live on first visit."""
    global system_instance, cloud_publisher
    if _autostart_enabled():
        with _system_lock:
            if not system_instance:
                system_instance = SmartWasteSystem()
            system_instance.start()

    cloud_publisher = CloudPublisher.from_env(build_snapshot)
    if cloud_publisher:
        cloud_publisher.start()
    yield
    with _system_lock:
        if system_instance:
            system_instance.stop()
    if cloud_publisher:
        cloud_publisher.publish_once()   # leave the cloud showing "stopped"
        cloud_publisher.stop()


app = FastAPI(
    title="Fog-Based Smart Waste Management System",
    description="Monitoring and control API for the fog-node waste collection simulation.",
    version="1.0.0",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")

# ---------------------------------------------------------------------------
# Endpoints. Declared as plain `def` so they run in the threadpool: election
# blocks for ~2 s and must not stall the event loop.
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
def index():
    """Serve the main UI page"""
    return FileResponse(WEB_DIR / "templates" / "index.html")

@app.get("/health", tags=["public"])
def health():
    """Liveness check"""
    return {
        "status": "ok",
        "running": bool(system_instance and system_instance.running),
        "cloud": cloud_publisher.get_status() if cloud_publisher else {"enabled": False},
    }

@app.get("/api/system/status", tags=["public"])
def api_system_status():
    """Get system status"""
    return _require_system().get_status()

@app.post("/api/system/start", tags=["admin"], dependencies=[Depends(require_admin)])
def api_system_start():
    """Start the system"""
    global system_instance
    with _system_lock:
        if not system_instance:
            system_instance = SmartWasteSystem()
        system_instance.start()
    return {"status": "started"}

@app.post("/api/system/stop", tags=["admin"], dependencies=[Depends(require_admin)])
def api_system_stop():
    """Stop the system"""
    with _system_lock:
        if system_instance:
            system_instance.stop()
    return {"status": "stopped"}

@app.post("/api/system/config", tags=["admin"], dependencies=[Depends(require_admin)])
def api_system_config(config: Optional[SystemConfig] = None):
    """Configure and (re)start the system"""
    global system_instance
    config = config or SystemConfig()

    with _system_lock:
        if system_instance:
            system_instance.stop()
        system_instance = SmartWasteSystem(config.zones, config.bins_per_zone,
                                           config.trucks_per_zone, config.update_interval)
        system_instance.start()

    return {"status": "configured_and_started", "config": config.model_dump()}

@app.get("/api/bins", tags=["public"])
def api_bins():
    """Get all bin data"""
    return _require_system().get_bins_data()

@app.get("/api/routes", tags=["public"])
def api_routes():
    """Get all active routes"""
    return _require_system().get_routes_data()

@app.get("/api/network", tags=["public"])
def api_network():
    """Get network topology"""
    return _require_system().get_network_topology()

@app.get("/api/events", tags=["public"])
def api_events(limit: int = Query(50, ge=1, le=100)):
    """Get recent events"""
    if not system_instance:
        return []
    return system_instance.get_events(limit)

@app.post("/api/election/trigger", tags=["admin"], dependencies=[Depends(require_admin)])
def api_trigger_election(request: Optional[ElectionRequest] = None):
    """Manually trigger leader election"""
    system = _require_system()
    initiator = request.initiator_zone if request else None
    if initiator is not None and not 1 <= initiator <= system.zones:
        raise HTTPException(status_code=400,
                            detail=f"initiator_zone must be between 1 and {system.zones}")
    return system.trigger_election(initiator)

@app.post("/api/bin/{bin_id}/empty", tags=["admin"], dependencies=[Depends(require_admin)])
def api_empty_bin(bin_id: str):
    """Manually empty a specific bin"""
    system = _require_system()
    if bin_id not in system.bin_simulator.bins:
        raise HTTPException(status_code=404, detail=f"Unknown bin {bin_id}")
    return system.empty_bin(bin_id)
