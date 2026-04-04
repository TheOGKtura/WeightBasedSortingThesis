"""
Barcode Scanner Module — detects and decodes barcodes using NCNN
Extracts barcode ROI and saves successful scans to local storage.
"""

import os
import time
import logging
import csv
import cv2
import numpy as np
from dataclasses import dataclass
from typing import List, Tuple, Optional
from threading import Lock
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    import ncnn
    NCNN_AVAILABLE = True
except ImportError:
    NCNN_AVAILABLE = False
    logger.warning("ncnn not installed. Run: pip install ncnn")

try:
    from pyzbar.pyzbar import decode as zbar_decode
    PYZBAR_AVAILABLE = True
except ImportError:
    PYZBAR_AVAILABLE = False
    logger.warning("pyzbar not installed. Run: pip install pyzbar")

from PySide6.QtCore import QThread, Signal


@dataclass
class Detection:
    x1: int
    y1: int
    x2: int
    y2: int
    score: float
    cls_id: int = 0


class NcnnBarcodeDetector:
    """NCNN-based barcode detector"""
    
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
    """Decode barcode in ROI"""
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
    """Full-frame fallback barcode decode"""
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


class BarcodeScanner(QThread):
    """Background thread for barcode detection and decoding"""
    
    barcode_detected = Signal(str)  # Emits: "SYMBOLOGY:VALUE"
    barcode_frame_ready = Signal(np.ndarray)  # Emits frame for saving
    detection_completed = Signal()

    def __init__(self, model_dir: str = "wssModel_ncnn_model", parent=None):
        super().__init__(parent)
        self.model_dir = model_dir
        self.detector = None
        self._running = False
        self._lock = Lock()
        self._frame_queue = []
        self._csv_file = None
        self._csv_writer = None
        self._seen_barcodes = set()

        if NCNN_AVAILABLE:
            try:
                self.detector = NcnnBarcodeDetector(model_dir)
                logger.info(f"NCNN Barcode Detector initialized with {model_dir}")
            except Exception as e:
                logger.error(f"Failed to initialize NCNN detector: {e}")
        else:
            logger.warning("NCNN not available - barcode detection disabled")

    def add_frame(self, frame_bgr: np.ndarray):
        """Add frame to processing queue"""
        with self._lock:
            if len(self._frame_queue) > 5:  # Keep queue manageable
                self._frame_queue.pop(0)
            self._frame_queue.append(frame_bgr.copy())

    def run(self):
        """Main processing loop"""
        self._running = True
        logger.info("BarcodeScanner thread started")

        while self._running:
            frame = None
            with self._lock:
                if self._frame_queue:
                    frame = self._frame_queue.pop(0)

            if frame is not None:
                try:
                    self._process_frame(frame)
                except Exception as e:
                    logger.error(f"Error processing frame: {e}")

            self.msleep(50)  # ~20 fps processing

        logger.info("BarcodeScanner thread stopped")

    def _process_frame(self, frame_bgr: np.ndarray):
        """Process a single frame for barcode detection"""
        if not NCNN_AVAILABLE or not self.detector:
            return

        try:
            detections = self.detector.detect(frame_bgr, conf_thr=0.35, iou_thr=0.45)
            if not detections:
                # Try full frame fallback
                if PYZBAR_AVAILABLE:
                    ff_hits = decode_barcode_fullframe(frame_bgr)
                    for barcode_text, (x1, y1, x2, y2) in ff_hits:
                        if barcode_text not in self._seen_barcodes:
                            self._seen_barcodes.add(barcode_text)
                            logger.info(f"Barcode detected (full-frame): {barcode_text}")
                            self.barcode_detected.emit(barcode_text)
                            self.barcode_frame_ready.emit(frame_bgr.copy())
                return

            # Process ROI detections
            for det in detections:
                decoded = decode_barcode_roi(frame_bgr, det)
                if decoded:
                    for barcode_text in decoded:
                        if barcode_text not in self._seen_barcodes:
                            self._seen_barcodes.add(barcode_text)
                            logger.info(f"Barcode detected (NCNN ROI): {barcode_text}")
                            self.barcode_detected.emit(barcode_text)
                            self.barcode_frame_ready.emit(frame_bgr.copy())

        except Exception as e:
            logger.error(f"Error in barcode detection: {e}")

    def stop(self):
        """Stop the scanner thread"""
        self._running = False
        if self._csv_file:
            self._csv_file.close()
        self.wait(5000)

    def clear_seen_barcodes(self):
        """Clear the set of seen barcodes (for testing)"""
        with self._lock:
            self._seen_barcodes.clear()
