#!/usr/bin/env python3
"""
Launcher script for the Fog Waste Management System Web UI
"""

import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, system_instance

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
        app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
    except KeyboardInterrupt:
        print("\nShutting down...")
        if system_instance:
            system_instance.stop()
        print("Server stopped.")
