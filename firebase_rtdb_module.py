"""
Firebase Realtime Database telemetry helper.

Defaults are chosen to work with this project out of the box:
- credentials file: ./creds.json
- database URL: wssthesis RTDB (asia-southeast1)

Override with environment variables when needed:
- FIREBASE_CRED_PATH
- FIREBASE_DB_URL
- FIREBASE_DEVICE_ID
- FIREBASE_APP_NAME
"""

from __future__ import annotations

import os
import socket
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


DEFAULT_DB_URL = "https://wssthesis-default-rtdb.asia-southeast1.firebasedatabase.app"
DEFAULT_CRED_NAME = "creds.json"


@dataclass(frozen=True)
class FirebaseConfig:
    db_url: str
    cred_path: str
    device_id: str
    app_name: str


class FirebaseRTDBClient:
    def __init__(self, cfg: FirebaseConfig):
        self.cfg = cfg
        self._db = None
        self._app = None
        self._enabled = False
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self._enabled and self._db is not None

    @classmethod
    def from_env(cls) -> "FirebaseRTDBClient":
        local_creds = os.path.join(os.path.dirname(__file__), DEFAULT_CRED_NAME)
        cfg = FirebaseConfig(
            db_url=(os.environ.get("FIREBASE_DB_URL", "").strip() or DEFAULT_DB_URL),
            cred_path=(os.environ.get("FIREBASE_CRED_PATH", "").strip() or local_creds),
            device_id=(os.environ.get("FIREBASE_DEVICE_ID", "").strip() or socket.gethostname()),
            app_name=(os.environ.get("FIREBASE_APP_NAME", "").strip() or "wssthesis-pi-app"),
        )
        client = cls(cfg)
        client.initialize()
        return client

    def initialize(self) -> bool:
        if not os.path.isfile(self.cfg.cred_path):
            print(f"[FIREBASE] Disabled: credentials not found at {self.cfg.cred_path}")
            return False

        try:
            import firebase_admin
            from firebase_admin import credentials, db
        except Exception as e:
            print(f"[FIREBASE] Disabled: firebase-admin unavailable: {e}")
            return False

        try:
            with self._lock:
                app = None
                try:
                    app = firebase_admin.get_app(self.cfg.app_name)
                except ValueError:
                    cred = credentials.Certificate(self.cfg.cred_path)
                    app = firebase_admin.initialize_app(
                        cred,
                        {"databaseURL": self.cfg.db_url},
                        name=self.cfg.app_name,
                    )

                self._db = db
                self._app = app
                self._enabled = app is not None

            if self._enabled:
                print(
                    f"[FIREBASE] Connected: {self.cfg.db_url} "
                    f"(device={self.cfg.device_id})"
                )
            return self._enabled
        except Exception as e:
            print(f"[FIREBASE] Initialization failed: {e}")
            self._db = None
            self._app = None
            self._enabled = False
            return False

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _device_ref(self, suffix: str = ""):
        if not self.enabled:
            return None
        root = f"/devices/{self.cfg.device_id}"
        path = f"{root}/{suffix.lstrip('/')}" if suffix else root
        return self._db.reference(path, app=self._app)

    def _dispatch_async(self, func, *args, **kwargs) -> None:
        t = threading.Thread(target=func, args=args, kwargs=kwargs, daemon=True)
        t.start()

    def set_state(self, state: str, extra: dict[str, Any] | None = None) -> None:
        if not self.enabled:
            return

        payload: dict[str, Any] = {
            "state": state,
            "updated_at": self._now_iso(),
        }
        if extra:
            payload.update(extra)

        def _write_status() -> None:
            try:
                ref = self._device_ref("status")
                if ref is not None:
                    ref.update(payload)
            except Exception as e:
                print(f"[FIREBASE] Status write failed: {e}")

        self._dispatch_async(_write_status)

    def push_event(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        if not self.enabled:
            return

        payload: dict[str, Any] = {
            "event_type": event_type,
            "created_at": self._now_iso(),
        }
        if data:
            payload.update(data)

        def _write_event() -> None:
            try:
                ref = self._device_ref("events")
                if ref is not None:
                    ref.push(payload)
            except Exception as e:
                print(f"[FIREBASE] Event write failed ({event_type}): {e}")

        self._dispatch_async(_write_event)