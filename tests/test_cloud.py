#!/usr/bin/env python3
"""
Test suite for the cloud tier: the Supabase publisher (web/cloud_publisher.py)
and the Firebase Hosting build (hosting/build.py). Uses a local fake Supabase
endpoint, so no network access or real keys are needed.
"""

import base64
import importlib.util
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT))

from web.cloud_publisher import CloudPublisher, SNAPSHOT_ID

spec = importlib.util.spec_from_file_location("hosting_build", ROOT / "hosting" / "build.py")
hosting_build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hosting_build)


def fake_jwt(role):
    def seg(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")
    return f"{seg({'alg': 'HS256'})}.{seg({'role': role})}.signature"


class FakeSupabase:
    """Records requests to /rest/v1/snapshots and answers with a fixed status."""

    def __init__(self, status=201):
        self.status = status
        self.requests = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                outer.requests.append({
                    "path": self.path,
                    "headers": {k.lower(): v for k, v in self.headers.items()},
                    "body": json.loads(self.rfile.read(length)),
                })
                self.send_response(outer.status)
                self.end_headers()
                if outer.status >= 400:
                    self.wfile.write(b'{"message":"denied"}')

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def snapshot(running=True):
    return {"status": {"running": running}, "bins": [{"bin_id": "bin_1_1"}], "routes": [],
            "network": {"nodes": [], "edges": []}, "events": []}


class TestCloudPublisher(unittest.TestCase):

    def setUp(self):
        self.fake = FakeSupabase()

    def tearDown(self):
        self.fake.close()

    def test_upserts_live_row(self):
        pub = CloudPublisher(self.fake.url, "sb_secret_abc", lambda: snapshot())
        self.assertTrue(pub.publish_once())

        req = self.fake.requests[0]
        self.assertEqual(req["path"], "/rest/v1/snapshots?on_conflict=id")
        self.assertEqual(req["headers"]["apikey"], "sb_secret_abc")
        self.assertIn("resolution=merge-duplicates", req["headers"]["prefer"])
        self.assertEqual(req["body"]["id"], SNAPSHOT_ID)
        self.assertEqual(req["body"]["payload"]["bins"][0]["bin_id"], "bin_1_1")
        self.assertIn("cloud", req["body"]["payload"])
        self.assertEqual(pub.published, 1)
        self.assertIsNotNone(pub.last_ms)

    def test_accepts_data_api_url_with_rest_v1_suffix(self):
        pub = CloudPublisher(self.fake.url + "/rest/v1/", "sb_secret_abc", lambda: snapshot())
        self.assertTrue(pub.publish_once())
        self.assertEqual(self.fake.requests[0]["path"], "/rest/v1/snapshots?on_conflict=id")

    def test_new_style_key_is_not_sent_as_bearer(self):
        CloudPublisher(self.fake.url, "sb_secret_abc", lambda: snapshot()).publish_once()
        self.assertNotIn("authorization", self.fake.requests[0]["headers"])

    def test_legacy_jwt_key_is_also_sent_as_bearer(self):
        key = fake_jwt("service_role")
        CloudPublisher(self.fake.url, key, lambda: snapshot()).publish_once()
        self.assertEqual(self.fake.requests[0]["headers"]["authorization"], f"Bearer {key}")

    def test_reports_previous_sync_latency(self):
        pub = CloudPublisher(self.fake.url, "sb_secret_abc", lambda: snapshot())
        pub.publish_once()
        pub.publish_once()
        self.assertIsNone(self.fake.requests[0]["body"]["payload"]["cloud"]["sync_ms"])
        self.assertIsNotNone(self.fake.requests[1]["body"]["payload"]["cloud"]["sync_ms"])

    def test_stopped_state_is_published_once(self):
        pub = CloudPublisher(self.fake.url, "sb_secret_abc", lambda: snapshot(running=False))
        self.assertTrue(pub.publish_once())
        self.assertFalse(pub.publish_once())
        self.assertEqual(len(self.fake.requests), 1)

    def test_no_system_publishes_nothing(self):
        pub = CloudPublisher(self.fake.url, "sb_secret_abc", lambda: None)
        self.assertFalse(pub.publish_once())
        self.assertEqual(self.fake.requests, [])

    def test_http_error_is_recorded_not_raised(self):
        self.fake.status = 401
        pub = CloudPublisher(self.fake.url, "sb_secret_bad", lambda: snapshot())
        self.assertFalse(pub.publish_once())
        self.assertEqual(pub.failures, 1)
        self.assertIn("401", pub.last_error)

    def test_unreachable_server_is_recorded_not_raised(self):
        pub = CloudPublisher("http://127.0.0.1:9", "sb_secret_abc", lambda: snapshot(), timeout=1)
        self.assertFalse(pub.publish_once())
        self.assertIsNotNone(pub.last_error)

    def test_snapshot_exception_is_recorded_not_raised(self):
        def broken():
            raise RuntimeError("boom")
        pub = CloudPublisher(self.fake.url, "sb_secret_abc", broken)
        self.assertFalse(pub.publish_once())
        self.assertIn("boom", pub.last_error)

    def test_from_env_requires_url_and_key(self):
        saved = {k: os.environ.pop(k, None) for k in ("SUPABASE_URL", "SUPABASE_SECRET_KEY")}
        try:
            self.assertIsNone(CloudPublisher.from_env(lambda: None))
            os.environ["SUPABASE_URL"] = self.fake.url
            self.assertIsNone(CloudPublisher.from_env(lambda: None))
            os.environ["SUPABASE_SECRET_KEY"] = "sb_secret_abc"
            self.assertIsNotNone(CloudPublisher.from_env(lambda: None))
        finally:
            for k, v in saved.items():
                os.environ.pop(k, None)
                if v is not None:
                    os.environ[k] = v


class TestHostingBuild(unittest.TestCase):

    def test_rejects_secret_keys(self):
        self.assertTrue(hosting_build.check_public_key("sb_secret_abc"))
        self.assertTrue(hosting_build.check_public_key(fake_jwt("service_role")))
        self.assertTrue(hosting_build.check_public_key(""))

    def test_accepts_public_keys(self):
        self.assertEqual(hosting_build.check_public_key("sb_publishable_abc"), "")
        self.assertEqual(hosting_build.check_public_key(fake_jwt("anon")), "")

    def test_build_writes_cloud_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = hosting_build.OUT
            hosting_build.OUT = Path(tmp) / "public"
            try:
                out = hosting_build.build("https://demo.supabase.co/", "sb_publishable_abc")
            finally:
                hosting_build.OUT = original

            self.assertTrue((out / "index.html").is_file())
            self.assertTrue((out / "static" / "app.js").is_file())
            self.assertTrue((out / "static" / "style.css").is_file())
            config = (out / "static" / "config.js").read_text(encoding="utf-8")
            self.assertIn('"mode": "cloud"', config)
            self.assertIn('"supabaseUrl": "https://demo.supabase.co"', config)
            self.assertIn("sb_publishable_abc", config)

    def test_build_refuses_secret_key_and_http(self):
        with self.assertRaises(ValueError):
            hosting_build.build("https://demo.supabase.co", "sb_secret_abc")
        with self.assertRaises(ValueError):
            hosting_build.build("http://demo.supabase.co", "sb_publishable_abc")


if __name__ == "__main__":
    unittest.main()
