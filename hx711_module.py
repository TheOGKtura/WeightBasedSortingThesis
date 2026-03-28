"""
HX711 load-cell module (10 SPS) — CAPTURE (5s) -> FINALIZE -> HOLD until removed

Behavior:
- IDLE: emit live safe weight while waiting for an item
- CAPTURING: when item present, collect samples for CAPTURE_SECONDS
- HOLDING: compute final robust weight once, emit the SAME final weight continuously
- RESET: when removed (empty confirmed), reset and wait for next item

Outlier defenses:
- Median pre-filter (RAW_MEDIAN_WINDOW=5)
- Hard gating (reject > MAX_PLAUSIBLE_G; reject jumps > MAX_STEP_G; reject NaN/inf)
- Robust final weight (MAD-filter + trimmed mean)

Signals:
- weight_ready: SAFE weight for logic/DB (live in IDLE/CAPTURING, held in HOLDING)
- weight_display_ready: UI-only stabilized weight (snap band)
- weight_finalized: emitted ONCE per item (final robust weight)
- raw_reading: raw library reading (debug; may include spikes)
"""

import math
import time
import threading
import statistics
import json
import os
from collections import deque
from PySide6.QtCore import QThread, Signal, QObject

from hx711 import HX711 as HX711Driver


# ── Pins / calibration ──
HX711_DOUT_PIN = 5
HX711_SCK_PIN = 6
DEFAULT_REFERENCE_UNIT = 223.949121
_CALIBRATION_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "hx711_calibration.json")


def _load_reference_unit() -> float:
    if not os.path.exists(_CALIBRATION_CONFIG_PATH):
        return float(DEFAULT_REFERENCE_UNIT)

    try:
        with open(_CALIBRATION_CONFIG_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
        value = float(payload.get("reference_unit", DEFAULT_REFERENCE_UNIT))
        if value <= 0.0 or not math.isfinite(value):
            return float(DEFAULT_REFERENCE_UNIT)
        return value
    except Exception:
        return float(DEFAULT_REFERENCE_UNIT)


REFERENCE_UNIT = _load_reference_unit()


def get_current_reference_unit() -> float:
    return float(REFERENCE_UNIT)


def persist_reference_unit(value: float) -> float | None:
    global REFERENCE_UNIT

    if not isinstance(value, (int, float)) or not math.isfinite(value):
        return None

    value = float(value)
    if value <= 0.0:
        return None

    payload = {"reference_unit": value}
    with open(_CALIBRATION_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    REFERENCE_UNIT = value
    return value

# ── Timing ──
READ_INTERVAL_MS = 100       # 10 SPS loop
INTERNAL_SAMPLES = 1         # keep 1 for responsiveness

# ── Thresholds ──
ZERO_THRESHOLD = 5.0
PRESENT_THRESHOLD = 208.0
CLEAR_THRESHOLD = 140.0
EMPTY_CONFIRM_SAMPLES = 6    # 0.6s empty required to reset (tune for conveyor vibration)

# ── Capture / hold ──
CAPTURE_SECONDS = 3
EXPECTED_CAPTURE_SAMPLES = int(CAPTURE_SECONDS * (1000 / READ_INTERVAL_MS))
MIN_CAPTURE_SAMPLES = max(20, int(EXPECTED_CAPTURE_SAMPLES * 0.75))
TRIM_FRACTION = 0.10         # trim 10% extremes after MAD-filter

# ── Target qualification for accepted items ──
TARGET_WEIGHT_MIN_G = 224.5
TARGET_WEIGHT_MAX_G = 229.5
TARGET_WEIGHT_TOLERANCE_PCT = 3.5

# ── UI stabilization (UI only) ──
SNAP_BAND_G = 6.9

# ── Auto-retare (optional; can briefly block when it runs) ──
TARE_SAMPLES = 20
RETARE_EMPTY_SAMPLES = 40    # 8s empty before retare (reduces blocking frequency)
CALIBRATION_SAMPLES = 35

# ── Robust / outlier handling ──
ROBUST_Z_THRESH = 3.3
MAX_PLAUSIBLE_G = 1000.0     # max product 1000g => keep margin; rejects 4131g spikes
MAX_STEP_G = 700.0           # max change per 100ms; tune (400–900) depending on item drop impact
RAW_MEDIAN_WINDOW = 5        # median window size (odd recommended)


# ── Robust helpers ──
def robust_average(values, z_thresh: float = ROBUST_Z_THRESH) -> float:
    """Median/MAD-filtered mean for small windows."""
    if not values:
        return 0.0
    if len(values) < 5:
        return sum(values) / len(values)

    med = statistics.median(values)
    abs_dev = [abs(x - med) for x in values]
    mad = statistics.median(abs_dev)
    if mad == 0:
        return float(med)

    def robust_z(x):
        return 0.6745 * (x - med) / mad

    filtered = [x for x in values if abs(robust_z(x)) <= z_thresh]
    if not filtered:
        return float(med)
    return sum(filtered) / len(filtered)


def robust_trimmed_average(values, z_thresh: float = ROBUST_Z_THRESH, trim_frac: float = TRIM_FRACTION) -> float:
    """
    Robust final weight:
      1) MAD-filter around the median
      2) Trim top/bottom trim_frac
      3) Mean of remainder
    """
    if not values:
        return 0.0
    if len(values) < 8:
        return robust_average(values, z_thresh=z_thresh)

    med = statistics.median(values)
    abs_dev = [abs(x - med) for x in values]
    mad = statistics.median(abs_dev)

    if mad != 0:
        def robust_z(x):
            return 0.6745 * (x - med) / mad
        vals = [x for x in values if abs(robust_z(x)) <= z_thresh]
        if not vals:
            vals = [float(med)]
    else:
        vals = list(values)

    xs = sorted(vals)
    k = int(len(xs) * trim_frac)
    if k > 0 and len(xs) - 2 * k >= 3:
        xs = xs[k:len(xs) - k]

    return float(sum(xs) / len(xs))


def _is_finite(x) -> bool:
    return isinstance(x, (int, float)) and math.isfinite(x)


def _median(dq: deque) -> float:
    xs = list(dq)
    if not xs:
        return 0.0
    return float(statistics.median(xs))


def sanitize_weight(w: float, last_good: float) -> float:
    """
    Hard gate:
    - reject NaN/inf
    - clamp small/negative to 0
    - reject > MAX_PLAUSIBLE_G
    - reject single-step jumps > MAX_STEP_G
    """
    if not _is_finite(w):
        return last_good

    if w < ZERO_THRESHOLD:
        w = 0.0

    if w > MAX_PLAUSIBLE_G:
        return last_good

    if abs(w - last_good) > MAX_STEP_G:
        return last_good

    return float(w)


def is_weight_in_target_range(weight: float) -> bool:
    """Qualification filter disabled: accept every finite finalized weight."""
    return _is_finite(weight)


# ── State labels ──
IDLE = "IDLE"
CAPTURING = "CAPTURING"
HOLDING = "HOLDING"


class HX711Thread(QThread):
    weight_ready = Signal(float)          # SAFE logic/DB weight (live or held)
    weight_display_ready = Signal(float)  # UI-only stabilized
    weight_finalized = Signal(float)      # ONE shot per item
    weight_qualified = Signal(float)      # ONE shot per item (target range only)
    raw_reading = Signal(float)           # raw debug

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._lock = threading.Lock()

        # UI stabilization
        self._last_stable_weight = 0.0

        # outlier gating
        self._last_good_weight = 0.0
        self._raw_window = deque(maxlen=RAW_MEDIAN_WINDOW)

        # small logic smoothing window
        self._logic_window = deque(maxlen=7)

        # auto-retare
        self._empty_samples_for_retare = 0

        # state machine
        self._state = IDLE
        self._capture_start = 0.0
        self._capture_buf = []
        self._held_weight = 0.0
        self._empty_run = 0
        self._final_sent = False

    def run(self):
        self._running = True

        sensor = None
        try:
            sensor = HX711Driver(HX711_DOUT_PIN, HX711_SCK_PIN)
            sensor.set_reading_format("MSB", "MSB")
            sensor.set_reference_unit(get_current_reference_unit())
            sensor.reset()
            sensor.tare(TARE_SAMPLES)

            while self._running:
                # ── Raw read ──
                try:
                    w_raw = float(sensor.get_weight(INTERNAL_SAMPLES))
                except Exception:
                    # Keep worker alive through transient read failures.
                    self.msleep(READ_INTERVAL_MS)
                    continue

                self.raw_reading.emit(w_raw)

                # ── Median prefilter + hard gating ──
                self._raw_window.append(w_raw)
                w_med = _median(self._raw_window)
                w = sanitize_weight(w_med, self._last_good_weight)
                self._last_good_weight = w

                # ── Smooth a bit for logic ──
                self._logic_window.append(w)
                w_logic = robust_average(list(self._logic_window), z_thresh=ROBUST_Z_THRESH)

                # ── Auto-retare when empty for long time (optional; can block briefly) ──
                if w_logic == 0.0:
                    self._empty_samples_for_retare += 1
                    if self._empty_samples_for_retare >= RETARE_EMPTY_SAMPLES:
                        sensor.tare(TARE_SAMPLES)
                        self._empty_samples_for_retare = 0
                else:
                    self._empty_samples_for_retare = 0

                now = time.monotonic()

                # ── State machine ──
                if self._state == IDLE:
                    self._held_weight = 0.0
                    self._empty_run = 0
                    self._final_sent = False
                    self._capture_buf.clear()

                    out_weight = w_logic

                    if w_logic >= PRESENT_THRESHOLD:
                        self._state = CAPTURING
                        self._capture_start = now
                        self._capture_buf = [w_logic]

                elif self._state == CAPTURING:
                    out_weight = w_logic
                    self._capture_buf.append(w_logic)

                    # If it disappears early, abort and go back
                    if w_logic <= CLEAR_THRESHOLD:
                        self._empty_run += 1
                        if self._empty_run >= 2:
                            self._state = IDLE
                            self._capture_buf.clear()
                            self._empty_run = 0
                    else:
                        self._empty_run = 0

                    elapsed = now - self._capture_start
                    if self._state == CAPTURING and elapsed >= CAPTURE_SECONDS and len(self._capture_buf) >= MIN_CAPTURE_SAMPLES:
                        final_w = robust_trimmed_average(self._capture_buf, z_thresh=ROBUST_Z_THRESH, trim_frac=TRIM_FRACTION)

                        self._held_weight = final_w
                        self._state = HOLDING

                        if not self._final_sent:
                            self.weight_finalized.emit(final_w)
                            if is_weight_in_target_range(final_w):
                                self.weight_qualified.emit(final_w)
                            self._final_sent = True

                        out_weight = self._held_weight

                else:  # HOLDING
                    out_weight = self._held_weight

                    if w_logic <= CLEAR_THRESHOLD:
                        self._empty_run += 1
                    else:
                        self._empty_run = 0

                    if self._empty_run >= EMPTY_CONFIRM_SAMPLES:
                        # Reset for next item
                        self._state = IDLE
                        self._held_weight = 0.0
                        self._empty_run = 0
                        self._final_sent = False
                        self._capture_buf.clear()
                        self._logic_window.clear()
                        self._raw_window.clear()
                        self._last_good_weight = 0.0
                        self._last_stable_weight = 0.0
                        out_weight = 0.0

                # ── Emit SAFE weight (live or held) ──
                self.weight_ready.emit(float(out_weight))

                # ── UI stabilized weight (snap band) ──
                if out_weight > 0.0:
                    if self._last_stable_weight > 0.0 and abs(out_weight - self._last_stable_weight) <= SNAP_BAND_G:
                        w_display = self._last_stable_weight
                    else:
                        self._last_stable_weight = float(out_weight)
                        w_display = float(out_weight)
                else:
                    w_display = 0.0
                    self._last_stable_weight = 0.0

                self.weight_display_ready.emit(w_display)

                self.msleep(READ_INTERVAL_MS)
        finally:
            if sensor is not None:
                try:
                    sensor.power_down()
                except Exception:
                    pass

    def stop(self):
        self._running = False
        self.wait(3000)

    def reset(self):
        self._state = IDLE
        self._held_weight = 0.0
        self._capture_buf.clear()
        self._logic_window.clear()
        self._raw_window.clear()
        self._last_good_weight = 0.0
        self._last_stable_weight = 0.0
        self._empty_run = 0
        self._final_sent = False


class HX711Module(QObject):
    weight_finalized = Signal(float)
    weight_qualified = Signal(float)
    weight_display_ready = Signal(float)

    def __init__(self, label_weight, label_count=None, parent=None):
        super().__init__(parent)
        self.label_weight = label_weight
        self.label_count = label_count
        self.thread = None
        self._is_running = False
        self._captured_count = 0

    @property
    def is_running(self) -> bool:
        return self._is_running

    def start(self):
        if self._is_running:
            return

        self.thread = HX711Thread()
        self.thread.weight_display_ready.connect(self._on_weight)
        self.thread.weight_finalized.connect(self._on_weight_finalized)
        self.thread.weight_qualified.connect(self._on_weight_qualified)
        self.thread.start()
        self._is_running = True

    def stop(self):
        if not self._is_running:
            return
        if self.thread:
            self.thread.stop()
        self._is_running = False

    def reset(self):
        self.stop()
        self._captured_count = 0
        self.label_weight.setText("Weight: -")
        if self.label_count:
            self.label_count.setText("Count: -")

    def suggest_reference_unit_from_known_weight(
        self,
        known_weight_g: float,
        samples: int = CALIBRATION_SAMPLES,
    ) -> float | None:
        """
        Compute REFERENCE_UNIT from raw HX711 counts using a known mass.

        Formula:
            reference_unit = raw_counts / known_weight_g

        This is independent from the currently configured REFERENCE_UNIT.
        """
        details = self.suggest_reference_unit_details_from_known_weight(
            known_weight_g=known_weight_g,
            samples=samples,
        )
        if details is None:
            return None
        return float(details["reference_unit"])

    def suggest_reference_unit_details_from_known_weight(
        self,
        known_weight_g: float,
        samples: int = CALIBRATION_SAMPLES,
    ) -> dict | None:
        """
        Compute REFERENCE_UNIT using raw HX711 counts and return calibration details.

        Returns:
            {
                "reference_unit": <float>,
                "raw_counts": <float>,
                "samples": <int>
            }
        """
        if known_weight_g <= 0.0:
            return None

        used_samples = max(8, int(samples))

        was_running = self._is_running
        if was_running:
            self.stop()

        sensor = None
        try:
            sensor = HX711Driver(HX711_DOUT_PIN, HX711_SCK_PIN)
            sensor.set_reading_format("MSB", "MSB")
            # Explicit raw-count mode so calibration is independent from current reference unit.
            sensor.set_reference_unit(1)
            sensor.reset()
            sensor.tare(TARE_SAMPLES)

            raw_values = [float(sensor.get_value(1)) for _ in range(used_samples)]
            raw_counts = robust_trimmed_average(raw_values, z_thresh=ROBUST_Z_THRESH, trim_frac=TRIM_FRACTION)
            if raw_counts <= 0.0:
                return None

            reference_unit = float(raw_counts / known_weight_g)
            return {
                "reference_unit": reference_unit,
                "raw_counts": float(raw_counts),
                "samples": int(used_samples),
            }
        finally:
            if sensor is not None:
                try:
                    sensor.power_down()
                except Exception:
                    pass
            if was_running:
                self.start()

    def apply_reference_unit(self, new_reference_unit: float) -> float | None:
        was_running = self._is_running
        if was_running:
            self.stop()

        try:
            return persist_reference_unit(new_reference_unit)
        finally:
            if was_running:
                self.start()

    @staticmethod
    def is_weight_accepted(weight: float) -> bool:
        return is_weight_in_target_range(weight)

    def _on_weight_finalized(self, weight: float):
        # Finalized is emitted for all items; tally is handled on qualified-only path.
        self.weight_finalized.emit(weight)

    def _on_weight_qualified(self, weight: float):
        self._captured_count += 1
        if self.label_count:
            self.label_count.setText(f"Count: {self._captured_count}")
            self.label_count.adjustSize()
        self.weight_qualified.emit(weight)

    def _on_weight(self, weight: float):
        self.label_weight.setText(f"Weight: {weight:.1f} g")
        self.label_weight.adjustSize()
        self.weight_display_ready.emit(weight)
