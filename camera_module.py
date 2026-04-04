"""
PiCamera2 module — streams video into a QLabel inside frame_camera.
Sends frames to OCR module without blocking UI.
Integrates barcode scanning for live detection.
Falls back to a placeholder if the camera is unavailable.
"""

import os
import logging
import time
import cv2
import numpy as np
from dataclasses import dataclass
from threading import Lock
from typing import List, Tuple
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QImage, QPixmap, QFont
from PySide6.QtWidgets import QLabel, QVBoxLayout

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

try:
    import ncnn
    NCNN_AVAILABLE = True
except ImportError as e:
    NCNN_AVAILABLE = False
    logger.warning(f"ncnn not available: {e}")

try:
    from pyzbar.pyzbar import decode as zbar_decode
    PYZBAR_AVAILABLE = True
except ImportError as e:
    PYZBAR_AVAILABLE = False
    logger.warning(f"pyzbar not available: {e}")


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

    def detect(self, bgr: np.ndarray, conf_thr: float = 0.35, iou_thr: float = 0.45) -> List[Detection]:
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

try:
    from picamera2 import Picamera2
    PICAMERA_AVAILABLE = True
    logger.info("picamera2 imported successfully.")
except ImportError as e:
    PICAMERA_AVAILABLE = False
    logger.warning(f"picamera2 not available: {e}")
except Exception as e:
    PICAMERA_AVAILABLE = False
    logger.warning(f"picamera2 import error: {e}")


class CameraThread(QThread):
    """Captures frames in a background thread, emits QImage only."""
    frame_ready = Signal(QImage)
    barcode_detected = Signal(str)
    barcode_frame_ready = Signal(np.ndarray)
    error_occurred = Signal(str)

    def __init__(self, model_dir="wssModel_ncnn_model", resolution=(640, 640), rotation=90, lens_position=None, parent=None):
        super().__init__(parent)
        self.resolution = resolution
        self.rotation = rotation  # 0, 90, 180, 270
        self.lens_position = lens_position  # 0.0-5.0 focus distance, or None for autofocus
        self._running = False
        self.picam = None
        self._frame_count = 0
        self._barcode_detector = None
        self._seen_barcodes = set()
        self._debug_scanner = os.environ.get("BARCODE_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"}
        self._last_debug_ts = 0.0
        try:
            self._barcode_detector = NcnnBarcodeDetector(model_dir)
        except Exception as exc:
            logger.warning(f"Barcode detector unavailable: {exc}")

    def _rotate_image(self, array, rotation):
        """Rotate image array by 90, 180, or 270 degrees"""
        if rotation == 0:
            return array
        elif rotation == 90:
            return cv2.rotate(array, cv2.cv2.ROTATE_90_CLOCKWISE)
        elif rotation == 180:
            return cv2.rotate(array, cv2.ROTATE_180)
        elif rotation == 270:
            return cv2.rotate(array, cv2.ROTATE_90_COUNTERCLOCKWISE)
        else:
            logger.warning(f"Invalid rotation {rotation}. Using 0.")
            return array

    @staticmethod
    def _enhance_frame_clarity(frame_bgr: np.ndarray, clarity_amount: float) -> np.ndarray:
        """Apply unsharp masking for clearer barcode edges."""
        if clarity_amount <= 0:
            return frame_bgr
        
        blurred = cv2.GaussianBlur(frame_bgr, (0, 0), 1.1)
        return cv2.addWeighted(frame_bgr, 1.0 + clarity_amount, blurred, -clarity_amount, 0)

    def run(self):
        try:
            self.picam = Picamera2()
            logger.info(f"Camera sensor modes: {self.picam.sensor_modes}")

            config = self.picam.create_preview_configuration(
                main={"size": self.resolution, "format": "RGB888"}
            )
            self.picam.configure(config)

            # Favor autofocus and a sharper preview for barcode reading.
            camera_controls = {
                "AfMode": 2,
                "AeEnable": True,
                "AwbEnable": True,
                "Sharpness": 1.8,
                "Contrast": 1.1,
                "Brightness": 0.02,
            }
            if self.lens_position is not None:
                camera_controls["LensPosition"] = self.lens_position
            self.picam.set_controls(camera_controls)

            self.picam.start()
            self._running = True
            logger.info(f"Camera started at {self.resolution} with LensPosition={self.lens_position}")

            # Trigger autofocus once on startup when supported.
            try:
                self.picam.autofocus_cycle()
                self.msleep(500)
                logger.info("Autofocus cycle completed.")
            except Exception as e:
                logger.warning(f"Autofocus cycle failed: {e}")

            while self._running:
                try:
                    array = self.picam.capture_array()
                    
                    # Apply rotation via OpenCV
                    if self.rotation != 0:
                        array = self._rotate_image(array, self.rotation)
                    
                    # Make sure array is contiguous in memory
                    array = np.ascontiguousarray(array)
                    
                    h, w, ch = array.shape
                    bytes_per_line = ch * w

                    # Work in BGR (model expects 3-channel color input)
                    bgr_array = cv2.cvtColor(array, cv2.COLOR_RGB2BGR)
                    
                    # Apply frame clarity enhancement (unsharp mask for better barcode edges)
                    bgr_array = self._enhance_frame_clarity(bgr_array, clarity_amount=0.25)

                    # Decode barcode directly from the live frame so the scanner stays in sync.
                    if self._barcode_detector is not None:
                        detections = self._barcode_detector.detect(bgr_array, conf_thr=0.35, iou_thr=0.45)

                        hits = []
                        if detections:
                            for det in detections:
                                # Always draw detector ROI so users can see scan candidates.
                                cv2.rectangle(
                                    bgr_array,
                                    (det.x1, det.y1),
                                    (det.x2, det.y2),
                                    (0, 255, 255),
                                    2,
                                )
                                cv2.putText(
                                    bgr_array,
                                    f"det {det.score:.2f}",
                                    (det.x1, max(20, det.y1 - 8)),
                                    cv2.FONT_HERSHEY_SIMPLEX,
                                    0.45,
                                    (0, 255, 255),
                                    1,
                                    cv2.LINE_AA,
                                )

                                decoded = decode_barcode_roi(bgr_array, det)
                                if decoded:
                                    hits.extend(decoded)
                                    cv2.rectangle(
                                        bgr_array,
                                        (det.x1, det.y1),
                                        (det.x2, det.y2),
                                        (0, 255, 0),
                                        2,
                                    )
                                    cv2.putText(
                                        bgr_array,
                                        decoded[0],
                                        (det.x1, max(20, det.y1 - 8)),
                                        cv2.FONT_HERSHEY_SIMPLEX,
                                        0.5,
                                        (0, 255, 0),
                                        2,
                                        cv2.LINE_AA,
                                    )
                        else:
                            ff_hits = decode_barcode_fullframe(bgr_array)
                            hits.extend([item for item, _bbox in ff_hits])
                            for item, (x1, y1, x2, y2) in ff_hits:
                                cv2.rectangle(bgr_array, (x1, y1), (x2, y2), (255, 180, 0), 2)
                                cv2.putText(
                                    bgr_array,
                                    item,
                                    (x1, max(20, y1 - 8)),
                                    cv2.FONT_HERSHEY_SIMPLEX,
                                    0.5,
                                    (255, 180, 0),
                                    2,
                                    cv2.LINE_AA,
                                )

                        if self._debug_scanner and (time.time() - self._last_debug_ts) >= 1.0:
                            logger.info(
                                "[BARCODE_DEBUG] detections=%d hits=%d seen=%d",
                                len(detections),
                                len(hits),
                                len(self._seen_barcodes),
                            )
                            self._last_debug_ts = time.time()

                        for barcode_text in hits:
                            if barcode_text not in self._seen_barcodes:
                                self._seen_barcodes.add(barcode_text)
                                self.barcode_detected.emit(barcode_text)
                                self.barcode_frame_ready.emit(bgr_array.copy())
                    else:
                        ff_hits = decode_barcode_fullframe(bgr_array)
                        for barcode_text, (x1, y1, x2, y2) in ff_hits:
                            cv2.rectangle(bgr_array, (x1, y1), (x2, y2), (255, 180, 0), 2)
                            cv2.putText(
                                bgr_array,
                                barcode_text,
                                (x1, max(20, y1 - 8)),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.5,
                                (255, 180, 0),
                                2,
                                cv2.LINE_AA,
                            )
                            if barcode_text not in self._seen_barcodes:
                                self._seen_barcodes.add(barcode_text)
                                self.barcode_detected.emit(barcode_text)
                                self.barcode_frame_ready.emit(bgr_array.copy())

                    # OCR processing disabled (placeholder)
                    # Frames will not be submitted to OCR module
                    self._frame_count += 1

                    # Send QImage to main thread for display (as RGB for Qt)
                    preview_rgb = cv2.cvtColor(bgr_array, cv2.COLOR_BGR2RGB)
                    qimg = QImage(
                        preview_rgb.data, w, h, bytes_per_line,
                        QImage.Format_RGB888
                    )
                    self.frame_ready.emit(qimg.copy())

                except Exception as e:
                    logger.error(f"Frame capture error: {e}")

                self.msleep(33)  # ~30 fps

        except Exception as e:
            error_msg = f"Camera init failed: {e}"
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
        finally:
            self._cleanup()

    def _cleanup(self):
        try:
            if self.picam:
                self.picam.stop()
                self.picam.close()
                logger.info("Camera closed.")
        except Exception as e:
            logger.error(f"Camera cleanup error: {e}")

    def stop(self):
        self._running = False
        self.wait(5000)


class CameraModule:
    """
    Manages the camera lifecycle and OCR scanning.
    Call start() after login, stop() on logout.
    """

    def __init__(self, frame_camera, barcode_callback=None, barcode_frame_callback=None, rotation=0, lens_position=None, model_dir="wssModel_ncnn_model"):
        self.frame_camera = frame_camera
        self.rotation = rotation  # Camera rotation: 0, 90, 180, 270
        self.lens_position = lens_position  # Focus distance: 0.0-5.0
        self.model_dir = model_dir

        self.video_label = QLabel(frame_camera)
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setStyleSheet("background-color: #000000;")

        if frame_camera.layout():
            old_layout = frame_camera.layout()
            while old_layout.count():
                old_layout.takeAt(0)
        else:
            layout = QVBoxLayout(frame_camera)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self.video_label)

        self.thread = None

        self._barcode_callback = barcode_callback
        self._barcode_frame_callback = barcode_frame_callback

        if not PICAMERA_AVAILABLE:
            self._show_placeholder("Camera not available\n(picamera2 not installed)")

    def start(self):
        if not PICAMERA_AVAILABLE:
            self._show_placeholder("Camera not available\n(picamera2 not installed)")
            return

        if self.thread and self.thread.isRunning():
            return

        self._show_placeholder("Starting camera...")

        self.thread = CameraThread(
            model_dir=self.model_dir,
            resolution=(640, 640),
            rotation=self.rotation,
            lens_position=self.lens_position
        )
        self.thread.frame_ready.connect(self._update_frame)
        if self._barcode_callback:
            self.thread.barcode_detected.connect(self._barcode_callback)
        if self._barcode_frame_callback:
            self.thread.barcode_frame_ready.connect(self._barcode_frame_callback)
        self.thread.error_occurred.connect(self._on_error)
        self.thread.start()

    def stop(self):
        if self.thread and self.thread.isRunning():
            self.thread.stop()
            self.thread = None
        self._show_placeholder("Camera stopped")

    def _update_frame(self, qimg: QImage):
        size = self.video_label.size()
        pixmap = QPixmap.fromImage(qimg).scaled(
            size, Qt.KeepAspectRatio, Qt.FastTransformation
        )
        self.video_label.setPixmap(pixmap)

    def _on_error(self, error_msg: str):
        logger.error(f"Camera error: {error_msg}")
        self._show_placeholder(f"Camera Error:\n{error_msg}")

    def _show_placeholder(self, text: str):
        self.video_label.clear()
        self.video_label.setText(text)
        self.video_label.setFont(QFont("Segoe UI", 12))
        self.video_label.setStyleSheet(
            "background-color: #1a1a2e; color: #ecf0f1; padding: 10px;"
        )

