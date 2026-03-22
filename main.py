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
from PySide6.QtCore import Qt

from gui import Ui_MainWindow
from login_page import LoginPage
from roles import has_permission
from camera_module import CameraModule
from clock_module import ClockModule
from hx711_module import HX711Module


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        # ── Enable touch input ──
        self.setAttribute(Qt.WA_AcceptTouchEvents, True)

        self.current_user = None
        self.current_role = None

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

        # Start the clock immediately
        self.clock.start()

        # ── Signals ──
        self.login_page.login_successful.connect(self.on_login_success)

        # Navigation — Home button logs out and returns to login (index 0)
        self.ui.pushButton_home.clicked.connect(self.logout)

        # Start / Stop toggle
        self.ui.pushButton_start.clicked.connect(self.toggle_hx711)

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
    #  Logout — returns to login page
    # ─────────────────────────────────────
    def logout(self):
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
        self.hx711.stop()
        self.camera.stop()
        self.clock.stop()
        QApplication.instance().quit()

    # ─────────────────────────────────────
    #  Cleanup on close
    # ─────────────────────────────────────
    def closeEvent(self, event):
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

