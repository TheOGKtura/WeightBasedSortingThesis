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

def samples_stats(samples):
    """Return mean/min/max/stdev for a list of numeric samples."""
    mean = statistics.mean(samples)
    mn = min(samples)
    mx = max(samples)
    stdev = statistics.pstdev(samples) if len(samples) > 1 else 0.0
    return mean, mn, mx, stdev

def verify_calibration(tare, scale, known_weight,
                       n=30, delay=0.02,
                       abs_tolerance=2.0,
                       pct_tolerance=1.0,
                       max_stdev_units=1.0):
    """
    Verify calibration using a known weight.
    Pass criteria:
      - absolute error <= abs_tolerance (in your units)
      - percent error <= pct_tolerance (%), if known_weight != 0
      - sample stdev in units <= max_stdev_units (stability)
    """
    mean_raw, raw_samples = read_average(n=n, delay=delay)

    # Convert each raw sample to units (so we can get stability in real units)
    unit_samples = [((r - tare) / scale) for r in raw_samples]
    u_mean, u_min, u_max, u_stdev = samples_stats(unit_samples)

    err = u_mean - known_weight
    abs_err = abs(err)
    pct_err = (abs_err / abs(known_weight) * 100.0) if known_weight != 0 else float("inf")

    pass_abs = abs_err <= abs_tolerance
    pass_pct = (pct_err <= pct_tolerance) if known_weight != 0 else False
    pass_stability = u_stdev <= max_stdev_units

    ok = pass_abs and pass_pct and pass_stability

    print("\nCalibration verification results:")
    print(f"  expected (known):  {known_weight:.4f}")
    print(f"  measured mean:     {u_mean:.4f}")
    print(f"  measured min/max:  {u_min:.4f} .. {u_max:.4f}")
    print(f"  measured stdev:    {u_stdev:.4f}  (units)")
    print(f"  error:             {err:+.4f}  (abs {abs_err:.4f}, {pct_err:.3f}%)")
    print("  thresholds:")
    print(f"    abs_tolerance:   {abs_tolerance:.4f} units")
    print(f"    pct_tolerance:   {pct_tolerance:.3f}%")
    print(f"    max_stdev_units: {max_stdev_units:.4f} units")
    print(f"  STATUS: {'PASS' if ok else 'FAIL'}\n")

    return ok

def main():
    try:
        print("HX711 raw read test. Press Ctrl+C to quit.\n")
        print(f"Using DOUT=GPIO{DOUT}, SCK=GPIO{SCK}, gain pulses={GAIN_PULSES}\n")

        input("Remove all weight from the scale, then press Enter to tare...")
        tare, tare_samples = read_average(n=30, delay=0.02)
        t_mean, t_min, t_max, t_stdev = samples_stats(tare_samples)
        print(f"Tare (mean of 30): {tare:.2f}")
        print(f"Tare sample span: {t_min} .. {t_max}   stdev={t_stdev:.2f}\n")

        known = float(input("Place a known weight on the scale.\nEnter known weight value (e.g., 500 for grams): ").strip())
        w_mean, w_samples = read_average(n=30, delay=0.02)
        w_mean2, w_min, w_max, w_stdev = samples_stats(w_samples)
        print(f"Loaded mean: {w_mean:.2f}")
        print(f"Loaded sample span: {w_min} .. {w_max}   stdev={w_stdev:.2f}\n")

        delta = w_mean - tare
        if abs(delta) < 1:
            print("Delta is too small; something is wrong (no signal change).")
            return

        scale = delta / known  # counts per unit (grams, kg, etc.)
        print("Calibration result:")
        print(f"  delta_counts = loaded - tare = {delta:.2f}")
        print(f"  counts_per_unit = {scale:.6f}  (counts / your_unit)")
        print(f"  unit_per_count  = {1/scale:.9f} (your_unit / count)\n")

        # --- NEW: verify calibration step ---
        input("Verification step:\nRemove the weight (back to zero), then press Enter...")
        # Re-tare check (optional but useful)
        tare2, tare2_samples = read_average(n=20, delay=0.02)
        print(f"Re-zero check (mean of 20): {tare2:.2f}  (drift vs tare: {tare2 - tare:+.2f} counts)")
        input("Now place the SAME known weight back on the scale, then press Enter to verify...")

        # Tune these tolerances for your project/scale:
        abs_tol = max(0.5, known * 0.005)   # e.g., 0.5 units or 0.5% of known, whichever is larger
        pct_tol = 1.0                       # 1% allowed
        max_stdev = max(0.2, known * 0.001) # stability requirement

        ok = verify_calibration(
            tare=tare,
            scale=scale,
            known_weight=known,
            n=30,
            delay=0.02,
            abs_tolerance=abs_tol,
            pct_tolerance=pct_tol,
            max_stdev_units=max_stdev
        )

        if not ok:
            print("Calibration verification failed.")
            print("Common causes: unstable platform, mechanical binding, wrong wiring, noisy power, wrong gain/channel, or too-low sample count.")
            print("You can retry calibration with more samples (e.g., 50-100) and ensure the scale is stable.\n")

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