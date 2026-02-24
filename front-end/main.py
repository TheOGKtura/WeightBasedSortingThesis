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
    
    WORK_HOURS_OPTIONS = [2, 4, 6, 8]  # hours

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
        self.ui.pushButton_home.clicked.connect(lambda: self.ui.stackedWidget_page_selector.setCurrentIndex(0))
        self.ui.pushButton_analytics.clicked.connect(lambda: self.ui.stackedWidget_page_selector.setCurrentIndex(1))
        self.ui.pushButton_logistics.clicked.connect(lambda: self.ui.stackedWidget_page_selector.setCurrentIndex(2))
        self.ui.pushButton_settings.clicked.connect(lambda: self.ui.stackedWidget_page_selector.setCurrentIndex(3))
    


        #Uptime and Datetime
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_info)
        self.timer.start(1000)  # update every second

        # Camera setup


        # Slider setup
        self.ui.slider_worktime.valueChanged.connect(self.on_worktime_changed)
        self.on_worktime_changed(self.ui.slider_worktime.value())

    #Define the functions
    def apply_role_permissions(self):
        p = self.permissions

        self.ui.pushButton_settings.setEnabled(p["settings"])
        self.ui.pushButton_analytics.setEnabled(p["analytics"])
        self.ui.pushButton_logistics.setEnabled(p["logistics"])
        self.ui.pushButton_start.setEnabled(p["start"])

    def toggle_page(self, target_index: int):
            stack = self.ui.stackedWidget_page_selector
            if stack.currentIndex() == target_index:
                stack.setCurrentIndex(0)
            else:
                stack.setCurrentIndex(target_index)

    def toggle_start(self):
        if not self.is_running:
            self.start_sys()
            self.ui.pushButton_start.setChecked(True)
            self.ui.pushButton_start.setText("Stop")
            self.ui.pushButton_start.setProperty("state", "stop")
            self.is_running = True

            
            self.ui.pushButton_analytics.setEnabled(self.permissions["analytics"])
            self.ui.pushButton_logistics.setEnabled(self.permissions["logistics"])
        else:
            self.stop_sys()
            self.ui.pushButton_start.setChecked(False)
            self.ui.pushButton_start.setText("Start")
            self.is_running = False

            self.ui.pushButton_analytics.setEnabled(self.permissions["analytics"])
            self.ui.pushButton_logistics.setEnabled(self.permissions["logistics"])


    def start_sys(self):
        print("Camera Here")

    def stop_sys(self):     
        print("Camera Out")

    def on_worktime_changed(self, slider_index: int):
        hours = self.WORK_HOURS_OPTIONS[slider_index]
        self.ui.slider_label.setText(f"Set Worktime (hours): {hours}")
        print(f"Worktime set to: {hours} hours")

    def get_working_hours(self) -> int:
        return self.WORK_HOURS_OPTIONS[self.ui.slider_worktime.value()]
        
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

