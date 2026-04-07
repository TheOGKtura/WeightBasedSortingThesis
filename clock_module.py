"""
Real-time system clock — updates label_uptime and label_date every second.
"""

from PySide6.QtCore import QTimer, QDateTime


class ClockModule:
    """
    Updates two QLabels with live time and date.
    Call start() once after UI is ready.
    """

    def __init__(self, label_uptime, label_date):
        self.label_uptime = label_uptime
        self.label_date = label_date

        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)

    def start(self):
        self._tick()  # immediate first update
        self.timer.start(1000)

    def stop(self):
        self.timer.stop()

    def _tick(self):
        now = QDateTime.currentDateTime()
        self.label_uptime.setText(now.toString("hh:mm:ss"))
        self.label_uptime.adjustSize()
        self.label_date.setText(now.toString("yyyy-MM-dd"))
        self.label_date.adjustSize()