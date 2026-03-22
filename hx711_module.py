"""
HX711 load-cell module (10 SPS, weight-first) — FIXED + Discrete Target Matching (Option 2)
+ Robust outlier rejection (Median/MAD). (NO SIMULATION MODE)

Changes from your earlier version:
- Removed simulation mode entirely (requires hx711 library + hardware).
- Added robust outlier rejection for the presence window average.
- Reduced SNAP_BAND_G default to avoid display "freezing".
- Increased COUNT_AVG_WINDOW for more stable counting.

Counts ONLY when the measured weight (window-robust average) matches one of:
225, 300, 450, 500, 600, 750, 800, 900, 1000 within ±5%.
"""

import threading
import statistics
from collections import deque
from PySide6.QtCore import QThread, Signal, QObject

from hx711 import HX711 as HX711Driver  # <-- REQUIRED; will raise if not installed


# ── Configuration (10 SPS tuned) ──
HX711_DOUT_PIN = 5
HX711_SCK_PIN = 6
REFERENCE_UNIT = 97.456231590  # <-- replace with your calibrated value (can be negative)

READ_INTERVAL_MS = 100   # 10 SPS
INTERNAL_SAMPLES = 1     # IMPORTANT for responsiveness (try 3 if still noisy)

# Weight handling
ZERO_THRESHOLD = 5.0

# Display stabilization: use small band; 150g can freeze display across large changes
SNAP_BAND_G = 10.0

# Counting logic (hysteresis + confirmation)
PRESENT_THRESHOLD = 200.0
CLEAR_THRESHOLD = 120.0

COUNT_AVG_WINDOW = 7
PRESENT_CONFIRM_SAMPLES = 3
EMPTY_CONFIRM_SAMPLES = 4

# Drift correction
TARE_SAMPLES = 21
RETARE_EMPTY_SAMPLES = 35  # 35 * 100ms = 3.5s

# ── Discrete target matching ──
TARGET_WEIGHTS_G = [225, 300, 450, 500, 600, 750, 800, 900, 1000]
TOL_PCT = 0.05  # ±5%

# ── Outlier rejection config ──
ROBUST_Z_THRESH = 3.3     # lower = more aggressive rejection (try 3.0–4.0)


def match_target_weight(w_g: float):
    """Return matched target weight if within tolerance, else None."""
    for t in TARGET_WEIGHTS_G:
        if t * (1.0 - TOL_PCT) <= w_g <= t * (1.0 + TOL_PCT):
            return float(t)
    return None


def robust_average(values, z_thresh: float = ROBUST_Z_THRESH) -> float:
    """
    Robust average using Median + MAD outlier rejection.
    Keeps values within z_thresh robust-z of the median.
    """
    if not values:
        return 0.0
    if len(values) < 5:
        return sum(values) / len(values)

    med = statistics.median(values)
    abs_dev = [abs(x - med) for x in values]
    mad = statistics.median(abs_dev)

    if mad == 0:
        return med

    def robust_z(x):
        return 0.6745 * (x - med) / mad

    filtered = [x for x in values if abs(robust_z(x)) <= z_thresh]
    if not filtered:
        return med
    return sum(filtered) / len(filtered)


class HX711Thread(QThread):
    """
    Reads HX711 continuously. Emits weight every sample (fast UI),
    and emits count only on debounced presence transitions (no duplicates),
    AND only when the measured weight matches one of the discrete target weights.
    """
    weight_ready = Signal(float)
    count_updated = Signal(int)
    raw_reading = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._count = 0
        self._lock = threading.Lock()

        # display stabilization
        self._last_stable_weight = 0.0

        # counting / presence state
        self._product_present = False
        self._presence_window = deque(maxlen=COUNT_AVG_WINDOW)
        self._present_run = 0
        self._empty_run = 0

        # retare state
        self._empty_samples_for_retare = 0

        # last accepted matched target (optional)
        self._last_matched_target = None

    def run(self):
        self._running = True
        with self._lock:
            self._count = 0

        sensor = HX711Driver(HX711_DOUT_PIN, HX711_SCK_PIN)
        sensor.set_reading_format("MSB", "MSB")
        sensor.set_reference_unit(REFERENCE_UNIT)
        sensor.reset()
        sensor.tare(TARE_SAMPLES)

        while self._running:
            # ── Read one sample ──
            w = float(sensor.get_weight(INTERNAL_SAMPLES))
            self.raw_reading.emit(w)

            # Clamp near-zero/negative drift to 0
            if w < ZERO_THRESHOLD:
                w = 0.0

            # ── Retare only when empty for long enough ──
            if w == 0.0:
                self._empty_samples_for_retare += 1
                if self._empty_samples_for_retare >= RETARE_EMPTY_SAMPLES:
                    sensor.tare(TARE_SAMPLES)
                    self._empty_samples_for_retare = 0
            else:
                self._empty_samples_for_retare = 0

            # ── Weight stabilization for display ──
            if w > 0.0:
                if self._last_stable_weight > 0.0 and abs(w - self._last_stable_weight) <= SNAP_BAND_G:
                    w_display = self._last_stable_weight
                else:
                    self._last_stable_weight = w
                    w_display = w
            else:
                w_display = 0.0

            self.weight_ready.emit(w_display)

            # ── Presence detection using robust averaging over a window ──
            self._presence_window.append(w)
            w_avg = robust_average(list(self._presence_window), z_thresh=ROBUST_Z_THRESH)

            if not self._product_present:
                if w_avg >= PRESENT_THRESHOLD:
                    self._present_run += 1
                else:
                    self._present_run = 0

                # Attempt count only when present confirmed N times AND matches a target band
                if self._present_run >= PRESENT_CONFIRM_SAMPLES:
                    matched = match_target_weight(w_avg)
                    if matched is not None:
                        with self._lock:
                            self._count += 1
                            count = self._count
                        self.count_updated.emit(count)

                        self._product_present = True
                        self._empty_run = 0
                        self._last_matched_target = matched
                    else:
                        self._last_matched_target = None

                    self._present_run = 0
            else:
                if w_avg <= CLEAR_THRESHOLD:
                    self._empty_run += 1
                else:
                    self._empty_run = 0

                if self._empty_run >= EMPTY_CONFIRM_SAMPLES:
                    self._product_present = False
                    self._empty_run = 0
                    self._present_run = 0
                    self._last_stable_weight = 0.0
                    self._presence_window.clear()
                    self._last_matched_target = None

            self.msleep(READ_INTERVAL_MS)

        sensor.power_down()

    def stop(self):
        self._running = False
        self.wait()

    def reset_count(self):
        with self._lock:
            self._count = 0
        self._last_stable_weight = 0.0
        self._product_present = False
        self._presence_window.clear()
        self._present_run = 0
        self._empty_run = 0
        self._empty_samples_for_retare = 0
        self._last_matched_target = None


class HX711Module(QObject):
    def __init__(self, label_weight, label_count, parent=None):
        super().__init__(parent)
        self.label_weight = label_weight
        self.label_count = label_count
        self.thread = None
        self._is_running = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    def start(self):
        if self._is_running:
            return

        self.thread = HX711Thread()
        self.thread.weight_ready.connect(self._on_weight)
        self.thread.count_updated.connect(self._on_count)
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
        self.label_weight.setText("Weight: -")
        self.label_count.setText("Count: -")

    def _on_weight(self, weight: float):
        self.label_weight.setText(f"Weight: {weight:.1f} g")
        self.label_weight.adjustSize()

    def _on_count(self, count: int):
        self.label_count.setText(f"Count: {count}")
        self.label_count.adjustSize()
