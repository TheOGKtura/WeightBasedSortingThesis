import sys
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtCore import QTimer, Qt

from roles import ROLES
from wssgui import Ui_MainWindow
from sys_info import get_datetime, get_app_uptime
from login_dialog import LoginDialog

from pathlib import Path
#Call Logical Functions for Button and othet Stuff



#This Class calls the function inside of wss_gui1.py 
class MainWindow(QMainWindow):
    def __init__(self, role_key):
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.setAttribute(Qt.WA_AcceptTouchEvents, True)

        self.role_key = role_key
        self.role = ROLES[role_key]
        self.permissions = self.role["permissions"]
        self.apply_role_permissions()


        # \/ Toggle process for start
        self.is_running = False # <-- important variable to track state
        self.ui.pushButton_start.setCheckable(True)
        self.ui.pushButton_start.clicked.connect(self.toggle_start)

        #Change Page within the application
        self.ui.pushButton_analytics.clicked.connect(lambda: self.ui.stackedWidget_page_selector.setCurrentIndex(1))
        self.ui.pushButton_logistics.clicked.connect(lambda: self.ui.stackedWidget_page_selector.setCurrentIndex(2))
        self.ui.pushButton_back.clicked.connect(lambda: self.ui.stackedWidget_page_selector.setCurrentIndex(0))

        #Uptime and Datetime
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_info)
        self.timer.start(1000)  # update every second

        # Camera setup

    

    #Define the functions
    def apply_role_permissions(self):
        p = self.permissions

        self.ui.pushButton_settings.setEnabled(p["settings"])
        self.ui.pushButton_analytics.setEnabled(p["analytics"])
        self.ui.pushButton_logistics.setEnabled(p["logistics"])
        self.ui.pushButton_start.setEnabled(p["start"])

        
    def toggle_start(self):
        if not self.is_running:
            self.start_sys()
            self.ui.pushButton_start.setChecked(True)
            self.ui.pushButton_start.setText("Stop")
            self.ui.pushButton_start.setProperty("state", "stop")
            self.ui.label_operation_status.setText("Operating")
            self.is_running = True

            
            self.ui.pushButton_analytics.setEnabled(self.permissions["analytics"])
            self.ui.pushButton_logistics.setEnabled(self.permissions["logistics"])
        else:
            self.stop_sys()
            self.ui.pushButton_start.setChecked(False)
            self.ui.label_operation_status.setText("Idle")
            self.ui.pushButton_start.setText("Start")
            self.is_running = False

            self.ui.pushButton_analytics.setEnabled(self.permissions["analytics"])
            self.ui.pushButton_logistics.setEnabled(self.permissions["logistics"])


    def start_sys(self):
        print("Camera Here")

    def stop_sys(self):     
        print("Camera Out")

        
    def update_info(self):
        self.ui.label_time.setText(get_datetime()) 
        self.ui.label_runtime.setText(get_app_uptime())
        #when camera detect, add info


if __name__ == "__main__":
    app = QApplication(sys.argv)

    qss_path = Path(__file__).parent / "qss/style.qss"
    app.setStyleSheet(qss_path.read_text())

    login = LoginDialog()
    if login.exec() == LoginDialog.Accepted:
        window = MainWindow(login.role)
        window.show()
    sys.exit(app.exec())

