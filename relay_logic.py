from dataclasses import dataclass

@dataclass(frozen=True)
class RelayMapping:
    # Inverted relay wiring:
    # relay OFF => machine has power (RUN)
    # relay ON  => power cut (STOP)
    payload_for_run: str = "OFF"
    payload_for_stop: str = "ON"