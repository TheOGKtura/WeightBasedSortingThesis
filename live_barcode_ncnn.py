#!/usr/bin/env python3
import argparse
import csv
import signal
import sys
import time
from dataclasses import dataclass
from typing import List, Tuple

import cv2
import ncnn
import numpy as np  

try:
    from picamera2 import Picamera2
except ImportError as exc:
    raise SystemExit(
        "picamera2 is required. Install with: pip install picamera2"
    ) from exc

try:
    from pyzbar.pyzbar import decode as zbar_decode
except ImportError as exc:
    raise SystemExit(
        "pyzbar is required. Install with: pip install pyzbar"
    ) from exc


@dataclass
class Detection:
    x1: int
    y1: int
    x2: int
    y2: int
    score: float
    cls_id: int = 0


class NcnnBarcodeDetector:
    def __init__(self, model_dir: str, input_size: Tuple[int, int] = (640, 640)):
        self.input_w, self.input_h = input_size
        self.net = ncnn.Net()
        self.net.load_param(f"{model_dir}/model.ncnn.param")
        self.net.load_model(f"{model_dir}/model.ncnn.bin")

    def _letterbox(self, image: np.ndarray) -> Tuple[np.ndarray, float, int, int]:
        h, w = image.shape[:2]
        scale = min(self.input_w / w, self.input_h / h)
        new_w, new_h = int(round(w * scale)), int(round(h * scale))

        resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        canvas = np.full((self.input_h, self.input_w, 3), 114, dtype=np.uint8)
        pad_x = (self.input_w - new_w) // 2
        pad_y = (self.input_h - new_h) // 2
        canvas[pad_y : pad_y + new_h, pad_x : pad_x + new_w] = resized
        return canvas, scale, pad_x, pad_y

    @staticmethod
    def _xywh_to_xyxy(xywh: np.ndarray) -> np.ndarray:
        out = np.empty_like(xywh)
        out[:, 0] = xywh[:, 0] - xywh[:, 2] / 2.0
        out[:, 1] = xywh[:, 1] - xywh[:, 3] / 2.0
        out[:, 2] = xywh[:, 0] + xywh[:, 2] / 2.0
        out[:, 3] = xywh[:, 1] + xywh[:, 3] / 2.0
        return out

    @staticmethod
    def _nms(boxes: np.ndarray, scores: np.ndarray, iou_thr: float) -> List[int]:
        x1 = boxes[:, 0]
        y1 = boxes[:, 1]
        x2 = boxes[:, 2]
        y2 = boxes[:, 3]
        areas = (x2 - x1).clip(min=0) * (y2 - y1).clip(min=0)
        order = scores.argsort()[::-1]

        keep: List[int] = []
        while order.size > 0:
            i = order[0]
            keep.append(int(i))

            xx1 = np.maximum(x1[i], x1[order[1:]])
            yy1 = np.maximum(y1[i], y1[order[1:]])
            xx2 = np.minimum(x2[i], x2[order[1:]])
            yy2 = np.minimum(y2[i], y2[order[1:]])

            w = np.maximum(0.0, xx2 - xx1)
            h = np.maximum(0.0, yy2 - yy1)
            inter = w * h
            union = areas[i] + areas[order[1:]] - inter + 1e-7
            iou = inter / union

            inds = np.where(iou <= iou_thr)[0]
            order = order[inds + 1]

        return keep

    @staticmethod
    def _as_n_by_c(raw: np.ndarray) -> np.ndarray:
        out = np.array(raw)
        out = np.squeeze(out)

        if out.ndim == 1:
            if out.size % 5 == 0:
                out = out.reshape(-1, 5)
            else:
                raise ValueError(f"Unexpected 1D output shape: {out.shape}")
        elif out.ndim == 2:
            if out.shape[1] in (5, 6):
                pass
            elif out.shape[0] in (5, 6):
                out = out.T
            elif out.shape[1] > 6 and out.shape[0] < out.shape[1]:
                out = out.T
        else:
            raise ValueError(f"Unexpected output shape: {out.shape}")

        return out.astype(np.float32)

    def detect(
        self,
        bgr: np.ndarray,
        conf_thr: float = 0.35,
        iou_thr: float = 0.45,
    ) -> List[Detection]:
        h0, w0 = bgr.shape[:2]
        letterbox, scale, pad_x, pad_y = self._letterbox(bgr)

        rgb = cv2.cvtColor(letterbox, cv2.COLOR_BGR2RGB)
        inp = rgb.astype(np.float32) / 255.0
        inp = np.transpose(inp, (2, 0, 1))

        ex = self.net.create_extractor()
        ex.input("in0", ncnn.Mat(inp).clone())
        _, out = ex.extract("out0")

        pred = self._as_n_by_c(np.array(out))
        if pred.shape[1] < 5:
            return []

        if pred.shape[1] == 5:
            boxes_xywh = pred[:, :4]
            scores = pred[:, 4]
            cls_ids = np.zeros((pred.shape[0],), dtype=np.int32)
        else:
            boxes_xywh = pred[:, :4]
            # YOLO head commonly exports [x, y, w, h, obj, cls0, cls1, ...].
            # Confidence is obj * best_class_prob, not just max over [obj, classes].
            objectness = pred[:, 4]
            cls_scores = pred[:, 5:]

            if cls_scores.shape[1] == 0:
                cls_ids = np.zeros((pred.shape[0],), dtype=np.int32)
                scores = objectness
            else:
                cls_ids = np.argmax(cls_scores, axis=1).astype(np.int32)
                best_cls = cls_scores[np.arange(cls_scores.shape[0]), cls_ids]
                scores = objectness * best_cls

        keep_conf = scores >= conf_thr
        if not np.any(keep_conf):
            return []

        boxes_xywh = boxes_xywh[keep_conf]
        scores = scores[keep_conf]
        cls_ids = cls_ids[keep_conf]

        boxes = self._xywh_to_xyxy(boxes_xywh)

        boxes[:, [0, 2]] -= pad_x
        boxes[:, [1, 3]] -= pad_y
        boxes /= scale

        boxes[:, [0, 2]] = boxes[:, [0, 2]].clip(0, w0 - 1)
        boxes[:, [1, 3]] = boxes[:, [1, 3]].clip(0, h0 - 1)

        keep = self._nms(boxes, scores, iou_thr)

        detections: List[Detection] = []
        for i in keep:
            x1, y1, x2, y2 = boxes[i]
            detections.append(
                Detection(
                    x1=int(x1),
                    y1=int(y1),
                    x2=int(x2),
                    y2=int(y2),
                    score=float(scores[i]),
                    cls_id=int(cls_ids[i]),
                )
            )

        return detections


def decode_barcode_roi(frame_bgr: np.ndarray, det: Detection) -> List[str]:
    x1, y1, x2, y2 = det.x1, det.y1, det.x2, det.y2
    if x2 <= x1 or y2 <= y1:
        return []

    roi = frame_bgr[y1:y2, x1:x2]
    if roi.size == 0:
        return []

    decoded = zbar_decode(roi)
    out: List[str] = []
    for item in decoded:
        text = item.data.decode("utf-8", errors="replace").strip()
        if text:
            out.append(f"{item.type}:{text}")
    return out


def decode_barcode_fullframe(frame_bgr: np.ndarray) -> List[Tuple[str, Tuple[int, int, int, int]]]:
    decoded = zbar_decode(frame_bgr)
    out: List[Tuple[str, Tuple[int, int, int, int]]] = []
    for item in decoded:
        text = item.data.decode("utf-8", errors="replace").strip()
        if not text:
            continue
        rect = item.rect
        x1 = int(rect.left)
        y1 = int(rect.top)
        x2 = int(rect.left + rect.width)
        y2 = int(rect.top + rect.height)
        out.append((f"{item.type}:{text}", (x1, y1, x2, y2)))
    return out


def decode_qr_fullframe(
    frame_bgr: np.ndarray, qr_detector: cv2.QRCodeDetector
) -> List[Tuple[str, Tuple[int, int, int, int]]]:
    out: List[Tuple[str, Tuple[int, int, int, int]]] = []

    # Prefer multi decode when available, fall back to single decode.
    try:
        ok, decoded_info, points, _ = qr_detector.detectAndDecodeMulti(frame_bgr)
    except Exception:
        ok, decoded_info, points = False, [], None

    if ok and points is not None and len(decoded_info) > 0:
        for text, quad in zip(decoded_info, points):
            text = (text or "").strip()
            if not text:
                continue
            q = np.array(quad, dtype=np.float32)
            x1 = int(np.min(q[:, 0]))
            y1 = int(np.min(q[:, 1]))
            x2 = int(np.max(q[:, 0]))
            y2 = int(np.max(q[:, 1]))
            out.append((f"QRCODE:{text}", (x1, y1, x2, y2)))
        return out

    text, points_single, _ = qr_detector.detectAndDecode(frame_bgr)
    text = (text or "").strip()
    if text and points_single is not None:
        q = np.array(points_single, dtype=np.float32).reshape(-1, 2)
        x1 = int(np.min(q[:, 0]))
        y1 = int(np.min(q[:, 1]))
        x2 = int(np.max(q[:, 0]))
        y2 = int(np.max(q[:, 1]))
        out.append((f"QRCODE:{text}", (x1, y1, x2, y2)))

    return out


def enhance_frame_clarity(frame_bgr: np.ndarray, amount: float) -> np.ndarray:
    if amount <= 0:
        return frame_bgr

    # Lightweight unsharp mask for clearer edges in preview and barcode ROI.
    blurred = cv2.GaussianBlur(frame_bgr, (0, 0), 1.1)
    return cv2.addWeighted(frame_bgr, 1.0 + amount, blurred, -amount, 0)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Live barcode detection + decode using NCNN and Picamera2"
    )
    parser.add_argument(
        "--model-dir",
        default="wssModel_ncnn_model",
        help="Folder with model.ncnn.param and model.ncnn.bin",
    )
    parser.add_argument("--conf", type=float, default=0.35, help="Confidence threshold")
    parser.add_argument("--iou", type=float, default=0.45, help="NMS IoU threshold")
    parser.add_argument("--width", type=int, default=640, help="Camera stream width")
    parser.add_argument("--height", type=int, default=640, help="Camera stream height")
    parser.add_argument(
        "--clarity",
        type=float,
        default=0.25,
        help="Software sharpening amount for preview/inference (0 disables)",
    )
    parser.add_argument(
        "--csv",
        default="barcode_results.csv",
        help="CSV file path to append decoded barcode results (set empty string to disable)",
    )
    parser.add_argument(
        "--expected",
        default="",
        help="Expected barcode text for live accuracy tracking",
    )
    parser.add_argument(
        "--metrics-every",
        type=int,
        default=30,
        help="Print live metrics every N frames",
    )
    parser.add_argument(
        "--scan-indicator-ms",
        type=int,
        default=1200,
        help="How long to show the SCANNED indicator after a successful decode",
    )
    parser.add_argument(
        "--fullframe-decode",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Fallback to full-frame pyzbar decode when ROI decode fails",
    )
    parser.add_argument(
        "--qr-fallback",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use OpenCV QRCodeDetector fallback when other decode paths fail",
    )
    args = parser.parse_args()

    detector = NcnnBarcodeDetector(args.model_dir)
    qr_detector = cv2.QRCodeDetector()

    picam2 = Picamera2()
    config = picam2.create_preview_configuration(
        main={"size": (args.width, args.height), "format": "RGB888"}
    )
    picam2.configure(config)

    # Attempt continuous autofocus and mild contrast/sharpness tuning.
    try:
        picam2.set_controls({
            "AfMode": 2,
            "AeEnable": True,
            "AwbEnable": True,
            "Contrast": 1.1,
            "Sharpness": 1.6,
        })
    except Exception as exc:
        print(f"Warning: could not apply camera controls: {exc}")

    picam2.start()

    print("Press q in the preview window to quit.")
    window_name = "NCNN Barcode Live Test"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    running = True

    def handle_signal(signum, _frame):
        nonlocal running
        running = False
        print(f"Received signal {signum}, shutting down...")

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    seen = set()
    prev_t = time.time()
    csv_file = None
    csv_writer = None
    frame_idx = 0

    # Live metrics. These are task-appropriate for barcode detection/decoding.
    total_detections = 0
    total_decoded = 0
    correct_decoded = 0
    false_decoded = 0
    last_scan_ts = 0.0
    last_scan_text = ""

    if args.csv:
        csv_file = open(args.csv, "a", newline="", encoding="utf-8")
        csv_writer = csv.writer(csv_file)
        print(f"CSV logging enabled: {args.csv}")
        if csv_file.tell() == 0:
            csv_writer.writerow(
                [
                    "timestamp",
                    "symbology",
                    "barcode_text",
                    "score",
                    "x1",
                    "y1",
                    "x2",
                    "y2",
                ]
            )
            csv_file.flush()

    try:
        while running:
            rgb = picam2.capture_array()
            frame = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            frame = enhance_frame_clarity(frame, args.clarity)
            frame_idx += 1

            detections = detector.detect(frame, conf_thr=args.conf, iou_thr=args.iou)
            total_detections += len(detections)
            decoded_labels: List[str] = []
            ff_hits: List[Tuple[str, Tuple[int, int, int, int]]] = []
            qr_hits: List[Tuple[str, Tuple[int, int, int, int]]] = []

            for det in detections:
                decoded = decode_barcode_roi(frame, det)
                if decoded:
                    decoded_labels.extend(decoded)
                    for item in decoded:
                        total_decoded += 1
                        if csv_writer is not None:
                            symbology, text = item.split(":", 1)
                            csv_writer.writerow(
                                [
                                    time.strftime("%Y-%m-%d %H:%M:%S"),
                                    symbology,
                                    text,
                                    f"{det.score:.4f}",
                                    det.x1,
                                    det.y1,
                                    det.x2,
                                    det.y2,
                                ]
                            )
                            csv_file.flush()

                        if args.expected:
                            expected = args.expected.strip()
                            actual = item.split(":", 1)[1].strip()
                            if actual == expected:
                                correct_decoded += 1
                            else:
                                false_decoded += 1

                        if item not in seen:
                            seen.add(item)
                            print(f"[{time.strftime('%H:%M:%S')}] {item}")

                        last_scan_ts = time.time()
                        last_scan_text = item

                cv2.rectangle(frame, (det.x1, det.y1), (det.x2, det.y2), (0, 255, 0), 2)
                label = f"barcode {det.score:.2f}"
                if decoded:
                    label += f" | {decoded[0]}"
                cv2.putText(
                    frame,
                    label,
                    (det.x1, max(20, det.y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (0, 255, 0),
                    2,
                    cv2.LINE_AA,
                )

            if args.fullframe_decode and not decoded_labels:
                ff_hits = decode_barcode_fullframe(frame)
                for item, (x1, y1, x2, y2) in ff_hits:
                    total_decoded += 1

                    if csv_writer is not None:
                        symbology, text = item.split(":", 1)
                        csv_writer.writerow(
                            [
                                time.strftime("%Y-%m-%d %H:%M:%S"),
                                symbology,
                                text,
                                "1.0000",
                                x1,
                                y1,
                                x2,
                                y2,
                            ]
                        )
                        csv_file.flush()

                    if args.expected:
                        expected = args.expected.strip()
                        actual = item.split(":", 1)[1].strip()
                        if actual == expected:
                            correct_decoded += 1
                        else:
                            false_decoded += 1

                    if item not in seen:
                        seen.add(item)
                        print(f"[{time.strftime('%H:%M:%S')}] {item} (full-frame)")

                    last_scan_ts = time.time()
                    last_scan_text = item

            if args.qr_fallback and not decoded_labels and not ff_hits:
                qr_hits = decode_qr_fullframe(frame, qr_detector)
                for item, (x1, y1, x2, y2) in qr_hits:
                    total_decoded += 1

                    if csv_writer is not None:
                        symbology, text = item.split(":", 1)
                        csv_writer.writerow(
                            [
                                time.strftime("%Y-%m-%d %H:%M:%S"),
                                symbology,
                                text,
                                "1.0000",
                                x1,
                                y1,
                                x2,
                                y2,
                            ]
                        )
                        csv_file.flush()

                    if args.expected:
                        expected = args.expected.strip()
                        actual = item.split(":", 1)[1].strip()
                        if actual == expected:
                            correct_decoded += 1
                        else:
                            false_decoded += 1

                    if item not in seen:
                        seen.add(item)
                        print(f"[{time.strftime('%H:%M:%S')}] {item} (opencv-qr)")

                    last_scan_ts = time.time()
                    last_scan_text = item

            for item, (x1, y1, x2, y2) in ff_hits:
                cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 180, 0), 2)
                cv2.putText(
                    frame,
                    f"zbar {item}",
                    (x1, max(20, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (255, 180, 0),
                    2,
                    cv2.LINE_AA,
                )

            for item, (x1, y1, x2, y2) in qr_hits:
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 180, 255), 2)
                cv2.putText(
                    frame,
                    f"qr {item}",
                    (x1, max(20, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 180, 255),
                    2,
                    cv2.LINE_AA,
                )

            now = time.time()
            fps = 1.0 / max(1e-6, now - prev_t)
            prev_t = now
            cv2.putText(
                frame,
                f"FPS: {fps:.1f} | detections: {len(detections)}",
                (10, 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 255, 255),
                2,
                cv2.LINE_AA,
            )

            if args.expected:
                decode_acc = (correct_decoded / max(1, total_decoded)) * 100.0
                cv2.putText(
                    frame,
                    f"expected: {args.expected} | decode acc: {decode_acc:.1f}%",
                    (10, 56),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (255, 255, 0),
                    2,
                    cv2.LINE_AA,
                )

            if args.expected and args.metrics_every > 0 and frame_idx % args.metrics_every == 0:
                decode_acc = (correct_decoded / max(1, total_decoded)) * 100.0
                print(
                    "[metrics] "
                    f"frames={frame_idx} "
                    f"detections={total_detections} "
                    f"decoded={total_decoded} "
                    f"correct={correct_decoded} "
                    f"false={false_decoded} "
                    f"decode_acc={decode_acc:.2f}%"
                )

            if (time.time() - last_scan_ts) * 1000.0 <= max(0, args.scan_indicator_ms):
                cv2.rectangle(frame, (10, 70), (min(620, args.width - 10), 120), (0, 120, 0), -1)
                cv2.putText(
                    frame,
                    "SCANNED",
                    (20, 104),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1.0,
                    (255, 255, 255),
                    2,
                    cv2.LINE_AA,
                )
                if last_scan_text:
                    short_text = last_scan_text
                    if len(short_text) > 42:
                        short_text = short_text[:39] + "..."
                    cv2.putText(
                        frame,
                        short_text,
                        (170, 104),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.55,
                        (255, 255, 255),
                        2,
                        cv2.LINE_AA,
                    )

            try:
                cv2.imshow(window_name, frame)

                # Handle window close button (X) in addition to keyboard quit.
                if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                    break
            except cv2.error:
                # Some desktop stacks can raise on destroyed window.
                break

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break

    except KeyboardInterrupt:
        pass

    finally:
        try:
            picam2.stop()
        except Exception:
            pass
        try:
            picam2.close()
        except Exception:
            pass
        if csv_file is not None:
            csv_file.close()
        try:
            cv2.destroyWindow(window_name)
        except Exception:
            pass
        cv2.destroyAllWindows()
        cv2.waitKey(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
