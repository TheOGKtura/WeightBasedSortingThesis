import json
import os
from dataclasses import dataclass, asdict

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QLineEdit,
    QDoubleSpinBox,
    QStackedWidget,
)

from hx711_module import get_current_reference_unit


@dataclass
class ProductProfile:
    name: str
    target_weight_g: float
    tolerance_g: float


class CalibrationPage(QWidget):
    back_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("page_calibration")

        self._profiles: list[ProductProfile] = []
        self._card_widgets: list[QWidget] = []
        self._live_weight = 0.0
        self._reference_unit_provider = None
        self._reference_unit_applier = None
        self._suggested_reference_unit = None
        self._admin_mode = True

        self._profiles_path = os.path.join(
            os.path.dirname(__file__),
            "calibration_profiles.json",
        )

        self._build_ui()
        self._load_profiles()
        self._refresh_cards()

    def set_reference_unit_provider(self, provider):
        self._reference_unit_provider = provider

    def set_reference_unit_applier(self, applier):
        self._reference_unit_applier = applier

    def set_admin_mode(self, is_admin: bool):
        self._admin_mode = bool(is_admin)

        self.name_input.setEnabled(self._admin_mode)
        self.target_input.setEnabled(self._admin_mode)
        self.tolerance_input.setEnabled(self._admin_mode)
        self.add_card_button.setEnabled(self._admin_mode)
        self.capture_target_button.setEnabled(self._admin_mode)
        self.delete_button.setEnabled(self._admin_mode)
        self.suggest_button.setEnabled(self._admin_mode)
        self.apply_button.setEnabled(self._admin_mode and self._suggested_reference_unit is not None)

        if not self._admin_mode:
            self.suggestion_label.setText("Suggested reference unit: admin only")

    def get_profile_names(self) -> list[str]:
        return [p.name for p in self._profiles]

    def select_profile_by_name(self, name: str) -> bool:
        idx = self._find_profile_by_name(name)
        if idx is None:
            return False
        if self.carousel.count() > 0:
            self.carousel.setCurrentIndex(idx)
        return True

    def get_current_profile_name(self) -> str | None:
        profile = self._current_profile()
        return None if profile is None else profile.name

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("HX711 Calibration")
        title.setObjectName("calibrationTitle")
        subtitle = QLabel("Create product cards and compare target vs live weight")
        subtitle.setObjectName("calibrationSubtitle")

        title_col = QVBoxLayout()
        title_col.addWidget(title)
        title_col.addWidget(subtitle)

        self.back_button = QPushButton("Back")
        self.back_button.setObjectName("calibrationBackButton")
        self.back_button.clicked.connect(self.back_requested.emit)

        header.addLayout(title_col)
        header.addStretch()
        header.addWidget(self.back_button)
        root.addLayout(header)

        metrics_row = QHBoxLayout()

        self.live_weight_label = QLabel("Live: 0.0 g")
        self.live_weight_label.setObjectName("metricChip")
        self.target_weight_label = QLabel("Target: -")
        self.target_weight_label.setObjectName("metricChip")
        self.error_label = QLabel("Error: -")
        self.error_label.setObjectName("metricChip")

        metrics_row.addWidget(self.live_weight_label)
        metrics_row.addWidget(self.target_weight_label)
        metrics_row.addWidget(self.error_label)
        root.addLayout(metrics_row)

        form_card = QFrame()
        form_card.setObjectName("calibrationFormCard")
        form_layout = QHBoxLayout(form_card)
        form_layout.setContentsMargins(12, 10, 12, 10)
        form_layout.setSpacing(10)

        self.name_input = QLineEdit()
        self.name_input.setObjectName("calibrationInput")
        self.name_input.setPlaceholderText("Product name")

        self.target_input = QDoubleSpinBox()
        self.target_input.setObjectName("calibrationInput")
        self.target_input.setRange(1.0, 10000.0)
        self.target_input.setDecimals(1)
        self.target_input.setSingleStep(1.0)
        self.target_input.setSuffix(" g")

        self.tolerance_input = QDoubleSpinBox()
        self.tolerance_input.setObjectName("calibrationInput")
        self.tolerance_input.setRange(0.1, 1000.0)
        self.tolerance_input.setDecimals(1)
        self.tolerance_input.setSingleStep(0.5)
        self.tolerance_input.setValue(5.0)
        self.tolerance_input.setSuffix(" g")

        self.add_card_button = QPushButton("Save Card")
        self.add_card_button.setObjectName("calibrationPrimaryButton")
        self.add_card_button.clicked.connect(self._add_or_update_profile)

        self.capture_target_button = QPushButton("Use Live as Target")
        self.capture_target_button.setObjectName("calibrationGhostButton")
        self.capture_target_button.clicked.connect(self._set_target_to_live)

        form_layout.addWidget(QLabel("Name"))
        form_layout.addWidget(self.name_input, 2)
        form_layout.addWidget(QLabel("Target"))
        form_layout.addWidget(self.target_input, 1)
        form_layout.addWidget(QLabel("Tolerance"))
        form_layout.addWidget(self.tolerance_input, 1)
        form_layout.addWidget(self.capture_target_button)
        form_layout.addWidget(self.add_card_button)

        root.addWidget(form_card)

        nav_row = QHBoxLayout()
        self.prev_button = QPushButton("Previous")
        self.prev_button.setObjectName("calibrationGhostButton")
        self.prev_button.clicked.connect(self._show_previous)

        self.next_button = QPushButton("Next")
        self.next_button.setObjectName("calibrationGhostButton")
        self.next_button.clicked.connect(self._show_next)

        self.index_label = QLabel("Card 0/0")
        self.index_label.setObjectName("carouselIndex")

        self.delete_button = QPushButton("Delete Card")
        self.delete_button.setObjectName("calibrationDangerButton")
        self.delete_button.clicked.connect(self._delete_current)

        nav_row.addWidget(self.prev_button)
        nav_row.addWidget(self.index_label)
        nav_row.addWidget(self.next_button)
        nav_row.addStretch()
        nav_row.addWidget(self.delete_button)
        root.addLayout(nav_row)

        self.carousel = QStackedWidget()
        self.carousel.setObjectName("carouselHost")
        self.carousel.currentChanged.connect(self._on_current_card_changed)
        root.addWidget(self.carousel, 1)

        calibration_row = QHBoxLayout()
        self.reference_label = QLabel(f"Current reference unit: {get_current_reference_unit():.6f}")
        self.reference_label.setObjectName("calibrationInfo")
        self.suggest_button = QPushButton("Suggest New Reference Unit")
        self.suggest_button.setObjectName("calibrationPrimaryButton")
        self.suggest_button.clicked.connect(self._suggest_reference_unit)
        self.apply_button = QPushButton("Apply Suggested Unit")
        self.apply_button.setObjectName("calibrationGhostButton")
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self._apply_suggested_reference_unit)
        self.suggestion_label = QLabel("Suggested reference unit: -")
        self.suggestion_label.setObjectName("calibrationInfo")

        calibration_row.addWidget(self.reference_label)
        calibration_row.addWidget(self.suggest_button)
        calibration_row.addWidget(self.apply_button)
        calibration_row.addWidget(self.suggestion_label)
        root.addLayout(calibration_row)

    def on_live_weight(self, weight: float):
        self._live_weight = float(weight)
        self.live_weight_label.setText(f"Live: {self._live_weight:.1f} g")
        self._refresh_error_chip()

    def _set_target_to_live(self):
        if self._live_weight > 0.0:
            self.target_input.setValue(self._live_weight)

    def _add_or_update_profile(self):
        name = self.name_input.text().strip()
        if not name:
            return

        profile = ProductProfile(
            name=name,
            target_weight_g=float(self.target_input.value()),
            tolerance_g=float(self.tolerance_input.value()),
        )

        idx = self._find_profile_by_name(name)
        if idx is None:
            self._profiles.append(profile)
            self._refresh_cards(select_index=len(self._profiles) - 1)
        else:
            self._profiles[idx] = profile
            self._refresh_cards(select_index=idx)

        self._save_profiles()

    def _find_profile_by_name(self, name: str):
        for i, p in enumerate(self._profiles):
            if p.name.lower() == name.lower():
                return i
        return None

    def _clear_cards(self):
        while self.carousel.count() > 0:
            w = self.carousel.widget(0)
            self.carousel.removeWidget(w)
            w.deleteLater()
        self._card_widgets = []

    def _refresh_cards(self, select_index: int | None = None):
        self._clear_cards()

        if not self._profiles:
            placeholder = QFrame()
            placeholder.setObjectName("productCard")
            layout = QVBoxLayout(placeholder)
            empty_title = QLabel("No cards yet")
            empty_title.setObjectName("cardTitle")
            msg = QLabel("Create a profile with product name and target weight.")
            msg.setObjectName("cardBody")
            msg.setWordWrap(True)
            layout.addWidget(empty_title)
            layout.addWidget(msg)
            layout.addStretch()
            self.carousel.addWidget(placeholder)
        else:
            for profile in self._profiles:
                self.carousel.addWidget(self._build_card(profile))

        if select_index is not None and self.carousel.count() > 0:
            self.carousel.setCurrentIndex(max(0, min(select_index, self.carousel.count() - 1)))

        self._update_index_label()
        self._on_current_card_changed(self.carousel.currentIndex())

    def _build_card(self, profile: ProductProfile) -> QWidget:
        card = QFrame()
        card.setObjectName("productCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        title = QLabel(profile.name)
        title.setObjectName("cardTitle")

        target = QLabel(f"Target: {profile.target_weight_g:.1f} g")
        target.setObjectName("cardBody")

        tol = QLabel(f"Tolerance: +/-{profile.tolerance_g:.1f} g")
        tol.setObjectName("cardBody")

        delta = self._live_weight - profile.target_weight_g
        verdict = "PASS" if abs(delta) <= profile.tolerance_g else "OUT"
        status = QLabel(f"Live delta: {delta:+.1f} g ({verdict})")
        status.setObjectName("cardLiveStatus")
        if verdict == "PASS":
            status.setStyleSheet("color: #2ecc71; font-size: 14px; font-weight: bold;")
        else:
            status.setStyleSheet("color: #e74c3c; font-size: 14px; font-weight: bold;")

        layout.addWidget(title)
        layout.addWidget(target)
        layout.addWidget(tol)
        layout.addWidget(status)
        layout.addStretch()
        return card

    def _show_previous(self):
        if self.carousel.count() <= 1:
            return
        idx = (self.carousel.currentIndex() - 1) % self.carousel.count()
        self.carousel.setCurrentIndex(idx)

    def _show_next(self):
        if self.carousel.count() <= 1:
            return
        idx = (self.carousel.currentIndex() + 1) % self.carousel.count()
        self.carousel.setCurrentIndex(idx)

    def _delete_current(self):
        idx = self.carousel.currentIndex()
        if not self._profiles:
            return
        if idx < 0 or idx >= len(self._profiles):
            return

        self._profiles.pop(idx)
        self._save_profiles()
        self._refresh_cards(select_index=max(0, idx - 1))

    def _on_current_card_changed(self, _index: int):
        self._update_index_label()

        profile = self._current_profile()
        if profile is None:
            self.target_weight_label.setText("Target: -")
            self.error_label.setText("Error: -")
            return

        self.name_input.setText(profile.name)
        self.target_input.setValue(profile.target_weight_g)
        self.tolerance_input.setValue(profile.tolerance_g)
        self._refresh_error_chip()

    def _current_profile(self):
        idx = self.carousel.currentIndex()
        if 0 <= idx < len(self._profiles):
            return self._profiles[idx]
        return None

    def _update_index_label(self):
        if not self._profiles:
            self.index_label.setText("Card 0/0")
            return
        self.index_label.setText(f"Card {self.carousel.currentIndex() + 1}/{len(self._profiles)}")

    def _refresh_error_chip(self):
        profile = self._current_profile()
        if profile is None:
            self.target_weight_label.setText("Target: -")
            self.error_label.setText("Error: -")
            return

        delta = self._live_weight - profile.target_weight_g
        verdict = "PASS" if abs(delta) <= profile.tolerance_g else "OUT"
        self.target_weight_label.setText(f"Target: {profile.target_weight_g:.1f} g")
        self.error_label.setText(f"Error: {delta:+.1f} g")

        card = self.carousel.currentWidget()
        if card is not None:
            status_label = card.findChild(QLabel, "cardLiveStatus")
            if status_label is not None:
                status_label.setText(f"Live delta: {delta:+.1f} g ({verdict})")
                if verdict == "PASS":
                    status_label.setStyleSheet("color: #2ecc71; font-size: 14px; font-weight: bold;")
                else:
                    status_label.setStyleSheet("color: #e74c3c; font-size: 14px; font-weight: bold;")

    def _suggest_reference_unit(self):
        if not self._admin_mode:
            self.suggestion_label.setText("Suggested reference unit: admin only")
            return

        profile = self._current_profile()
        known_weight_g = 0.0
        if profile is not None and profile.target_weight_g > 0.0:
            known_weight_g = float(profile.target_weight_g)
        elif self.target_input.value() > 0.0:
            known_weight_g = float(self.target_input.value())

        if known_weight_g <= 0.0:
            self._suggested_reference_unit = None
            self.apply_button.setEnabled(False)
            self.suggestion_label.setText("Suggested reference unit: -")
            return

        if self._reference_unit_provider is None:
            self._suggested_reference_unit = None
            self.apply_button.setEnabled(False)
            self.suggestion_label.setText("Suggested reference unit: provider not configured")
            return

        suggested = self._reference_unit_provider(known_weight_g)
        if suggested is None:
            self._suggested_reference_unit = None
            self.apply_button.setEnabled(False)
            self.suggestion_label.setText("Suggested reference unit: measurement failed")
            return

        self._suggested_reference_unit = float(suggested)
        self.apply_button.setEnabled(True)
        self.suggestion_label.setText(f"Suggested reference unit: {suggested:.6f}")

    def _apply_suggested_reference_unit(self):
        if not self._admin_mode:
            self.suggestion_label.setText("Suggested reference unit: admin only")
            return

        if self._suggested_reference_unit is None:
            return
        if self._reference_unit_applier is None:
            self.suggestion_label.setText("Suggested reference unit: applier not configured")
            return

        applied = self._reference_unit_applier(float(self._suggested_reference_unit))
        if applied is None:
            self.suggestion_label.setText("Suggested reference unit: apply failed")
            return

        self.reference_label.setText(f"Current reference unit: {float(applied):.6f}")
        self.suggestion_label.setText(f"Suggested reference unit: {float(applied):.6f} (applied)")

    def _save_profiles(self):
        try:
            payload = [asdict(p) for p in self._profiles]
            with open(self._profiles_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            print(f"[CALIBRATION] Failed saving profiles: {e}")

    def _load_profiles(self):
        if not os.path.exists(self._profiles_path):
            return
        try:
            with open(self._profiles_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            self._profiles = [
                ProductProfile(
                    name=item.get("name", "Product"),
                    target_weight_g=float(item.get("target_weight_g", 0.0)),
                    tolerance_g=float(item.get("tolerance_g", 5.0)),
                )
                for item in payload
                if isinstance(item, dict)
            ]
        except Exception as e:
            print(f"[CALIBRATION] Failed loading profiles: {e}")
            self._profiles = []
