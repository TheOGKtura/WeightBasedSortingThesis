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
from calibration_page import CalibrationPage
from relay_mqtt_controller import RelayMqttConfig, RelayMqttController


RELAY_MQTT_HOST = os.environ.get("RELAY_MQTT_HOST", "127.0.0.1")
RELAY_MQTT_PORT = int(os.environ.get("RELAY_MQTT_PORT", "1883"))
RELAY_RUN_SECONDS = float(os.environ.get("RELAY_RUN_SECONDS", "11"))


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

        # ── Load QSS ──
        qss_path = os.path.join(os.path.dirname(__file__), "login_page.qss")
        with open(qss_path, "r") as f:
            self.setStyleSheet(f.read())

        # ── Insert login page at index 0 ──
        self.login_page = LoginPage()
        self.ui.stackedWidget.insertWidget(0, self.login_page)

        # ── Insert calibration page at index 1 ──
        self.calibration_page = CalibrationPage()
        self.ui.stackedWidget.insertWidget(1, self.calibration_page)
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
            )
        )
        self.relay.start()

        self._relay_stop_timer = QTimer(self)
        self._relay_stop_timer.setSingleShot(True)
        self._relay_stop_timer.timeout.connect(self._end_relay_cycle)

        # Start the clock immediately
        self.clock.start()

        # ── Signals ──
        self.login_page.login_successful.connect(self.on_login_success)
        self.hx711.weight_finalized.connect(self.on_weight_captured)
        self.hx711.weight_display_ready.connect(self.calibration_page.on_live_weight)
        self.relay.connected_changed.connect(self.on_relay_connected_changed)
        self.relay.status_changed.connect(self.on_relay_status_changed)
        self.calibration_page.back_requested.connect(self.go_to_main_page)

        # Navigation — Home button logs out and returns to login (index 0)
        self.ui.pushButton_home.clicked.connect(self.logout)

        # Start / Stop toggle
        self.ui.pushButton_start.clicked.connect(self.toggle_hx711)
        self.ui.pushButton_calibrate.clicked.connect(self.open_calibration)

    # ─────────────────────────────────────
    #  Login
    # ─────────────────────────────────────
    def on_login_success(self, username: str, role: str, permissions: dict):
        self.current_user = username
        self.current_role = role

        self.ui.label_account.setText(f"  {username}  ({role})")
        self.ui.label_account.adjustSize()

        self.apply_permissions(permissions)
        self.camera.start()
        self.hx711.reset()
        self.ui.pushButton_start.setText("Start")
        self.ui.stackedWidget.setCurrentWidget(self.ui.page_main)

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
        else:
            self.hx711.start()
            self.ui.pushButton_start.setText("Stop")

    # ─────────────────────────────────────
    #  OCR Product Detection
    # ─────────────────────────────────────
    def on_product_detected(self, product_name: str):
        """Called when OCR detects a product name from camera feed."""
        self.ui.label_product.setText(product_name)
        print(f"\n  ╔═══════════════════════════════════════╗")
        print(f"  ║  PRODUCT → {product_name:<27} ║")
        print(f"  ╚═══════════════════════════════════════╝\n")

    # ─────────────────────────────────────
    #  Calibration Navigation
    # ─────────────────────────────────────
    def open_calibration(self):
        if not self.hx711.is_running:
            self.hx711.start()
            self.ui.pushButton_start.setText("Stop")
        self.ui.stackedWidget.setCurrentWidget(self.calibration_page)

    def go_to_main_page(self):
        self.ui.stackedWidget.setCurrentWidget(self.ui.page_main)

    # ─────────────────────────────────────
    #  Relay by Finalized Weight
    # ─────────────────────────────────────
    def on_weight_captured(self, weight: float):
        """Run conveyor for a fixed window after stable weight capture."""
        if self.ui.stackedWidget.currentWidget() is self.calibration_page:
            print(f"[RELAY] Skipped RUN for {weight:.1f} g (calibration mode)")
            return

        if self._relay_cycle_active:
            return
        if not self._relay_connected:
            print(f"[RELAY] Skipped RUN for {weight:.1f} g (MQTT not connected)")
            return

        self._relay_cycle_active = True
        self.relay.run()
        self._relay_stop_timer.start(int(RELAY_RUN_SECONDS * 1000))
        print(f"[RELAY] Weight captured ({weight:.1f} g). RUN for {RELAY_RUN_SECONDS:.1f}s")

    def _end_relay_cycle(self):
        self.relay.stop_power()
        self._relay_cycle_active = False
        print("[RELAY] STOP (timer elapsed)")

    def on_relay_connected_changed(self, connected: bool):
        self._relay_connected = connected
        # Keep conveyor off by default whenever MQTT becomes available.
        if connected:
            self.relay.stop_power()

    def on_relay_status_changed(self, status: str):
        print(f"[RELAY] {status}")

    # ─────────────────────────────────────
    #  Logout — returns to login page
    # ─────────────────────────────────────
    def logout(self):
        self._relay_stop_timer.stop()
        self.relay.stop_power()
        self._relay_cycle_active = False
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
        self._relay_stop_timer.stop()
        self.relay.stop_power()
        self.relay.stop()
        self.hx711.stop()
        self.camera.stop()
        self.clock.stop()
        QApplication.instance().quit()

    # ─────────────────────────────────────
    #  Cleanup on close
    # ─────────────────────────────────────
    def closeEvent(self, event):
        self._relay_stop_timer.stop()
        self.relay.stop_power()
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

