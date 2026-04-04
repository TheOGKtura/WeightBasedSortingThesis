import RPi.GPIO as GPIO
import time

# ---------------------
# Configuration
# ---------------------
servo_pin = 17  # GPIO pin connected to servo signal (Yellow/Orange)
GPIO.setmode(GPIO.BCM)
GPIO.setup(servo_pin, GPIO.OUT)

# 50Hz is standard for analog servos like MG958
pwm = GPIO.PWM(servo_pin, 50)  
pwm.start(0)  # initial duty cycle

# ---------------------
# Helper function
# ---------------------
def angle_to_duty(angle):
    """
    Converts 0-180 degree angle to duty cycle for 50Hz PWM
    MG958 safe range ~500us to 2500us
    Duty cycle formula: (us / 20000) * 100
    """
    if angle < 0:
        angle = 0
    elif angle > 180:
        angle = 180

    pulse_width_us = 500 + (angle / 180) * 2000  # 500-2500us
    duty = (pulse_width_us / 20000) * 100        # convert to % for PWM
    return duty

# ---------------------
# Main loop
# ---------------------
try:
    while True:
        inp = input("Enter servo angle (0-180, 'q' to quit): ")
        if inp.lower() == 'q':
            break

        try:
            angle = float(inp)
        except ValueError:
            print("Please enter a valid number!")
            continue

        if 0 <= angle <= 180:
            duty = angle_to_duty(angle)
            pwm.ChangeDutyCycle(duty)
            print(f"Moving servo to {angle}° (Duty: {duty:.2f}%)")
            time.sleep(6)  # allow servo to move
            pwm.ChangeDutyCycle(0)  # stop sending signal to prevent jitter
        else:
            print("Angle out of range! Must be 0-180°")

except KeyboardInterrupt:
    pass

finally:
    pwm.stop()
    GPIO.cleanup()
    print("Exiting...")