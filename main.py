import sys
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtCore import QTimer, Qt
from wssgui import Ui_MainWindow
from sys_info import get_datetime, get_app_uptime
#Call Logical Functions for Button and othet Stuff
#This Class calls the function inside of wss_gui1.py 
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.setAttribute(Qt.WA_AcceptTouchEvents, True)

        # \/ Toggle process for start
        self.is_running = False
        self.ui.pushButton_start.clicked.connect(self.toggle_start)
        #Change Page within the application
        self.ui.pushButton_analytics.clicked.connect(lambda: self.ui.stackedWidget_page_selector.setCurrentIndex(1))
        self.ui.pushButton_logistics.clicked.connect(lambda: self.ui.stackedWidget_page_selector.setCurrentIndex(2))
        self.ui.pushButton_back.clicked.connect(lambda: self.ui.stackedWidget_page_selector.setCurrentIndex(0))

        #Uptime and Datetime
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_info)
        self.timer.start(1000)  # update every second
    

    #Define the functions
    def toggle_start(self):
        if not self.is_running:
            self.start_sys()
            self.ui.pushButton_start.setText("Stop")
            self.ui.label_operation_status.setText("Operating")
            self.is_running = True
        else:
            self.stop_sys()
            self.ui.label_operation_status.setText("Idle")
            self.ui.pushButton_start.setText("Start")
            self.is_running = False

    def start_sys(self):

        print("Camera Here")

    def stop_sys(self):
        print("Camera Out")

    def update_info(self):
        self.ui.label_time.setText(get_datetime()) 
        self.ui.label_runtime.setText(get_app_uptime())

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

