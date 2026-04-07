#!/usr/bin/env python3
import time
import statistics
import RPi.GPIO as GPIO

DOUT = 5   # GPIO number (BCM)
SCK  = 6   # GPIO number (BCM)

# Gain/channel selection:
# After reading 24 bits, pulse extra clocks:
# 1 extra pulse = Channel A, gain 128 (most common)
# 2 extra pulses = Channel B, gain 32
# 3 extra pulses = Channel A, gain 64
GAIN_PULSES = 1

GPIO.setmode(GPIO.BCM)
GPIO.setup(SCK, GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(DOUT, GPIO.IN)

def wait_ready(timeout=1.0):
    t0 = time.time()
    while GPIO.input(DOUT) == 1:
        if time.time() - t0 > timeout:
            return False
        time.sleep(0.001)
    return True

def read_raw(timeout=1.0):
    if not wait_ready(timeout):
        raise TimeoutError("HX711 not ready (DOUT stayed high). Check wiring/power/gain rate.")

    # Read 24 bits
    value = 0
    for _ in range(24):
        GPIO.output(SCK, GPIO.HIGH)
        # short delay; HX711 is slow, but GPIO toggling is typically enough
        GPIO.output(SCK, GPIO.LOW)
        bit = GPIO.input(DOUT)
        value = (value << 1) | bit

    # Set gain/channel for next conversion
    for _ in range(GAIN_PULSES):
        GPIO.output(SCK, GPIO.HIGH)
        GPIO.output(SCK, GPIO.LOW)

    # Convert from unsigned 24-bit to signed 24-bit (two's complement)
    if value & 0x800000:
        value -= 1 << 24
    return value

def read_average(n=20, delay=0.01):
    samples = []
    for _ in range(n):
        samples.append(read_raw())
        time.sleep(delay)
    return statistics.mean(samples), samples

def main():
    try:
        print("HX711 raw read test. Press Ctrl+C to quit.\n")
        print(f"Using DOUT=GPIO{DOUT}, SCK=GPIO{SCK}, gain pulses={GAIN_PULSES}\n")

        input("Remove all weight from the scale, then press Enter to tare...")
        tare, tare_samples = read_average(n=30, delay=0.02)
        print(f"Tare (mean of 30): {tare:.2f}")
        print(f"Tare sample span: {min(tare_samples)} .. {max(tare_samples)}\n")

        known = float(input("Place a known weight on the scale.\nEnter known weight value (e.g., 500 for grams): ").strip())
        w_mean, w_samples = read_average(n=30, delay=0.02)
        print(f"Loaded mean: {w_mean:.2f}")
        print(f"Loaded sample span: {min(w_samples)} .. {max(w_samples)}\n")

        delta = w_mean - tare
        if abs(delta) < 1:
            print("Delta is too small; something is wrong (no signal change).")
            return

        scale = delta / known  # counts per unit (grams, kg, etc.)
        print("Calibration result:")
        print(f"  delta_counts = loaded - tare = {delta:.2f}")
        print(f"  counts_per_unit = {scale:.6f}  (counts / your_unit)")
        print(f"  unit_per_count  = {1/scale:.9f} (your_unit / count)\n")

        print("Streaming readings (raw, net, converted). Ctrl+C to stop.")
        while True:
            raw = read_raw()
            net = raw - tare
            units = net / scale
            print(f"raw={raw:>10d}  net={net:>12.2f}  units={units:>10.3f}")
            time.sleep(0.1)

    except KeyboardInterrupt:
        pass
    finally:
        GPIO.cleanup()

if __name__ == "__main__":
    main()
