import time
import RPi.GPIO as GPIO
from hx711 import HX711

# ========== CONFIG ==========
REFERENCE_CODE = 223
KNOWN_WEIGHT = 225  # grams

# Raspberry Pi GPIO pins (BCM numbering)
DATA_PIN = 5        # GPIO 5 (physical pin 29)
CLOCK_PIN = 6       # GPIO 6 (physical pin 31)

# ========== SETUP ==========
GPIO.setmode(GPIO.BCM)

hx = HX711(dout_pin=DATA_PIN, pd_sck_pin=CLOCK_PIN)
hx.set_reading_format("MSB", "MSB")

print(f"Tatobarι HX711 Weight Reader")
print(f"Reference Code: {REFERENCE_CODE}")
print(f"Known Weight Constant: {KNOWN_WEIGHT}g\n")

# ========== CALIBRATION ==========
print("=" * 50)
print("CALIBRATION PROCESS")
print("=" * 50)

print("\n1. Remove ALL weight from the scale")
print("Press ENTER when ready...")
input()

hx.reset()
time.sleep(1)

# Tare (zero) the scale
print("Zeroing the scale...")
hx.tare()
time.sleep(2)
print("✓ Scale zeroed\n")

print(f"2. Place EXACTLY {KNOWN_WEIGHT}g on the scale")
print("Press ENTER when ready...")
input()

time.sleep(2)

# Get calibration reading
print("Reading calibration value...")
calibration_readings = []
for i in range(10):
    calibration_readings.append(hx.get_weight(5))
    time.sleep(0.1)

avg_calibration = sum(calibration_readings) / len(calibration_readings)
calibration_factor = avg_calibration / KNOWN_WEIGHT

print(f"✓ Calibration complete!")
print(f"  Average reading: {avg_calibration:.2f}")
print(f"  Calibration factor: {calibration_factor:.6f}\n")

hx.set_weight_unit("g")

# ========== MAIN LOOP ==========
print("=" * 50)
print("WEIGHT MEASUREMENT")
print("=" * 50)
print("Press Ctrl+C to stop\n")

try:
    measurement_count = 0
    while True:
        measurement_count += 1
        
        # Get weight (average of 5 readings)
        weight = hx.get_weight(5)
        difference = weight - KNOWN_WEIGHT
        percent_diff = (difference / KNOWN_WEIGHT) * 100
        
        # Status indicator
        if abs(difference) < 2:
            status = "✓ EXCELLENT"
        elif abs(difference) < 5:
            status = "✓ GOOD"
        elif abs(difference) < 10:
            status = "⚠ OK"
        else:
            status = "✗ CHECK CALIBRATION"
        
        print(f"[{measurement_count:05d}] Weight: {weight:7.2f}g | Ref: {KNOWN_WEIGHT}g | Diff: {difference:+6.2f}g ({percent_diff:+5.1f}%) | {status}")
        
        time.sleep(1)

except KeyboardInterrupt:
    print("\n\nStopping weight reader...")
except Exception as e:
    print(f"\n\nError: {e}")
finally:
    hx.power_down()
    GPIO.cleanup()
    print("✓ HX711 powered down and GPIO cleaned up")