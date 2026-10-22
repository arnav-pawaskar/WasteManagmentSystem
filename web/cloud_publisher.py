"""
Cloud publisher: pushes a snapshot of the running simulation to Supabase.

This is the fog -> cloud link. The simulation (edge bins + fog nodes) runs on the
local machine; every few seconds the latest state is upserted into a single row of
the Supabase `snapshots` table, which the public dashboard on Firebase Hosting
reads. Standard library only, so the core system keeps no extra dependencies.

Configuration (environment or .env):
  SUPABASE_URL            https://<project-ref>.supabase.co
  SUPABASE_SECRET_KEY     secret / service_role key - stays on this machine only
  CLOUD_PUBLISH_INTERVAL  seconds between snapshots (default 3)
"""

import json
import os
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Callable, Optional

SNAPSHOT_ID = "live"
TABLE = "snapshots"


def normalize_supabase_url(url: str) -> str:
    """Accept the project URL with or without the Data API suffix (/rest/v1)."""
    url = url.strip().rstrip("/")
    if url.endswith("/rest/v1"):
        url = url[: -len("/rest/v1")]
    return url


def _auth_headers(key: str) -> dict:
    headers = {"apikey": key}
    # Legacy Supabase keys are JWTs and also go in Authorization. The newer
    # sb_secret_/sb_publishable_ keys are not JWTs and must only use `apikey`.
    if key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {key}"
    return headers


class CloudPublisher:
    """Background thread that upserts the latest snapshot every `interval` seconds."""

    def __init__(self, url: str, key: str, get_payload: Callable[[], Optional[dict]],
                 interval: float = 3.0, timeout: float = 5.0):
        self.endpoint = f"{normalize_supabase_url(url)}/rest/v1/{TABLE}?on_conflict=id"
        self.key = key
        self.get_payload = get_payload
        self.interval = max(1.0, float(interval))
        self.timeout = timeout

        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_running: Optional[bool] = None
        self._last_error_logged: Optional[str] = None

        # Exposed through /health
        self.published = 0
        self.failures = 0
        self.last_ok: Optional[str] = None
        self.last_error: Optional[str] = None
        self.last_ms: Optional[float] = None

    @classmethod
    def from_env(cls, get_payload: Callable[[], Optional[dict]]) -> Optional["CloudPublisher"]:
        """Build a publisher from environment variables, or None if not configured."""
        url = os.environ.get("SUPABASE_URL", "").strip()
        key = os.environ.get("SUPABASE_SECRET_KEY", "").strip()
        if not url or not key:
            return None
        interval = float(os.environ.get("CLOUD_PUBLISH_INTERVAL", "3") or 3)
        return cls(url, key, get_payload, interval=interval)

    # -- lifecycle -----------------------------------------------------------

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="cloud-publisher", daemon=True)
        self._thread.start()
        print(f"Cloud publisher: sending snapshots every {self.interval:g}s to Supabase")

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.timeout + 1)

    def _loop(self):
        while not self._stop.is_set():
            self.publish_once()
            self._stop.wait(self.interval)

    # -- publishing ----------------------------------------------------------

    def publish_once(self) -> bool:
        """Publish one snapshot. Returns True if a snapshot was sent successfully."""
        try:
            payload = self.get_payload()
        except Exception as e:  # never let a snapshot error kill the thread
            self._record_error(f"snapshot failed: {e}")
            return False
        if payload is None:
            return False

        # While stopped, publish the stopped state once and then go quiet
        running = bool(payload.get("status", {}).get("running"))
        if not running and self._last_running is False:
            return False

        # Include the previous round trip so the dashboard can show fog -> cloud latency
        payload["cloud"] = {"sync_ms": self.last_ms, "interval_s": self.interval}
        body = json.dumps({"id": SNAPSHOT_ID, "payload": payload}, default=str).encode("utf-8")

        headers = _auth_headers(self.key)
        headers.update({
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        })
        request = urllib.request.Request(self.endpoint, data=body, method="POST", headers=headers)

        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                response.read()
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:200]
            self._record_error(f"HTTP {e.code}: {detail}")
            return False
        except Exception as e:
            self._record_error(f"{type(e).__name__}: {e}")
            return False

        self.last_ms = round((time.perf_counter() - started) * 1000, 1)
        self.last_ok = datetime.now(timezone.utc).isoformat()
        self.last_error = None
        self.published += 1
        self._last_running = running
        if self._last_error_logged:
            print("Cloud publisher: connection restored")
            self._last_error_logged = None
        return True

    def _record_error(self, message: str):
        self.failures += 1
        self.last_error = message
        # Log each distinct error once instead of every interval
        if message != self._last_error_logged:
            print(f"Cloud publisher: {message}")
            self._last_error_logged = message

    def get_status(self) -> dict:
        return {
            "enabled": True,
            "published": self.published,
            "failures": self.failures,
            "last_ok": self.last_ok,
            "last_error": self.last_error,
            "last_sync_ms": self.last_ms,
            "interval_s": self.interval,
        }
