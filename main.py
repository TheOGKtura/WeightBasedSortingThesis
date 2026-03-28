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

from PySide6.QtWidgets import QApplication, QMainWindow, QLabel, QInputDialog
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
RELAY_RUN_SECONDS = float(os.environ.get("RELAY_RUN_SECONDS", "2"))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        # ── Enable touch input ──
        self.setAttribute(Qt.WA_AcceptTouchEvents, True)

        self.current_user = None
        self.current_role = None
        self._selected_profile_name = None
        self._relay_cycle_active = False
        self._relay_connected = False
        self._relay_queue_ms = 0

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

        self.selected_card_label = QLabel(self.ui.frame_product_description)
        self.selected_card_label.setObjectName("label_selected_card")
        self.selected_card_label.setGeometry(20, 112, 220, 20)
        self.selected_card_label.setText("Card: -")

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
        self.hx711.weight_qualified.connect(self.on_weight_captured)
        self.hx711.weight_display_ready.connect(self.calibration_page.on_live_weight)
        self.calibration_page.set_reference_unit_provider(self.suggest_reference_unit)
        self.calibration_page.set_reference_unit_applier(self.apply_reference_unit)
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
        self.calibration_page.set_admin_mode(role == "admin")
        self.ui.pushButton_calibrate.setText("Calibrate" if role == "admin" else "Choose Card")

        self._selected_profile_name = self.calibration_page.get_current_profile_name()
        self._update_selected_card_label()
        self.camera.start()
        self.hx711.reset()
        self.hx711.start()
        self.ui.pushButton_start.setText("Stop")
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
        if self.current_role != "admin":
            self.select_profile_for_user()
            return

        if not self.hx711.is_running:
            self.hx711.start()
            self.ui.pushButton_start.setText("Stop")
        self.ui.stackedWidget.setCurrentWidget(self.calibration_page)

    def select_profile_for_user(self):
        names = self.calibration_page.get_profile_names()
        if not names:
            self.selected_card_label.setText("Card: no profiles")
            return

        current_idx = 0
        if self._selected_profile_name in names:
            current_idx = names.index(self._selected_profile_name)

        selected, ok = QInputDialog.getItem(
            self,
            "Select Product Card",
            "Choose existing card:",
            names,
            current_idx,
            False,
        )
        if not ok or not selected:
            return

        self._selected_profile_name = str(selected)
        self.calibration_page.select_profile_by_name(self._selected_profile_name)
        self._update_selected_card_label()

    def _update_selected_card_label(self):
        if self._selected_profile_name:
            self.selected_card_label.setText(f"Card: {self._selected_profile_name}")
        else:
            self.selected_card_label.setText("Card: -")

    def go_to_main_page(self):
        self.ui.stackedWidget.setCurrentWidget(self.ui.page_main)

    # ─────────────────────────────────────
    #  Relay by Finalized Weight
    # ─────────────────────────────────────
    def on_weight_captured(self, weight: float):
        """Add relay runtime for each finalized qualified item."""
        if self.ui.stackedWidget.currentWidget() is self.calibration_page:
            print(f"[RELAY] Skipped RUN for {weight:.1f} g (calibration mode)")
            return

        if not self._relay_connected:
            print(f"[RELAY] Skipped RUN for {weight:.1f} g (MQTT not connected)")
            return

        added_ms = int(RELAY_RUN_SECONDS * 1000)
        remaining_ms = max(0, self._relay_stop_timer.remainingTime()) if self._relay_cycle_active else 0
        self._relay_queue_ms = remaining_ms + added_ms

        if not self._relay_cycle_active:
            self.relay.run()
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

    def suggest_reference_unit(self, known_weight_g: float):
        try:
            return self.hx711.suggest_reference_unit_details_from_known_weight(known_weight_g)
        except Exception as e:
            print(f"[CALIBRATION] Reference suggestion failed: {e}")
            return None

    def apply_reference_unit(self, new_reference_unit: float) -> float | None:
        try:
            applied = self.hx711.apply_reference_unit(new_reference_unit)
            if applied is not None:
                print(f"[CALIBRATION] Applied reference unit: {applied:.6f}")
            return applied
        except Exception as e:
            print(f"[CALIBRATION] Apply reference unit failed: {e}")
            return None

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
        self._relay_queue_ms = 0
        self.hx711.stop()
        self.camera.stop()
        self.current_user = None
        self.current_role = None
        self._selected_profile_name = None
        self.ui.pushButton_start.setText("Start")
        self.ui.pushButton_calibrate.setText("Calibrate")
        self.ui.label_account.setText("Not logged in")
        self.ui.label_product.setText("No Product Detected")
        self._update_selected_card_label()
        self.login_page.clear_fields()
        self.ui.stackedWidget.setCurrentIndex(0)

    # ─────────────────────────────────────
    #  Exit App — closes everything
    # ─────────────────────────────────────
    def exit_app(self):
        self._relay_stop_timer.stop()
        self.relay.stop_power()
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
        self._relay_stop_timer.stop()
        self.relay.stop_power()
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

