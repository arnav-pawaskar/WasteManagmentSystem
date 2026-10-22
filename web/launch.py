#!/usr/bin/env python3
"""
Launcher script for the Fog Waste Management System Web UI

Environment:
  ADMIN_API_KEY  key required by Start/Stop/Election (control endpoints are disabled without it)
  AUTOSTART      start a default simulation on launch (default: true)
  HOST, PORT     bind address (default: 127.0.0.1:8000)
"""

import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Add parent directory to path
sys.path.append(ROOT)


def load_env_file(path):
    """Minimal .env reader (KEY=VALUE lines). Real environment variables win."""
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file(os.path.join(ROOT, ".env"))

import uvicorn
from app import app

if __name__ == '__main__':
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))

    print("=" * 60)
    print("Fog-Based Smart Waste Management System - Web UI")
    print("=" * 60)
    print()
    print(f"Open your browser and navigate to: http://localhost:{port}")
    print(f"API documentation (Swagger):       http://localhost:{port}/docs")
    print()
    if not os.getenv("ADMIN_API_KEY"):
        print("WARNING: ADMIN_API_KEY is not set - Start/Stop/Election are disabled.")
        print()
    if os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SECRET_KEY"):
        print("Cloud sync: ON - publishing snapshots to Supabase")
    else:
        print("Cloud sync: OFF (set SUPABASE_URL and SUPABASE_SECRET_KEY in .env)")
    print()
    print("Features:")
    print("  - Real-time bin status visualization")
    print("  - Truck route tracking")
    print("  - Fog node network topology")
    print("  - Invitation Election Algorithm visualization")
    print("  - Event log and system statistics")
    print()
    print("Press Ctrl+C to stop the server")
    print("=" * 60)
    print()

    # Single worker only: the simulation is held in a module-global in app.py.
    # Shutdown (Ctrl+C) stops the simulation via the app's lifespan hook.
    uvicorn.run(app, host=host, port=port, workers=1)
