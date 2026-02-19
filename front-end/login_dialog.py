from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel,
    QComboBox, QLineEdit, QPushButton
)
from PySide6.QtCore import Qt
from pathlib import Path
from roles import ROLES


class LoginDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Login")
        self.setFixedSize(800, 480)
        self.setWindowFlags(Qt.FramelessWindowHint)

        self.role = None  # returned to main.p
        
        qss_path = Path(__file__).parent / "qss/login.qss"
        self.setStyleSheet(qss_path.read_text())
        
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(20)

        title = QLabel("Welcome!")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 32px; font-weight: bold;")

        self.combo_role = QComboBox()
        self.combo_role.addItems(
            [data["label"] for data in ROLES.values()]
        )
        self.combo_role.setFixedHeight(50)
        self.combo_role.setFixedWidth(480)

        self.pin_input = QLineEdit()
        self.pin_input.setPlaceholderText("Enter PIN")
        self.pin_input.setEchoMode(QLineEdit.Password)
        self.pin_input.setInputMethodHints(Qt.ImhDigitsOnly)
        self.pin_input.setMaxLength(6)
        self.pin_input.setFixedHeight(50)
        self.pin_input.setFixedWidth(480)

        self.label_error = QLabel("")
        self.label_error.setObjectName("errorLabel")
        self.label_error.setAlignment(Qt.AlignCenter)
     
        btn_login = QPushButton("LOGIN")
        btn_login.setFixedHeight(60)
        btn_login.setFixedWidth(480)
        btn_login.clicked.connect(self.validate_login)

        layout.addWidget(title)
        layout.addWidget(self.combo_role)
        layout.addWidget(self.pin_input)
        layout.addWidget(btn_login)
        layout.addWidget(self.label_error)

    def validate_login(self):
        selected_label = self.combo_role.currentText()
        entered_pin = self.pin_input.text()

        for role_key, role_data in ROLES.items():
            if role_data["label"] == selected_label:
                if role_data["pin"] == entered_pin:
                    self.role = role_key 
                    self.accept()
                    return

        self.label_error.setText("Invalid PIN")
        self.pin_input.clear()

