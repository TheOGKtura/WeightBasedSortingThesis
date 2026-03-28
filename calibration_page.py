import time

from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QDoubleSpinBox,
)

from hx711_module import get_current_reference_unit


class CalibrationWorker(QThread):
    completed = Signal(dict)
    failed = Signal(str)

    def __init__(self, known_weight_g: float, provider, applier, parent=None):
        super().__init__(parent)
        self.known_weight_g = float(known_weight_g)
        self.provider = provider
        self.applier = applier

    def run(self):
        try:
            provider_result = self.provider(self.known_weight_g)
            if provider_result is None:
                self.failed.emit("Calibration status: measurement failed")
                return

            raw_counts = None
            used_samples = None
            if isinstance(provider_result, dict):
                measured_reference = provider_result.get("reference_unit")
                raw_counts = provider_result.get("raw_counts")
                used_samples = provider_result.get("samples")
            else:
                measured_reference = provider_result

            if measured_reference is None:
                self.failed.emit("Calibration status: measurement failed")
                return

            applied = self.applier(float(measured_reference))
            if applied is None:
                self.failed.emit("Calibration status: apply failed")
                return

            self.completed.emit(
                {
                    "known_weight_g": self.known_weight_g,
                    "applied": float(applied),
                    "raw_counts": raw_counts,
                    "samples": used_samples,
                }
            )
        except Exception as e:
            self.failed.emit(f"Calibration status: error ({e})")


class CalibrationPage(QWidget):
    back_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("page_calibration")

        self._live_weight = 0.0
        self._reference_unit_provider = None
        self._reference_unit_applier = None
        self._admin_mode = True
        self._last_live_ui_update = 0.0
        self._live_ui_interval_s = 0.20
        self._calibration_worker = None

        self._build_ui()

    # Compatibility methods kept for main window flow.
    def get_profile_names(self) -> list[str]:
        return []

    def select_profile_by_name(self, _name: str) -> bool:
        return False

    def get_current_profile_name(self) -> str | None:
        return None

    def set_reference_unit_provider(self, provider):
        self._reference_unit_provider = provider

    def set_reference_unit_applier(self, applier):
        self._reference_unit_applier = applier

    def set_admin_mode(self, is_admin: bool):
        self._admin_mode = bool(is_admin)
        self.known_weight_input.setEnabled(self._admin_mode)
        self.calibrate_button.setEnabled(self._admin_mode)

        if not self._admin_mode:
            self.calibration_status_label.setText("Calibration status: admin only")

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("HX711 Calibration")
        title.setObjectName("calibrationTitle")
        subtitle = QLabel("Use known weight to compute and apply reference unit")
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
        self.reference_label = QLabel(f"Current reference unit: {get_current_reference_unit():.6f}")
        self.reference_label.setObjectName("metricChip")

        metrics_row.addWidget(self.live_weight_label)
        metrics_row.addWidget(self.reference_label)
        metrics_row.addStretch()
        root.addLayout(metrics_row)

        calibration_card = QFrame()
        calibration_card.setObjectName("calibrationFormCard")
        calibration_layout = QHBoxLayout(calibration_card)
        calibration_layout.setContentsMargins(12, 10, 12, 10)
        calibration_layout.setSpacing(10)

        known_weight_label = QLabel("Known weight")

        self.known_weight_input = QDoubleSpinBox()
        self.known_weight_input.setObjectName("calibrationInput")
        self.known_weight_input.setRange(1.0, 10000.0)
        self.known_weight_input.setDecimals(1)
        self.known_weight_input.setSingleStep(1.0)
        self.known_weight_input.setSuffix(" g")
        self.known_weight_input.setValue(225.0)

        self.calibrate_button = QPushButton("Calibrate & Apply")
        self.calibrate_button.setObjectName("calibrationPrimaryButton")
        self.calibrate_button.clicked.connect(self._calibrate_reference_unit)

        self.calibration_status_label = QLabel("Calibration status: -")
        self.calibration_status_label.setObjectName("calibrationInfo")
        self.calibration_status_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)

        calibration_layout.addWidget(known_weight_label)
        calibration_layout.addWidget(self.known_weight_input)
        calibration_layout.addWidget(self.calibrate_button)
        calibration_layout.addWidget(self.calibration_status_label, 1)

        root.addWidget(calibration_card)
        root.addStretch()

    def on_live_weight(self, weight: float):
        self._live_weight = float(weight)

        if not self.isVisible():
            return

        now = time.monotonic()
        if now - self._last_live_ui_update < self._live_ui_interval_s:
            return
        self._last_live_ui_update = now

        self.live_weight_label.setText(f"Live: {self._live_weight:.1f} g")

    def _calibrate_reference_unit(self):
        if not self._admin_mode:
            self.calibration_status_label.setText("Calibration status: admin only")
            return

        known_weight_g = float(self.known_weight_input.value())
        if known_weight_g <= 0.0:
            self.calibration_status_label.setText("Calibration status: invalid known weight")
            return

        if self._reference_unit_provider is None:
            self.calibration_status_label.setText("Calibration status: provider not configured")
            return

        if self._reference_unit_applier is None:
            self.calibration_status_label.setText("Calibration status: applier not configured")
            return

        if self._calibration_worker is not None and self._calibration_worker.isRunning():
            self.calibration_status_label.setText("Calibration status: calibration already running")
            return

        self.calibrate_button.setEnabled(False)
        self.calibration_status_label.setText("Calibration status: calibrating...")

        self._calibration_worker = CalibrationWorker(
            known_weight_g=known_weight_g,
            provider=self._reference_unit_provider,
            applier=self._reference_unit_applier,
            parent=self,
        )
        self._calibration_worker.completed.connect(self._on_calibration_completed)
        self._calibration_worker.failed.connect(self._on_calibration_failed)
        self._calibration_worker.finished.connect(self._on_calibration_finished)
        self._calibration_worker.start()

    def _on_calibration_completed(self, data: dict):
        applied = float(data.get("applied", 0.0))
        known_weight_g = float(data.get("known_weight_g", 0.0))
        raw_counts = data.get("raw_counts")
        used_samples = data.get("samples")

        self.reference_label.setText(f"Current reference unit: {applied:.6f}")
        if raw_counts is not None and used_samples is not None:
            self.calibration_status_label.setText(
                "Calibration status: "
                f"raw={float(raw_counts):.1f}, n={int(used_samples)}, "
                f"applied={applied:.6f}"
            )
        else:
            self.calibration_status_label.setText(
                f"Calibration status: applied ({known_weight_g:.1f} g -> {applied:.6f})"
            )

    def _on_calibration_failed(self, message: str):
        self.calibration_status_label.setText(message)

    def _on_calibration_finished(self):
        self.calibrate_button.setEnabled(self._admin_mode)
