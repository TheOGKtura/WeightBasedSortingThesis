#!/usr/bin/env python3
"""
HX711 calibration tester (modified tatobari style)

Shows:
- live raw counts (above tare) and grams
- computed REFERENCE_UNIT (counts per gram)
- verification reading vs known weight
"""

import time
import statistics
from hx711 import HX711

DOUT = 5
SCK = 6

TARE_SAMPLES = 25
LIVE_HZ = 10
LIVE_SECONDS = 5.0

CAL_READS = 40
CAL_DELAY = 0.05

def mean_samples(fn, n=CAL_READS, delay=CAL_DELAY):
    xs = []
    for _ in range(n):
        xs.append(float(fn()))
        time.sleep(delay)
    return statistics.mean(xs), xs

def live_stream(hx, seconds=LIVE_SECONDS):
    """Print live counts+grams for a few seconds."""
    period = 1.0 / LIVE_HZ
    t0 = time.monotonic()
    while time.monotonic() - t0 < seconds:
        # counts above tare (with ref_unit=1)
        counts = float(hx.get_value(1))
        # grams if reference unit has been set to counts/gram
        grams = float(hx.get_weight(1))
        print(f"counts={counts:>10.2f}   grams={grams:>8.2f}")
        time.sleep(period)

def main():
    hx = HX711(DOUT, SCK)
    hx.set_reading_format("MSB", "MSB")

    hx.reset()

    # Start in "counts mode"
    hx.set_reference_unit(1.0)

    input("Remove all weight, then press Enter to tare...")
    hx.tare(TARE_SAMPLES)

    print("\nLive readings (EMPTY) for a few seconds:")
    live_stream(hx, seconds=3.0)

    known_g = float(input("\nPlace known weight on scale.\nEnter known weight in grams (e.g., 225): ").strip())
    input("Let it settle 2 seconds, then press Enter to compute reference...")
    time.sleep(2.0)

    # In counts mode, get_value() ~= counts above tare
    loaded_counts_mean, loaded_counts_samples = mean_samples(lambda: hx.get_value(5))
    print(f"\nLoaded counts mean: {loaded_counts_mean:.2f}")
    print(f"Loaded counts span: {min(loaded_counts_samples):.2f} .. {max(loaded_counts_samples):.2f}")

    if abs(loaded_counts_mean) < 10:
        print("Counts delta is too small—check wiring / load cell / that the weight is really on the scale.")
        return

    reference_unit = loaded_counts_mean / known_g  # counts per gram

    print("\n=== COMPUTED CALIBRATION ===")
    print(f"Known weight:           {known_g:.4f} g")
    print(f"REFERENCE_UNIT:         {reference_unit:.6f}  (counts/gram)")
    print("\nPaste into your app:")
    print(f"REFERENCE_UNIT = {reference_unit:.6f}")

    # Switch to grams mode using computed reference
    hx.set_reference_unit(reference_unit)

    print("\nLive readings (with calibration applied) for a few seconds:")
    live_stream(hx, seconds=5.0)

    # Verification (average a bit)
    measured_g_mean, measured_samples = mean_samples(lambda: hx.get_weight(5))
    err = measured_g_mean - known_g

    print("\n=== VERIFICATION ===")
    print(f"Expected: {known_g:.2f} g")
    print(f"Measured: {measured_g_mean:.2f} g")
    print(f"Error:    {err:+.2f} g")
    print(f"Span:     {min(measured_samples):.2f} .. {max(measured_samples):.2f} g")

    hx.power_down()

if __name__ == "__main__":
    main()