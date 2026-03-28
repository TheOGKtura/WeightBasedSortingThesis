"""
Product recognition module (PiCamera-friendly) — ORB matching with strong "reject" behavior.

Anti-false-label features:
- Frame quality gate (min keypoints)
- Blur gate (Laplacian variance)
- Two-stage matching: compute good matches for all refs; run RANSAC only on top K candidates
- Best-vs-second margin rejection
- Debounced emit: require N consecutive detections; clear after M no-matches
"""

import os
import time
import logging
import numpy as np
from threading import Lock

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    logger.warning("opencv not installed. Run: pip install opencv-python-headless")

from PySide6.QtCore import QThread, Signal


PRODUCTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_img")

PRODUCT_DATABASE = [
    {
        "name": "Young Pork Tocino",
        "images": ["ct_image_1.jpg", "ct_image_2.jpg", "ct_image_3.jpg", "ct_image_4.jpg", "ct_image_5.jpg",
                   "ct_image_6.jpg", "ct_image_7.jpg", "ct_image_8.jpg", "ct_image_9.jpg","ct_image_96.jpg"],
    },
    {
        "name": "CDO CRISPY BURGER",
        "images": ["cb_image_1.jpg", "cb_image_2.jpg", "cb_image_3.jpg", "cb_image_4.jpg", "cb_image_5.jpg",
                   "cb_image_6.jpg", "cb_image_7.jpg", "cb_image_8.jpg", "cb_image_9.jpg", "cb_image_10.jpg",
                   "cb_image_11.jpg"],
    },
]

# ── Pi-friendly tuning ──
FRAME_MAX_WIDTH = 320

ORB_NFEATURES = 800
ORB_FAST_THRESHOLD = 12  # 8–20: lower finds more features; higher reduces noise

LOWE_RATIO = 0.72
MIN_GOOD_MATCHES = 18

# Reject frames that are too "simple" (empty background) or too dark
MIN_FRAME_KEYPOINTS = 70

# Reject motion blur (hand moving)
USE_BLUR_GATE = True
MIN_LAPLACIAN_VAR = 70.0  # raise if you still get blur false labels; lower if it rejects too much

# Two-stage match: run RANSAC only on top K candidates to save CPU
USE_RANSAC = True
TOPK_FOR_RANSAC = 2
RANSAC_REPROJ_THRESH = 5.0
MIN_INLIERS = 12

# Ambiguity reject: best must clearly beat second best
BEST_MARGIN_INLIERS = 5
BEST_MARGIN_RATIO = 1.15

# Thread debounce
CONFIRM_CONSECUTIVE = 2
CLEAR_CONSECUTIVE = 5


class ProductMatcher:
    def __init__(self, min_good_matches=MIN_GOOD_MATCHES):
        self.min_good_matches = min_good_matches
        self.references = []
        self.orb = None

        if not CV2_AVAILABLE:
            return

        self.orb = cv2.ORB_create(nfeatures=ORB_NFEATURES, fastThreshold=ORB_FAST_THRESHOLD)
        self.bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
        self._load_references()

    def _resize(self, img, max_width):
        h, w = img.shape[:2]
        if w > max_width:
            scale = max_width / w
            img = cv2.resize(img, (max_width, int(h * scale)), interpolation=cv2.INTER_AREA)
        return img

    def _laplacian_var(self, gray):
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())

    def _good_matches(self, des_ref, des_frame):
        matches = self.bf.knnMatch(des_ref, des_frame, k=2)
        good = []
        for pair in matches:
            if len(pair) != 2:
                continue
            m, n = pair
            if m.distance < LOWE_RATIO * n.distance:
                good.append(m)
        return good

    def _ransac_inliers(self, kp_ref, kp_frame, good):
        if len(good) < 4:
            return 0

        src_pts = np.float32([kp_ref[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp_frame[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)

        _H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, RANSAC_REPROJ_THRESH)
        if mask is None:
            return 0
        return int(mask.ravel().sum())

    def _load_references(self):
        print(f"\n  [MATCHER] Loading from: {PRODUCTS_DIR}")

        if not os.path.exists(PRODUCTS_DIR):
            os.makedirs(PRODUCTS_DIR, exist_ok=True)
            print("  [MATCHER] Created products folder — add reference images!")
            return

        for product in PRODUCT_DATABASE:
            loaded = 0
            for image_file in product["images"]:
                path = os.path.join(PRODUCTS_DIR, image_file)
                if not os.path.exists(path):
                    continue

                img = cv2.imread(path, cv2.IMREAD_COLOR)
                if img is None:
                    continue

                img = self._resize(img, FRAME_MAX_WIDTH)
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                kp, des = self.orb.detectAndCompute(gray, None)

                if des is None or kp is None or len(kp) < 30:
                    print(f"  [MATCHER] ✗ Not enough features: {image_file}")
                    continue

                self.references.append({
                    "name": product["name"],
                    "file": image_file,
                    "kp": kp,
                    "descriptors": des,
                    "num_features": len(kp),
                })
                loaded += 1

            if loaded:
                print(f"  [MATCHER] ✓ {product['name']}: {loaded} reference(s)")
            else:
                print(f"  [MATCHER] ✗ {product['name']}: NO references found")

        print(f"  [MATCHER] Total: {len(self.references)} reference images\n")

    def match(self, frame_rgb):
        if not self.orb or not self.references:
            return None

        frame_small = self._resize(frame_rgb, FRAME_MAX_WIDTH)
        gray = cv2.cvtColor(frame_small, cv2.COLOR_RGB2GRAY)

        if USE_BLUR_GATE and self._laplacian_var(gray) < MIN_LAPLACIAN_VAR:
            return None

        kp_frame, des_frame = self.orb.detectAndCompute(gray, None)
        if des_frame is None or kp_frame is None or len(kp_frame) < MIN_FRAME_KEYPOINTS:
            return None

        # Stage 1: compute "good match" counts for all refs (cheap)
        candidates = []
        for ref in self.references:
            try:
                good = self._good_matches(ref["descriptors"], des_frame)
                if len(good) < self.min_good_matches:
                    continue
                # preliminary key: good matches only
                prelim_key = len(good) * 1000.0 + (len(good) / ref["num_features"]) * 100.0
                candidates.append((prelim_key, ref, good))
            except Exception as e:
                logger.error(f"Match error: {e}")

        if not candidates:
            return None

        # Take top K by prelim score
        candidates.sort(key=lambda x: x[0], reverse=True)
        top = candidates[:max(1, TOPK_FOR_RANSAC)]

        # Stage 2: RANSAC on top K (expensive)
        scored = []
        for _prelim_key, ref, good in top:
            inliers = len(good)
            if USE_RANSAC:
                inliers = self._ransac_inliers(ref["kp"], kp_frame, good)
                if inliers < MIN_INLIERS:
                    continue

            score = (inliers / ref["num_features"]) * 100.0
            final_key = inliers * 1000.0 + score
            scored.append((final_key, ref, good, inliers, score))

        if not scored:
            return None

        scored.sort(key=lambda x: x[0], reverse=True)
        best = scored[0]
        second = scored[1] if len(scored) > 1 else None

        best_key, best_ref, best_good, best_inliers, best_score = best

        # Ambiguity reject (if we have a runner-up)
        if second is not None:
            second_key, _ref2, _good2, second_inliers, _score2 = second
            if (best_inliers < second_inliers + BEST_MARGIN_INLIERS) and (best_key < second_key * BEST_MARGIN_RATIO):
                return None

        return (best_ref["name"], best_score, len(best_good), best_inliers, best_ref["file"])


class RecognitionThread(QThread):
    product_detected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._lock = Lock()
        self._latest_frame = None

        self._scan_count = 0
        self._no_match_count = 0

        self._last_emitted = None
        self._candidate_name = None
        self._candidate_run = 0

        self.matcher = None

    def submit_frame(self, frame_array):
        with self._lock:
            self._latest_frame = frame_array

    def run(self):
        self._running = True
        self.matcher = ProductMatcher(min_good_matches=MIN_GOOD_MATCHES)

        if not self.matcher.references:
            print("\n  [WARN] No reference images!")
            print(f"  [WARN] Add images to: {PRODUCTS_DIR}/\n")

        print("=" * 55)
        print("  [SCAN] Recognition started — every 2 seconds")
        print("=" * 55)

        while self._running:
            for _ in range(20):
                if not self._running:
                    break
                self.msleep(100)

            if not self._running:
                break

            with self._lock:
                frame = self._latest_frame
                self._latest_frame = None

            if frame is not None:
                self._process_frame(frame)

    def _emit(self, name: str):
        self._last_emitted = name
        self.product_detected.emit(name)

    def _process_frame(self, frame_array):
        if not self.matcher or not self.matcher.references:
            return

        start = time.time()
        self._scan_count += 1
        result = self.matcher.match(frame_array)
        elapsed = time.time() - start

        if result:
            name, score, good, inliers, ref_file = result
            self._no_match_count = 0

            print(f"\n{'─' * 55}")
            print(f"  [SCAN #{self._scan_count}] ({elapsed:.2f}s)")
            print(f"  ✓ Match:     {name}")
            print(f"  ✓ Score:     {score:.1f}%")
            print(f"  ✓ Good:      {good} good matches")
            print(f"  ✓ Inliers:   {inliers} (RANSAC)")
            print(f"  ✓ Reference: {ref_file}")
            print(f"{'─' * 55}")

            # Debounce: require consecutive confirmations
            if name == self._candidate_name:
                self._candidate_run += 1
            else:
                self._candidate_name = name
                self._candidate_run = 1

            if self._candidate_run >= CONFIRM_CONSECUTIVE and name != self._last_emitted:
                print(f"  ★ DETECTED → {name}")
                self._emit(name)

        else:
            self._no_match_count += 1
            if self._no_match_count % 5 == 1:
                print(f"  [SCAN #{self._scan_count}] ({elapsed:.2f}s) — no match")

            if self._no_match_count >= CLEAR_CONSECUTIVE and self._last_emitted is not None:
                self._candidate_name = None
                self._candidate_run = 0
                print("  [SCAN] Product cleared")
                self._emit("No Product Detected")

    def stop(self):
        self._running = False
        self.wait(3000)
        print("  [SCAN] Stopped")

    def reset(self):
        with self._lock:
            self._latest_frame = None
        self._scan_count = 0
        self._no_match_count = 0
        self._last_emitted = None
        self._candidate_name = None
        self._candidate_run = 0
        print("  [SCAN] Reset")


class OCRModule:
    def __init__(self):
        self.thread = RecognitionThread()
        self.product_detected = self.thread.product_detected

        if CV2_AVAILABLE:
            print("[SCAN] Module ready (image matching)")
        else:
            print("[SCAN] WARNING: OpenCV not available")

    def start(self):
        if not self.thread.isRunning():
            self.thread.start()

    def stop(self):
        if self.thread.isRunning():
            self.thread.stop()

    def submit_frame(self, frame_array):
        self.thread.submit_frame(frame_array)

    def reset(self):
        self.thread.reset()
