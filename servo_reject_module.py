"""
Servo reject actuator helper.

Behavior:
- Homes to 0 degrees on startup.
- On reject trigger: move to 180 then return to 0.
"""

from __future__ import annotations

import time

try:
    import RPi.GPIO as GPIO
except Exception:
    GPIO = None


class ServoRejectController:
    def __init__(
        self,
        pin: int = 17,
        frequency_hz: int = 50,
        move_settle_seconds: float = 0.55,
        push_hold_seconds: float = 0.35,
    ):
        self.pin = int(pin)
        self.frequency_hz = int(frequency_hz)
        self.move_settle_seconds = float(move_settle_seconds)
        self.push_hold_seconds = float(push_hold_seconds)
        self._pwm = None
        self._enabled = GPIO is not None

        if not self._enabled:
            print("[SERVO] RPi.GPIO unavailable; servo control disabled")
            return

        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.pin, GPIO.OUT)
        self._pwm = GPIO.PWM(self.pin, self.frequency_hz)
        self._pwm.start(0)
        self.home()

    @property
    def is_enabled(self) -> bool:
        return bool(self._enabled)

    @staticmethod
    def _angle_to_duty(angle: int) -> float:
        if angle == 0:
            return (500 / 20000) * 100
        if angle == 180:
            return (2500 / 20000) * 100
        raise ValueError("Only 0 and 180 angles are supported")

    def _move(self, angle: int, hold_seconds: float | None = None):
        if not self._enabled or self._pwm is None:
            return
        duty = self._angle_to_duty(int(angle))
        self._pwm.ChangeDutyCycle(duty)
        time.sleep(self.move_settle_seconds if hold_seconds is None else float(hold_seconds))
        self._pwm.ChangeDutyCycle(0)

    def home(self):
        self._move(0)
        print("[SERVO] Home at 0")

    def reject_cycle(
        self,
        push_move_seconds: float | None = None,
        return_move_seconds: float | None = None,
        push_hold_seconds: float | None = None,
    ):
        if not self._enabled:
            print("[SERVO] Reject cycle skipped (disabled)")
            return
        print("[SERVO] Reject cycle: 180 -> 0")
        self._move(180, hold_seconds=push_move_seconds)
        hold = self.push_hold_seconds if push_hold_seconds is None else float(push_hold_seconds)
        if hold > 0:
            time.sleep(hold)
        self._move(0, hold_seconds=return_move_seconds)

    def cleanup(self):
        if not self._enabled:
            return
        try:
            self._move(0, hold_seconds=0.30)
        except Exception:
            pass
        if self._pwm is not None:
            self._pwm.stop()
            self._pwm = None
        GPIO.cleanup(self.pin)
        print("[SERVO] Cleaned up")
