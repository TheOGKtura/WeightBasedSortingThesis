"""
TowerPro MG958 Servo - Continuous Sweep
Raspberry Pi 4 Model B - GPIO 17 (Pin 11)
"""

import RPi.GPIO as GPIO
import time

# Setup
GPIO.setmode(GPIO.BCM)
GPIO.setup(17, GPIO.OUT)
pwm = GPIO.PWM(17, 50)  # 50Hz frequency
pwm.start(0)

print("Starting continuous servo sweep...")
print("Press Ctrl+C to stop\n")

try:
    while True:
        # Sweep 0° to 180°
        print("Sweeping 0° → 180°")
        for angle in range(0, 176, 2):
            duty_cycle = 5 + (angle / 175) * 5  # 5% to 10%
            pwm.ChangeDutyCycle(duty_cycle)
            time.sleep(0.04)
        
        # Sweep 180° back to 0°
        print("Sweeping 180° → 0°")
        for angle in range(175, -1, -2):
            duty_cycle = 5 + (angle / 175) * 5
            pwm.ChangeDutyCycle(duty_cycle)
            time.sleep(0.04)

except KeyboardInterrupt:
    print("\n\nStopping...")

finally:
    pwm.stop()
    GPIO.cleanup()
    print("Done!")
