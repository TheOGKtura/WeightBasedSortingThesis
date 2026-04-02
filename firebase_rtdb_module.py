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
        self._legacy_writes_enabled = os.environ.get("FIREBASE_LEGACY_WRITES", "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

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

    def _next_sequence(self, counter_path: str) -> int:
        """Return next 1-based sequence number stored under the device node."""
        ref = self._device_ref(counter_path)
        if ref is None:
            return 1

        def _txn(current):
            try:
                value = int(current)
            except (TypeError, ValueError):
                value = 0
            return value + 1

        result = ref.transaction(_txn)
        try:
            return max(1, int(result))
        except (TypeError, ValueError):
            return 1

    def set_state(self, state: str, extra: dict[str, Any] | None = None) -> None:
        if not self._legacy_writes_enabled:
            return
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

    def push_shift(self, production_shift: str, production_line: int, *, at_time: int | None = None) -> None:
        """
        Push a shift item with numeric keys under /devices/<device_id>/shifts/<n>.

        Shape:
            {
              "production_shift": "morning",
              "production_line": 0,
              "time": 12341234
            }
        """
        if not self.enabled:
            return

        payload: dict[str, Any] = {
            "production_shift": str(production_shift or "").strip() or "morning",
            "production_line": int(production_line),
            "time": int(at_time if at_time is not None else datetime.now().timestamp()),
        }

        def _write_shift() -> None:
            try:
                next_id = self._next_sequence("meta/shifts_seq")
                ref = self._device_ref(f"shifts/{next_id}")
                if ref is not None:
                    ref.set(payload)
            except Exception as e:
                print(f"[FIREBASE] Shift write failed: {e}")

        self._dispatch_async(_write_shift)

    def push_event(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        if not self._legacy_writes_enabled:
            return
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

    def push_record(self, data: dict[str, Any]) -> None:
        """
        Push a record item with numeric keys under /devices/<device_id>/records/<n>.

        Expected shape:
            {
              "product_name": "...",
              "standard": 225,
              "reading": 228,
              "production_shift": "morning",
              "production_line": 0,
              "operator": "mario",
              "time": 12341234,
              "accepted": true
            }
        """
        if not self.enabled:
            return

        payload: dict[str, Any] = dict(data or {})
        payload["time"] = int(payload.get("time") or datetime.now().timestamp())

        def _write_record() -> None:
            try:
                next_id = self._next_sequence("meta/records_seq")
                ref = self._device_ref(f"records/{next_id}")
                if ref is not None:
                    ref.set(payload)
            except Exception as e:
                print(f"[FIREBASE] Record write failed: {e}")

        self._dispatch_async(_write_record)

    def get_daily_quota_count(self, username: str, date_key: str) -> int:
        """Return persisted qualified-item count for a user on a specific date (YYYY-MM-DD)."""
        if not self.enabled:
            return 0

        safe_user = str(username or "").strip()
        safe_date = str(date_key or "").strip()
        if not safe_user or not safe_date:
            return 0

        try:
            ref = self._device_ref(f"daily_quota/{safe_user}/{safe_date}/count")
            if ref is None:
                return 0
            value = ref.get()
            return int(value) if value is not None else 0
        except Exception as e:
            print(f"[FIREBASE] Daily quota read failed ({safe_user}/{safe_date}): {e}")
            return 0

    def increment_daily_quota_count(
        self,
        username: str,
        date_key: str,
        delta: int = 1,
        *,
        role: str | None = None,
        product_name: str | None = None,
        quota: int | None = None,
    ) -> int:
        """
        Atomically increment persisted daily qualified-item count.

        Returns the resulting count after increment.
        """
        if not self._legacy_writes_enabled:
            return 0
        if not self.enabled:
            return 0

        safe_user = str(username or "").strip()
        safe_date = str(date_key or "").strip()
        step = int(delta)
        if not safe_user or not safe_date or step == 0:
            return self.get_daily_quota_count(safe_user, safe_date)

        try:
            ref = self._device_ref(f"daily_quota/{safe_user}/{safe_date}")
            if ref is None:
                return 0

            now_iso = self._now_iso()

            def _txn(current):
                payload = current if isinstance(current, dict) else {}
                previous = payload.get("count", 0)
                try:
                    current_count = int(previous)
                except (TypeError, ValueError):
                    current_count = 0

                new_count = max(0, current_count + step)
                payload.update(
                    {
                        "count": new_count,
                        "username": safe_user,
                        "date": safe_date,
                        "updated_at": now_iso,
                    }
                )
                if "created_at" not in payload:
                    payload["created_at"] = now_iso
                if role is not None:
                    payload["role"] = role
                if product_name is not None:
                    payload["product_name"] = product_name
                if quota is not None:
                    payload["quota"] = int(quota)
                return payload

            result = ref.transaction(_txn)
            if isinstance(result, dict):
                return int(result.get("count", 0))
            return self.get_daily_quota_count(safe_user, safe_date)
        except Exception as e:
            print(f"[FIREBASE] Daily quota increment failed ({safe_user}/{safe_date}): {e}")
            return self.get_daily_quota_count(safe_user, safe_date)

    def increment_operator_finalized_tally(
        self,
        username: str,
        date_key: str,
        accepted: bool,
        *,
        role: str | None = None,
        product_name: str | None = None,
        weight_g: float | None = None,
    ) -> dict[str, Any]:
        """
        Atomically update per-operator finalized-result tallies for a date.

        Path:
            /devices/<device_id>/operator_performance/<YYYY-MM-DD>/<username>
        """
        if not self._legacy_writes_enabled:
            return {
                "accepted_count": 1 if accepted else 0,
                "rejected_count": 0 if accepted else 1,
                "total_finalized": 1,
            }
        if not self.enabled:
            return {
                "accepted_count": 1 if accepted else 0,
                "rejected_count": 0 if accepted else 1,
                "total_finalized": 1,
            }

        safe_user = str(username or "").strip()
        safe_date = str(date_key or "").strip()
        if not safe_user or not safe_date:
            return {}

        try:
            ref = self._device_ref(f"operator_performance/{safe_date}/{safe_user}")
            if ref is None:
                return {}

            now_iso = self._now_iso()
            is_accepted = bool(accepted)

            def _txn(current):
                payload = current if isinstance(current, dict) else {}

                prev_acc = payload.get("accepted_count", 0)
                prev_rej = payload.get("rejected_count", 0)
                prev_tot = payload.get("total_finalized", 0)

                try:
                    acc_count = int(prev_acc)
                except (TypeError, ValueError):
                    acc_count = 0
                try:
                    rej_count = int(prev_rej)
                except (TypeError, ValueError):
                    rej_count = 0
                try:
                    total_count = int(prev_tot)
                except (TypeError, ValueError):
                    total_count = 0

                if is_accepted:
                    acc_count += 1
                else:
                    rej_count += 1
                total_count += 1

                payload.update(
                    {
                        "username": safe_user,
                        "date": safe_date,
                        "accepted_count": acc_count,
                        "rejected_count": rej_count,
                        "total_finalized": total_count,
                        "last_result": "accepted" if is_accepted else "rejected",
                        "updated_at": now_iso,
                    }
                )
                if "created_at" not in payload:
                    payload["created_at"] = now_iso
                if role is not None:
                    payload["role"] = role
                if product_name is not None:
                    payload["last_product_name"] = product_name
                if weight_g is not None:
                    try:
                        payload["last_weight_g"] = float(weight_g)
                    except (TypeError, ValueError):
                        pass
                return payload

            result = ref.transaction(_txn)
            return result if isinstance(result, dict) else {}
        except Exception as e:
            print(f"[FIREBASE] Operator tally increment failed ({safe_user}/{safe_date}): {e}")
            return {}

    def push_operator_finalized_log(
        self,
        username: str,
        date_key: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """
        Push per-item finalized logs for an operator/date.

        Path:
            /devices/<device_id>/operator_logs/<YYYY-MM-DD>/<username>
        """
        if not self._legacy_writes_enabled:
            return
        if not self.enabled:
            return

        safe_user = str(username or "").strip()
        safe_date = str(date_key or "").strip()
        if not safe_user or not safe_date:
            return

        payload: dict[str, Any] = {
            "created_at": self._now_iso(),
            "username": safe_user,
            "date": safe_date,
        }
        if data:
            payload.update(data)

        def _write_log() -> None:
            try:
                ref = self._device_ref(f"operator_logs/{safe_date}/{safe_user}")
                if ref is not None:
                    ref.push(payload)
            except Exception as e:
                print(f"[FIREBASE] Operator finalized log write failed ({safe_user}/{safe_date}): {e}")

        self._dispatch_async(_write_log)