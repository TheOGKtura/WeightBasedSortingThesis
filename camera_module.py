"""
PiCamera2 module — streams video into a QLabel inside frame_camera.
Sends frames to OCR module without blocking UI.
Falls back to a placeholder if the camera is unavailable.
"""

import os
import logging
import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QImage, QPixmap, QFont
from PySide6.QtWidgets import QLabel, QVBoxLayout

from ocr_module import OCRModule

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

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
    error_occurred = Signal(str)

    def __init__(self, ocr_module, resolution=(1280, 720), rotation=90, lens_position=0.0, parent=None):
        super().__init__(parent)
        self.resolution = resolution
        self.rotation = rotation  # 0, 90, 180, 270
        self.lens_position = lens_position  # 0.0-5.0 focus distance
        self.ocr = ocr_module
        self._running = False
        self.picam = None
        self._frame_count = 0

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

    def run(self):
        try:
            self.picam = Picamera2()
            logger.info(f"Camera sensor modes: {self.picam.sensor_modes}")

            config = self.picam.create_preview_configuration(
                main={"size": self.resolution, "format": "RGB888"}
            )
            self.picam.configure(config)

            # Set focus distance and other controls
            self.picam.set_controls({
                "AfMode": 1,  # Manual focus mode
                "LensPosition": self.lens_position,  # Adjustable focus distance
                "AwbEnable": True,
                "AwbMode": 0,
                "ColourGains": (0, 0),
            })

            self.picam.start()
            self._running = True
            logger.info(f"Camera started at {self.resolution} with LensPosition={self.lens_position}")

            # Single autofocus trigger on startup
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

                    # Submit to OCR every 10th frame
                    self._frame_count += 1
                    if self._frame_count % 10 == 0:
                        self.ocr.submit_frame(array.copy())

                    # Send QImage to main thread for display
                    qimg = QImage(
                        array.data, w, h, bytes_per_line,
                        QImage.Format_RGB888
                    ).rgbSwapped()
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

    def __init__(self, frame_camera, ocr_callback=None, rotation=0, lens_position=0.0):
        self.frame_camera = frame_camera
        self.rotation = rotation  # Camera rotation: 0, 90, 180, 270
        self.lens_position = lens_position  # Focus distance: 0.0-5.0

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

        # OCR runs on its own thread
        self.ocr = OCRModule()
        if ocr_callback:
            self.ocr.product_detected.connect(ocr_callback)

        if not PICAMERA_AVAILABLE:
            self._show_placeholder("Camera not available\n(picamera2 not installed)")

    def start(self):
        if not PICAMERA_AVAILABLE:
            self._show_placeholder("Camera not available\n(picamera2 not installed)")
            return

        if self.thread and self.thread.isRunning():
            return

        self._show_placeholder("Starting camera...")

        self.ocr.reset()
        self.ocr.start()

        # Pass OCR module directly to camera thread with rotation and focus
        self.thread = CameraThread(
            ocr_module=self.ocr,
            resolution=(1280, 720),
            rotation=self.rotation,
            lens_position=self.lens_position
        )
        self.thread.frame_ready.connect(self._update_frame)
        self.thread.error_occurred.connect(self._on_error)
        self.thread.start()

    def stop(self):
        self.ocr.stop()
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

