from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal, Slot
import paho.mqtt.client as mqtt


@dataclass(frozen=True)
class RelayMqttConfig:
    host: str
    port: int = 1883
    topic_set: str = "relay/1/set"
    topic_state: str = "relay/1/state"
    client_id: str = "pyside6-relay-gui"
    keepalive: int = 30
    reconnect_delay_s: float = 2.0


@dataclass(frozen=True)
class RelayCommandMapping:
    """
    Your hardware is inverted:
      - relay OFF => machine powered (RUN)
      - relay ON  => power cut (STOP)

    So:
      RUN  publishes payload_run (default "OFF")
      STOP publishes payload_stop (default "ON")
    """
    payload_run: str = "OFF"
    payload_stop: str = "ON"


class RelayMqttController(QObject):
    status_changed = Signal(str)     # human status text
    relay_state_changed = Signal(str) # raw state payload from topic_state
    connected_changed = Signal(bool)

    def __init__(self, cfg: RelayMqttConfig, mapping: RelayCommandMapping | None = None):
        super().__init__()
        self.cfg = cfg
        self.mapping = mapping or RelayCommandMapping()

        self._connected = False
        self._thread: threading.Thread | None = None
        self._stop_requested = False

        self.client = mqtt.Client(client_id=self.cfg.client_id)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

    @Slot()
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_requested = False
        self._thread = threading.Thread(target=self._mqtt_worker, daemon=True)
        self._thread.start()

    @Slot()
    def stop(self) -> None:
        self._stop_requested = True
        try:
            self.client.disconnect()
        except Exception:
            pass

    @Slot()
    def run(self) -> bool:
        return self._publish(self.mapping.payload_run)

    @Slot()
    def stop_power(self) -> bool:
        return self._publish(self.mapping.payload_stop)

    @Slot(str)
    def publish_raw(self, payload: str) -> bool:
        return self._publish(payload)

    # ----- internal -----

    def _set_connected(self, v: bool) -> None:
        if self._connected == v:
            return
        self._connected = v
        self.connected_changed.emit(v)

    def _mqtt_worker(self) -> None:
        while not self._stop_requested:
            try:
                self.status_changed.emit(f"MQTT: connecting to {self.cfg.host}:{self.cfg.port} ...")
                self.client.connect(self.cfg.host, self.cfg.port, keepalive=self.cfg.keepalive)
                self.client.loop_forever(retry_first_connection=True)
            except Exception as e:
                self.status_changed.emit(f"MQTT: error: {e}")
                self._set_connected(False)

            if not self._stop_requested:
                self.status_changed.emit("MQTT: retrying connection...")
                time.sleep(max(0.5, float(self.cfg.reconnect_delay_s)))

    def _publish(self, payload: str) -> bool:
        if not self._connected:
            self.status_changed.emit("MQTT: not connected (can't publish)")
            return False
        try:
            info = self.client.publish(self.cfg.topic_set, payload, qos=1, retain=False)
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                self.status_changed.emit(f"MQTT publish failed (rc={info.rc})")
                return False
            info.wait_for_publish(timeout=1.5)
            if not info.is_published():
                self.status_changed.emit("MQTT publish timeout")
                return False
            return True
        except Exception as e:
            self.status_changed.emit(f"MQTT publish error: {e}")
            return False

    # MQTT callbacks (run in MQTT thread)
    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self.status_changed.emit("MQTT: connected")
            self._set_connected(True)
            client.subscribe(self.cfg.topic_state)
        else:
            self.status_changed.emit(f"MQTT: connect failed (rc={rc})")
            self._set_connected(False)

    def _on_disconnect(self, client, userdata, rc, properties=None, reasonCode=None):
        if self._stop_requested:
            self.status_changed.emit("MQTT: disconnected")
        else:
            self.status_changed.emit(f"MQTT: disconnected (rc={rc})")
        self._set_connected(False)

    def _on_message(self, client, userdata, msg):
        if msg.topic == self.cfg.topic_state:
            payload = msg.payload.decode("utf-8", errors="replace").strip()
            self.relay_state_changed.emit(payload)