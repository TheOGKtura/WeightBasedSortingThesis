import RPi.GPIO as GPIO
import time
from hx711 import HX711   # assuming your HX711 class is saved as hx711.py

# Pin configuration (adjust to your wiring)
DOUT = 5   # GPIO pin connected to HX711 DOUT
PD_SCK = 6 # GPIO pin connected to HX711 SCK

def cleanAndExit():
    print("Cleaning up...")
    GPIO.cleanup()
    exit()

hx = HX711(dout=DOUT, pd_sck=PD_SCK)

# Step 1: Reset and tare
hx.reset()
print("Taring...")
hx.tare()

print("Tare done. Place a known weight on the scale.")

# Step 2: Wait for user to place weight
time.sleep(5)

# Step 3: Read raw value
raw_value = hx.read_average(times=15)
print("Raw average value:", raw_value)

# Step 4: Enter known weight (grams)
known_weight = 500.0  # example: 500g calibration weight

# Step 5: Compute reference unit
reference_unit = raw_value / known_weight
hx.set_reference_unit(reference_unit)

print("Calibration complete.")
print("Reference unit set to:", reference_unit)

# Step 6: Test readings
while True:
    try:
        weight = hx.get_weight(times=5)
        print("Weight: {} g".format(weight))
        time.sleep(1)
    except KeyboardInterrupt:
        cleanAndExit()
