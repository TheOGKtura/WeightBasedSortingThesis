"""
Application entry point.
Wires together: gui.py, login_page, camera, clock, hx711, ocr, and roles.
"""

import os
import sys

# ── Platform & Touch Configuration (must be before any Qt imports) ──
os.environ["QT_QPA_PLATFORM"] = "wayland"
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
os.environ["QT_SCALE_FACTOR"] = "1"

from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtCore import Qt, QTimer

from gui import Ui_MainWindow
from login_page import LoginPage
from roles import has_permission
from camera_module import CameraModule
from clock_module import ClockModule
from hx711_module import HX711Module
from relay_mqtt_controller import RelayMqttConfig, RelayMqttController, RelayCommandMapping
from firebase_rtdb_module import FirebaseRTDBClient


RELAY_MQTT_HOST = os.environ.get("RELAY_MQTT_HOST", "127.0.0.1")
RELAY_MQTT_PORT = int(os.environ.get("RELAY_MQTT_PORT", "1883"))
RELAY_RUN_SECONDS = float(os.environ.get("RELAY_RUN_SECONDS", "6"))
RELAY_PAYLOAD_RUN = os.environ.get("RELAY_PAYLOAD_RUN", "OFF")
RELAY_PAYLOAD_STOP = os.environ.get("RELAY_PAYLOAD_STOP", "ON")
RELAY_MQTT_CLIENT_ID = os.environ.get("RELAY_MQTT_CLIENT_ID", f"pyside6-relay-gui-{os.getpid()}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        # ── Enable touch input ──
        self.setAttribute(Qt.WA_AcceptTouchEvents, True)

        self.current_user = None
        self.current_role = None
        self._relay_cycle_active = False
        self._relay_connected = False
        self._relay_state = None
        self._relay_queue_ms = 0
        self._last_product_name = ""
        self._green_blinks_left = 0
        self._red_blinks_left = 0

        # ── Load QSS ──
        qss_path = os.path.join(os.path.dirname(__file__), "login_page.qss")
        with open(qss_path, "r") as f:
            self.setStyleSheet(f.read())

        # ── Insert login page at index 0 ──
        self.login_page = LoginPage()
        self.ui.stackedWidget.insertWidget(0, self.login_page)

        self.ui.stackedWidget.setCurrentIndex(0)

        # ── Modules ──
        self.camera = CameraModule(
            self.ui.frame_camera,
            ocr_callback=self.on_product_detected
        )
        self.clock = ClockModule(self.ui.label_uptime, self.ui.label_date)
        self.hx711 = HX711Module(
            self.ui.label_product_weight,
            self.ui.label_product_count
        )

        self.relay = RelayMqttController(
            RelayMqttConfig(
                host=RELAY_MQTT_HOST,
                port=RELAY_MQTT_PORT,
                client_id=RELAY_MQTT_CLIENT_ID,
            ),
            RelayCommandMapping(
                payload_run=RELAY_PAYLOAD_RUN,
                payload_stop=RELAY_PAYLOAD_STOP,
            ),
        )
        self.relay.start()

        self.firebase = FirebaseRTDBClient.from_env()
        self.firebase.set_state(
            "app_started",
            {
                "relay_mqtt_host": RELAY_MQTT_HOST,
                "relay_mqtt_port": RELAY_MQTT_PORT,
                "relay_mqtt_client_id": RELAY_MQTT_CLIENT_ID,
                "relay_payload_run": RELAY_PAYLOAD_RUN,
                "relay_payload_stop": RELAY_PAYLOAD_STOP,
            },
        )

        self._relay_stop_timer = QTimer(self)
        self._relay_stop_timer.setSingleShot(True)
        self._relay_stop_timer.timeout.connect(self._end_relay_cycle)

        self._green_blink_timer = QTimer(self)
        self._green_blink_timer.setInterval(140)
        self._green_blink_timer.timeout.connect(self._on_green_blink_tick)

        self._red_blink_timer = QTimer(self)
        self._red_blink_timer.setInterval(140)
        self._red_blink_timer.timeout.connect(self._on_red_blink_tick)

        self._telemetry_timer = QTimer(self)
        self._telemetry_timer.setInterval(30000)
        self._telemetry_timer.timeout.connect(self._publish_heartbeat)
        self._telemetry_timer.start()

        # Start the clock immediately
        self.clock.start()

        # ── Signals ──
        self.login_page.login_successful.connect(self.on_login_success)
        self.hx711.weight_qualified.connect(self.on_weight_captured)
        self.hx711.weight_finalized.connect(self.on_weight_finalized)
        self.relay.connected_changed.connect(self.on_relay_connected_changed)
        self.relay.status_changed.connect(self.on_relay_status_changed)
        self.relay.relay_state_changed.connect(self.on_relay_state_changed)

        # Navigation — Home button logs out and returns to login (index 0)
        self.ui.pushButton_home.clicked.connect(self.logout)

        # Start / Stop toggle
        self.ui.pushButton_start.clicked.connect(self.toggle_hx711)
        self.ui.pushButton_calibrate.setVisible(False)

    # ─────────────────────────────────────
    #  Login
    # ─────────────────────────────────────
    def on_login_success(self, username: str, role: str, permissions: dict):
        self.current_user = username
        self.current_role = role

        self.firebase.set_state(
            "user_logged_in",
            {
                "username": username,
                "role": role,
            },
        )

        self.ui.label_account.setText(f"  {username}  ({role})")
        self.ui.label_account.adjustSize()

        self.apply_permissions(permissions)
        self.camera.start()
        self.hx711.reset()
        self.hx711.start()
        self.ui.pushButton_start.setText("Stop")
        # Keep conveyor in safe OFF state until a qualified item triggers RUN.
        self._ensure_relay_on("login_success")
        self.ui.stackedWidget.setCurrentWidget(self.ui.page_main)

        self.firebase.push_event(
            "session_started",
            {
                "username": username,
                "role": role,
            },
        )

    def apply_permissions(self, permissions: dict):
        button_map = {
            "pushButton_start":     self.ui.pushButton_start,
            "pushButton_home":      self.ui.pushButton_home,
            "pushButton_calibrate": self.ui.pushButton_calibrate,
        }
        for key, button in button_map.items():
            allowed = permissions.get(key, False)
            button.setEnabled(allowed)
            button.setToolTip("" if allowed else "Permission denied")

    # ─────────────────────────────────────
    #  HX711 Start / Stop Toggle
    # ─────────────────────────────────────
    def toggle_hx711(self):
        if self.hx711.is_running:
            self.hx711.stop()
            self.ui.pushButton_start.setText("Start")
            self._ensure_relay_on("hx711_stopped")
            self.firebase.push_event("hx711_stopped", {"source": "ui_button"})
        else:
            self.hx711.start()
            self.ui.pushButton_start.setText("Stop")
            self.firebase.push_event("hx711_started", {"source": "ui_button"})

    # ─────────────────────────────────────
    #  OCR Product Detection
    # ─────────────────────────────────────
    def on_product_detected(self, product_name: str):
        """Called when OCR detects a product name from camera feed."""
        self.ui.label_product.setText(product_name)

        normalized = product_name.strip().lower()
        if normalized and normalized != self._last_product_name:
            self._last_product_name = normalized
            self.firebase.push_event(
                "product_detected",
                {
                    "product_name": product_name.strip(),
                    "username": self.current_user,
                    "role": self.current_role,
                },
            )

        print(f"\n  ╔═══════════════════════════════════════╗")
        print(f"  ║  PRODUCT → {product_name:<27} ║")
        print(f"  ╚═══════════════════════════════════════╝\n")

    def on_weight_finalized(self, weight: float):
        accepted = bool(self.hx711.is_weight_accepted(weight))
        self.firebase.push_event(
            "weight_finalized",
            {
                "weight_g": float(weight),
                "accepted": accepted,
                "username": self.current_user,
                "role": self.current_role,
            },
        )
        if not accepted:
            self._blink_red()

    # ─────────────────────────────────────
    #  Relay by Finalized Weight
    # ─────────────────────────────────────
    def on_weight_captured(self, weight: float):
        """Add relay runtime for each finalized qualified item."""
        is_calibration_mode = False
        product_name = self.ui.label_product.text().strip() or "Unknown"

        self.firebase.push_event(
            "weight_qualified",
            {
                "weight_g": float(weight),
                "product_name": product_name,
                "username": self.current_user,
                "role": self.current_role,
                "relay_connected": self._relay_connected,
                "relay_cycle_active": self._relay_cycle_active,
                "relay_queue_ms": self._relay_queue_ms,
                "is_calibration_mode": is_calibration_mode,
            },
        )

        if is_calibration_mode:
            print(f"[RELAY] Skipped RUN for {weight:.1f} g (calibration mode)")
            return

        # Accepted/qualified item indicator
        self._blink_green()

        if not self._relay_connected:
            # UI flag can be stale briefly during reconnect; still attempt RUN publish.
            print(
                f"[RELAY] MQTT UI flag disconnected for {weight:.1f} g; "
                "attempting RUN publish"
            )

        added_ms = int(RELAY_RUN_SECONDS * 1000)
        remaining_ms = max(0, self._relay_stop_timer.remainingTime()) if self._relay_cycle_active else 0
        self._relay_queue_ms = remaining_ms + added_ms

        # Publish RUN on every qualified event to avoid missed first-command issues.
        self.relay.run()
        if not self._relay_cycle_active:
            self._relay_cycle_active = True

        self._relay_stop_timer.start(self._relay_queue_ms)
        print(
            f"[RELAY] Qualified weight ({weight:.1f} g). "
            f"Added {RELAY_RUN_SECONDS:.1f}s, remaining {self._relay_queue_ms / 1000.0:.1f}s"
        )

    def _end_relay_cycle(self):
        self.relay.stop_power()
        self._relay_cycle_active = False
        self._relay_queue_ms = 0
        print("[RELAY] STOP (timer elapsed)")

    def on_relay_connected_changed(self, connected: bool):
        self._relay_connected = connected
        self.firebase.set_state("relay_connection_changed", {"relay_connected": connected})
        if connected:
            print(f"[MQTT] Connected to {RELAY_MQTT_HOST}:{RELAY_MQTT_PORT}")
        else:
            print("[MQTT] Disconnected")
        # Startup safety: force relay ON (cut power) when MQTT becomes available.
        # Do not interrupt an active timed relay cycle.
        if connected and not self._relay_cycle_active:
            self._ensure_relay_on("mqtt_connected")

    def on_relay_state_changed(self, payload: str):
        state = payload.strip().upper()
        if state:
            self._relay_state = state
        print(f"[RELAY_STATE] {payload}")

    def _ensure_relay_on(self, source: str):
        if not self._relay_connected:
            print(f"[RELAY] Cannot enforce ON from {source}: MQTT not connected")
            return
        if self._relay_state == "ON":
            print(f"[RELAY] Already ON ({source})")
            return
        self.relay.stop_power()
        print(f"[RELAY] Enforce ON ({source})")

    def on_relay_status_changed(self, status: str):
        self.firebase.push_event("relay_status", {"status": status})
        print(f"[RELAY] {status}")

    def _blink_green(self, blinks: int = 3):
        self._green_blinks_left = max(1, int(blinks)) * 2
        self.ui.frame_green_ind.setVisible(True)
        if self._green_blink_timer.isActive():
            self._green_blink_timer.stop()
        self._green_blink_timer.start()

    def _blink_red(self, blinks: int = 3):
        self._red_blinks_left = max(1, int(blinks)) * 2
        self.ui.frame_red_ind.setVisible(True)
        if self._red_blink_timer.isActive():
            self._red_blink_timer.stop()
        self._red_blink_timer.start()

    def _on_green_blink_tick(self):
        if self._green_blinks_left <= 0:
            self._green_blink_timer.stop()
            self.ui.frame_green_ind.setVisible(True)
            return
        self.ui.frame_green_ind.setVisible(not self.ui.frame_green_ind.isVisible())
        self._green_blinks_left -= 1
        if self._green_blinks_left <= 0:
            self._green_blink_timer.stop()
            self.ui.frame_green_ind.setVisible(True)

    def _on_red_blink_tick(self):
        if self._red_blinks_left <= 0:
            self._red_blink_timer.stop()
            self.ui.frame_red_ind.setVisible(True)
            return
        self.ui.frame_red_ind.setVisible(not self.ui.frame_red_ind.isVisible())
        self._red_blinks_left -= 1
        if self._red_blinks_left <= 0:
            self._red_blink_timer.stop()
            self.ui.frame_red_ind.setVisible(True)

    def _publish_heartbeat(self):
        self.firebase.set_state(
            "heartbeat",
            {
                "username": self.current_user,
                "role": self.current_role,
                "relay_connected": self._relay_connected,
                "relay_cycle_active": self._relay_cycle_active,
                "relay_queue_ms": self._relay_queue_ms,
                "current_product": self.ui.label_product.text().strip(),
            },
        )

    # ─────────────────────────────────────
    #  Logout — returns to login page
    # ─────────────────────────────────────
    def logout(self):
        if self.current_user is not None:
            self.firebase.push_event(
                "user_logout",
                {
                    "username": self.current_user,
                    "role": self.current_role,
                },
            )
        self.firebase.set_state("user_logged_out")

        self._relay_stop_timer.stop()
        self._ensure_relay_on("logout")
        self._relay_cycle_active = False
        self._relay_queue_ms = 0
        self.hx711.stop()
        self.camera.stop()
        self.current_user = None
        self.current_role = None
        self.ui.pushButton_start.setText("Start")
        self.ui.label_account.setText("Not logged in")
        self.ui.label_product.setText("No Product Detected")
        self.login_page.clear_fields()
        self.ui.stackedWidget.setCurrentIndex(0)

    # ─────────────────────────────────────
    #  Exit App — closes everything
    # ─────────────────────────────────────
    def exit_app(self):
        self.firebase.set_state("app_stopping")
        self._telemetry_timer.stop()
        self._relay_stop_timer.stop()
        self._ensure_relay_on("exit_app")
        self._relay_queue_ms = 0
        self.relay.stop()
        self.hx711.stop()
        self.camera.stop()
        self.clock.stop()
        QApplication.instance().quit()

    # ─────────────────────────────────────
    #  Cleanup on close
    # ─────────────────────────────────────
    def closeEvent(self, event):
        self.firebase.set_state("app_stopping")
        self._telemetry_timer.stop()
        self._relay_stop_timer.stop()
        self._ensure_relay_on("close_event")
        self._relay_queue_ms = 0
        self.relay.stop()
        self.hx711.stop()
        self.camera.stop()
        self.clock.stop()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # ── Touch Events ──
    app.setAttribute(Qt.AA_SynthesizeTouchForUnhandledMouseEvents, True)
    app.setAttribute(Qt.AA_SynthesizeMouseForUnhandledTouchEvents, True)

    window = MainWindow()

    # ── Fullscreen — hides Raspberry Pi taskbar ──
    window.setWindowFlags(
        Qt.FramelessWindowHint |
        Qt.WindowStaysOnTopHint
    )
    window.showFullScreen()

    sys.exit(app.exec())

