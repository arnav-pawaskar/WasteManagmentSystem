#!/usr/bin/env python3
"""
Launcher script for the Fog Waste Management System Web UI
"""

import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the module, not the name: `from app import system_instance` binds a copy of
# the value at import time (None), so the shutdown handler below would never see the
# system the app actually created.
import app as app_module
from app import app

if __name__ == '__main__':
    print("=" * 60)
    print("Fog-Based Smart Waste Management System - Web UI")
    print("=" * 60)
    print()
    print("Open your browser and navigate to: http://localhost:5000")
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
    
    try:
        app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        print("\nShutting down...")
        if app_module.system_instance:
            app_module.system_instance.stop()
        print("Server stopped.")
