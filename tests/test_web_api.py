#!/usr/bin/env python3
"""
Test suite for the FastAPI web layer (web/app.py).

Requires the web dependencies: pip install -r web/requirements.txt
Skipped automatically when they are not installed, so the core suite stays
standard-library only.
"""

import sys
import os
import unittest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from fastapi.testclient import TestClient
    from web import app as web_app
    HAVE_WEB_DEPS = True
except ImportError:
    HAVE_WEB_DEPS = False

ADMIN_KEY = "test-admin-key"
CONTROL_ENDPOINTS = [
    ("/api/system/stop", None),
    ("/api/system/start", None),
    ("/api/system/config", {"zones": 2, "bins_per_zone": 5, "trucks_per_zone": 1, "update_interval": 1}),
    ("/api/election/trigger", {"initiator_zone": None}),
]


@unittest.skipUnless(HAVE_WEB_DEPS, "web dependencies not installed")
class TestWebAPI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._saved_env = {k: os.environ.get(k) for k in ("ADMIN_API_KEY", "AUTOSTART")}
        os.environ["ADMIN_API_KEY"] = ADMIN_KEY
        os.environ["AUTOSTART"] = "true"
        # Entering the client runs the lifespan hook, which autostarts the simulation
        cls.client = TestClient(web_app.app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        # Exiting runs lifespan shutdown, which stops the simulation threads
        cls.client.__exit__(None, None, None)
        for key, value in cls._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def admin(self):
        return {"X-API-Key": ADMIN_KEY}

    def configure(self, zones=2, bins_per_zone=5):
        response = self.client.post("/api/system/config", headers=self.admin(), json={
            "zones": zones, "bins_per_zone": bins_per_zone,
            "trucks_per_zone": 1, "update_interval": 1})
        self.assertEqual(response.status_code, 200)
        return response.json()

    # --- public endpoints -------------------------------------------------

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_health_reports_cloud_sync_disabled_without_supabase(self):
        self.assertEqual(self.client.get("/health").json()["cloud"], {"enabled": False})

    def test_cloud_snapshot_is_json_serializable(self):
        import json
        snap = web_app.build_snapshot()
        for key in ("status", "bins", "routes", "network", "events", "generated_at"):
            self.assertIn(key, snap)
        json.dumps(snap)   # what the publisher sends must encode without a fallback

    def test_index_and_static_assets(self):
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("text/html", page.headers["content-type"])
        self.assertIn("/static/app.js", page.text)
        self.assertEqual(self.client.get("/static/app.js").status_code, 200)
        self.assertEqual(self.client.get("/static/style.css").status_code, 200)

    def test_autostart_runs_default_system(self):
        status = self.client.get("/api/system/status").json()
        self.assertIn("configuration", status)
        self.assertIn("fog_nodes", status)
        self.assertIn("election_status", status)

    def test_bins_match_configuration(self):
        self.configure(zones=2, bins_per_zone=5)
        bins = self.client.get("/api/bins").json()
        self.assertEqual(len(bins), 10)
        for key in ("bin_id", "zone_id", "x", "y", "fill_level", "is_overflowing"):
            self.assertIn(key, bins[0])

    def test_network_and_routes_shape(self):
        self.configure(zones=3, bins_per_zone=5)
        network = self.client.get("/api/network").json()
        self.assertEqual(len(network["nodes"]), 3)
        self.assertEqual(len(network["edges"]), 6)
        self.assertIsInstance(self.client.get("/api/routes").json(), list)

    def test_events_limit_bounds(self):
        self.assertEqual(self.client.get("/api/events?limit=5").status_code, 200)
        self.assertLessEqual(len(self.client.get("/api/events?limit=5").json()), 5)
        self.assertEqual(self.client.get("/api/events?limit=0").status_code, 422)
        self.assertEqual(self.client.get("/api/events?limit=1000").status_code, 422)

    # --- admin auth -------------------------------------------------------

    def test_control_endpoints_reject_missing_key(self):
        for path, body in CONTROL_ENDPOINTS:
            with self.subTest(path=path):
                self.assertEqual(self.client.post(path, json=body).status_code, 401)

    def test_control_endpoints_reject_wrong_key(self):
        for path, body in CONTROL_ENDPOINTS:
            with self.subTest(path=path):
                response = self.client.post(path, json=body, headers={"X-API-Key": "wrong"})
                self.assertEqual(response.status_code, 401)

    def test_control_endpoints_fail_closed_without_server_key(self):
        os.environ.pop("ADMIN_API_KEY")
        try:
            response = self.client.post("/api/system/stop", headers={"X-API-Key": ""})
            self.assertEqual(response.status_code, 503)
        finally:
            os.environ["ADMIN_API_KEY"] = ADMIN_KEY

    def test_stop_and_start_with_key(self):
        self.assertEqual(self.client.post("/api/system/stop", headers=self.admin()).status_code, 200)
        self.assertFalse(self.client.get("/health").json()["running"])
        self.assertEqual(self.client.post("/api/system/start", headers=self.admin()).status_code, 200)
        self.assertTrue(self.client.get("/health").json()["running"])

    # --- validation -------------------------------------------------------

    def test_config_rejects_out_of_range_values(self):
        for bad in ({"zones": 1000}, {"bins_per_zone": 1}, {"trucks_per_zone": 0}):
            with self.subTest(body=bad):
                response = self.client.post("/api/system/config", json=bad, headers=self.admin())
                self.assertEqual(response.status_code, 422)

    def test_config_returns_applied_values(self):
        result = self.configure(zones=2, bins_per_zone=6)
        self.assertEqual(result["status"], "configured_and_started")
        self.assertEqual(result["config"]["zones"], 2)
        self.assertEqual(result["config"]["bins_per_zone"], 6)

    def test_election_rejects_unknown_zone(self):
        self.configure(zones=2, bins_per_zone=5)
        response = self.client.post("/api/election/trigger", json={"initiator_zone": 9},
                                    headers=self.admin())
        self.assertEqual(response.status_code, 400)

    def test_empty_bin(self):
        self.configure(zones=2, bins_per_zone=5)
        bin_id = self.client.get("/api/bins").json()[0]["bin_id"]
        response = self.client.post(f"/api/bin/{bin_id}/empty", headers=self.admin())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.post("/api/bin/no_such_bin/empty",
                                          headers=self.admin()).status_code, 404)


if __name__ == "__main__":
    unittest.main()
