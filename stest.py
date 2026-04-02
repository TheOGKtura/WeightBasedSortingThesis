import RPi.GPIO as GPIO
import time

SERVO_PIN = 17
PWM_FREQUENCY = 50
HOME_ANGLE = 0
REJECT_ANGLE = 180
MOVE_SETTLE_SECONDS = 0.55
PUSH_HOLD_SECONDS = 0.35


def angle_to_duty(angle: int) -> float:
    if angle == 0:
        return (500 / 20000) * 100
    if angle == 180:
        return (2500 / 20000) * 100
    raise ValueError("Only 0 and 180 angles are supported")


def move_servo(pwm: GPIO.PWM, angle: int, hold_seconds: float = MOVE_SETTLE_SECONDS):
    duty = angle_to_duty(angle)
    pwm.ChangeDutyCycle(duty)
    time.sleep(hold_seconds)
    pwm.ChangeDutyCycle(0)


def reject_cycle(pwm: GPIO.PWM):
    print("[SERVO] Reject detected -> moving to 180")
    move_servo(pwm, REJECT_ANGLE, MOVE_SETTLE_SECONDS)
    time.sleep(PUSH_HOLD_SECONDS)
    print("[SERVO] Returning to home 0")
    move_servo(pwm, HOME_ANGLE, MOVE_SETTLE_SECONDS)


def handle_weight_result(pwm: GPIO.PWM, is_defect: bool):
    if is_defect:
        reject_cycle(pwm)
    else:
        # Keep default/home position for accepted items.
        move_servo(pwm, HOME_ANGLE, 0.20)


GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(SERVO_PIN, GPIO.OUT)
pwm = GPIO.PWM(SERVO_PIN, PWM_FREQUENCY)
pwm.start(0)

try:
    # Always start with a known default/home position.
    print("[SERVO] Homing to 0 on startup")
    move_servo(pwm, HOME_ANGLE)

    while True:
        inp = input("Weight result [d=defect, a=accepted, q=quit]: ").strip().lower()
        if inp == "q":
            break
        if inp not in {"d", "a"}:
            print("Invalid input. Use d, a, or q.")
            continue

        handle_weight_result(pwm, is_defect=(inp == "d"))

except KeyboardInterrupt:
    pass
finally:
    # Leave servo in default/home position before shutdown.
    try:
        move_servo(pwm, HOME_ANGLE, 0.30)
    except Exception:
        pass
    pwm.stop()
    GPIO.cleanup()
    print("[SERVO] Exiting")