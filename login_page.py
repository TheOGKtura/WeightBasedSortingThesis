import os
import subprocess
import signal

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFrame, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor

from roles import USERS, get_permissions


# ── Detect which on-screen keyboard is available ──
KEYBOARD_CMD = None
for cmd in ["squeekboard", "onboard", "matchbox-keyboard", "florence", "xvkbd"]:
    if os.popen(f"which {cmd}").read().strip():
        KEYBOARD_CMD = cmd
        break

if KEYBOARD_CMD:
    print(f"[KEYBOARD] Using: {KEYBOARD_CMD}")
else:
    print("[KEYBOARD] No on-screen keyboard found. Install one with:")
    print("           sudo apt install matchbox-keyboard")


class KeyboardManager:
    """Manages the on-screen keyboard process."""

    def __init__(self):
        self.process = None

    def show(self):
        if not KEYBOARD_CMD:
            return
        if self.process and self.process.poll() is None:
            return  # already running

        try:
            # Launch keyboard as a background process
            if KEYBOARD_CMD == "matchbox-keyboard":
                self.process = subprocess.Popen(
                    ["matchbox-keyboard"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            elif KEYBOARD_CMD == "onboard":
                self.process = subprocess.Popen(
                    ["onboard"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            elif KEYBOARD_CMD == "squeekboard":
                self.process = subprocess.Popen(
                    ["squeekboard"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            elif KEYBOARD_CMD == "florence":
                self.process = subprocess.Popen(
                    ["florence"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            elif KEYBOARD_CMD == "xvkbd":
                self.process = subprocess.Popen(
                    ["xvkbd"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
        except Exception as e:
            print(f"[KEYBOARD] Failed to open: {e}")

    def hide(self):
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except Exception:
                self.process.kill()
            self.process = None

    def cleanup(self):
        self.hide()
        # Kill any leftover keyboard processes
        if KEYBOARD_CMD:
            os.system(f"pkill -f {KEYBOARD_CMD} 2>/dev/null")


class FocusLineEdit(QLineEdit):
    """QLineEdit that emits signals on focus in/out for keyboard control."""

    focused = Signal()
    unfocused = Signal()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.focused.emit()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.unfocused.emit()


class LoginPage(QWidget):
    """
    Emits login_successful(username, role, permissions) on valid login.
    Connect this signal from main.py to swap to page_main.
    """
    login_successful = Signal(str, str, dict)  # username, role, permissions

    def __init__(self):
        super().__init__()
        self.setObjectName("loginPage")
        self.init_ui()

    def init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Left Panel (Branding) ──
        left_panel = QFrame()
        left_panel.setObjectName("leftPanel")
        left_panel.setFixedWidth(320)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setAlignment(Qt.AlignCenter)
        left_layout.setSpacing(12)

        app_icon_label = QLabel("🔒")
        app_icon_label.setFont(QFont("Segoe UI Emoji", 48))
        app_icon_label.setAlignment(Qt.AlignCenter)

        welcome_label = QLabel("Welcome Back")
        welcome_label.setObjectName("welcomeLabel")
        welcome_label.setAlignment(Qt.AlignCenter)

        subtitle_label = QLabel("Sign in to continue")
        subtitle_label.setObjectName("subtitleLabel")
        subtitle_label.setAlignment(Qt.AlignCenter)

        left_layout.addWidget(app_icon_label)
        left_layout.addWidget(welcome_label)
        left_layout.addWidget(subtitle_label)

        # ── Right Panel (Login Form) ──
        right_panel = QFrame()
        right_panel.setObjectName("rightPanel")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(50, 40, 50, 40)
        right_layout.setSpacing(16)
        right_layout.setAlignment(Qt.AlignCenter)

        form_title = QLabel("Sign In")
        form_title.setObjectName("formTitle")
        form_title.setAlignment(Qt.AlignLeft)

        username_label = QLabel("Username")
        username_label.setObjectName("fieldLabel")
        self.username_input = QLineEdit()
        self.username_input.setObjectName("inputField")
        self.username_input.setPlaceholderText("Enter your username")
        self.username_input.setMinimumHeight(48)

        password_label = QLabel("Password")
        password_label.setObjectName("fieldLabel")
        self.password_input = QLineEdit()
        self.password_input.setObjectName("inputField")
        self.password_input.setPlaceholderText("Enter your password")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setMinimumHeight(48)

        self.login_button = QPushButton("LOGIN")
        self.login_button.setObjectName("loginButton")
        self.login_button.setMinimumHeight(50)
        self.login_button.setCursor(Qt.PointingHandCursor)
        self.login_button.clicked.connect(self.handle_login)

        self.status_label = QLabel("")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setAlignment(Qt.AlignCenter)

        right_layout.addWidget(form_title)
        right_layout.addSpacing(8)
        right_layout.addWidget(username_label)
        right_layout.addWidget(self.username_input)
        right_layout.addSpacing(4)
        right_layout.addWidget(password_label)
        right_layout.addWidget(self.password_input)
        right_layout.addSpacing(8)
        right_layout.addWidget(self.login_button)
        right_layout.addWidget(self.status_label)

        # Button shadow
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(52, 152, 219, 120))
        shadow.setOffset(0, 4)
        self.login_button.setGraphicsEffect(shadow)

        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel)

        # Keyboard navigation
        self.username_input.returnPressed.connect(self.password_input.setFocus)
        self.password_input.returnPressed.connect(self.handle_login)

    def handle_login(self):
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()

        if not username or not password:
            self.status_label.setStyleSheet("color: #e74c3c;")
            self.status_label.setText("⚠ Please fill in all fields.")
            return

        user = USERS.get(username)

        if user and user["password"] == password:
            role = user["role"]
            permissions = get_permissions(role)
            self.status_label.setStyleSheet("color: #27ae60;")
            self.status_label.setText(f"✓ Logged in as '{role}'")
            self.login_successful.emit(username, role, permissions)
        else:
            self.status_label.setStyleSheet("color: #e74c3c;")
            self.status_label.setText("✗ Invalid username or password.")

    def clear_fields(self):
        """Reset inputs and status when returning to login screen."""
        self.username_input.clear()
        self.password_input.clear()
        self.status_label.clear()
        self.username_input.setFocus()
