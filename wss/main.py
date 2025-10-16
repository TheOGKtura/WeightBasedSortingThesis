from PySide6 import QtCore, QtGui, QtWidgets
import cv2 #for pc testing usb cam
import sys
import os 

class CardWidget(QtWidgets.QFrame):
    clicked = QtCore.Signal(str, str)  # Signal for title and description

    def __init__(self, title, description, image_path=None):
        super().__init__()
        self.title = title
        self.description = description
        self.setFixedSize(200, 250)
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.setFrameShadow(QtWidgets.QFrame.Raised)

        # Modern grey-blue card style
        self.setStyleSheet("""
            QFrame {
                background-color: #34495E;  /* greyish blue */
                border-radius: 12px;
                border: 2px solid #2C3E50;
            }
            QLabel {
                color: white;
                font-family: 'Segoe UI';
            }
            QFrame:hover {
                border: 2px solid #1ABC9C;
                background-color: #3E5871;
            }
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setAlignment(QtCore.Qt.AlignTop)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Image
        if image_path and os.path.exists(image_path):
            pixmap = QtGui.QPixmap(image_path)
            pixmap = pixmap.scaled(180, 120, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            image_label = QtWidgets.QLabel()
            image_label.setPixmap(pixmap)
            image_label.setAlignment(QtCore.Qt.AlignCenter)
            layout.addWidget(image_label)

        # Title
        title_label = QtWidgets.QLabel(title)
        title_label.setStyleSheet("""
            font-weight: bold;
            font-size: 15px;
            color: #ECF0F1;
        """)
        layout.addWidget(title_label)

        # Description
        desc_label = QtWidgets.QLabel(description)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #BDC3C7; font-size: 12px;")
        layout.addWidget(desc_label)

    def mousePressEvent(self, event):
        """Touch and click support"""
        self.clicked.emit(self.title, self.description)
        super().mousePressEvent(event)




class Ui_MainWindow(object):

    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(800, 480)
        MainWindow.setMinimumSize(QtCore.QSize(800, 480))
        MainWindow.setMaximumSize(QtCore.QSize(800, 480))

        self.centralwidget = QtWidgets.QWidget(MainWindow)
        self.stackedWidget = QtWidgets.QStackedWidget(self.centralwidget)
        self.stackedWidget.setGeometry(QtCore.QRect(0, 0, 800, 480))

        # === MAIN PAGE ===
        self.main = QtWidgets.QWidget()
        self.Overview = QtWidgets.QWidget(self.main)
        self.Overview.setGeometry(QtCore.QRect(160, 0, 651, 481))

        # === LABELS ===
        font14 = QtGui.QFont("Arial", 14)
        font16 = QtGui.QFont("Arial", 16)

        self.label_Approved = QtWidgets.QLabel("Approved", self.Overview)
        self.label_Approved.setGeometry(530, 80, 81, 21)
        self.label_Approved.setFont(font14)
        self.label_Approved.setAlignment(QtCore.Qt.AlignCenter)

        self.label_ApprovedCount = QtWidgets.QLabel("0", self.Overview)
        self.label_ApprovedCount.setGeometry(540, 110, 47, 21)
        self.label_ApprovedCount.setFont(font16)

        self.label_Rejected = QtWidgets.QLabel("Rejected", self.Overview)
        self.label_Rejected.setGeometry(530, 140, 81, 21)
        self.label_Rejected.setFont(font14)

        self.label_RejectedCount = QtWidgets.QLabel("0", self.Overview)
        self.label_RejectedCount.setGeometry(540, 170, 47, 21)
        self.label_RejectedCount.setFont(font16)

        self.label_weightThreshold = QtWidgets.QLabel("Threshold", self.Overview)
        self.label_weightThreshold.setGeometry(530, 210, 81, 21)
        self.label_weightThreshold.setFont(font14)
        self.label_weightThreshold.setAlignment(QtCore.Qt.AlignCenter)

        self.label_threshold = QtWidgets.QLabel("999", self.Overview)
        self.label_threshold.setGeometry(540, 250, 41, 21)
        self.label_threshold.setFont(font16)

        self.label_thresholdunit = QtWidgets.QLabel("kgs", self.Overview)
        self.label_thresholdunit.setGeometry(590, 250, 41, 31)
        self.label_thresholdunit.setFont(font16)

        self.label_Measured = QtWidgets.QLabel("Measured", self.Overview)
        self.label_Measured.setGeometry(530, 300, 81, 21)
        self.label_Measured.setFont(font14)
        self.label_Measured.setAlignment(QtCore.Qt.AlignCenter)

        self.label_measuredWeight = QtWidgets.QLabel("999", self.Overview)
        self.label_measuredWeight.setGeometry(540, 340, 41, 21)
        self.label_measuredWeight.setFont(font16)

        self.label_measuredunit = QtWidgets.QLabel("kgs", self.Overview)
        self.label_measuredunit.setGeometry(590, 340, 41, 31)
        self.label_measuredunit.setFont(font16)

        self.label_Product = QtWidgets.QLabel("Product", self.Overview)
        self.label_Product.setGeometry(20, 380, 71, 16)
        self.label_Product.setFont(font14)

        self.textProductDescription = QtWidgets.QTextBrowser(self.Overview)
        self.textProductDescription.setGeometry(40, 410, 561, 51)
        self.textProductDescription.setHtml("<p>[product description]</p>")

        # === CAMERA FEED ===
        self.CameraFeed = QtWidgets.QLabel(self.Overview)
        self.CameraFeed.setGeometry(30, 80, 471, 271)
        self.CameraFeed.setAlignment(QtCore.Qt.AlignCenter)

        self.cameradunno = QtWidgets.QLabel("Model Camera", self.Overview)
        self.cameradunno.setGeometry(30, 20, 471, 41)
        self.cameradunno.setAlignment(QtCore.Qt.AlignCenter)

        # === BUTTONS ===
        font_button = QtGui.QFont("Arial", 10, QtGui.QFont.Bold)
        self.buttonStatistics = QtWidgets.QPushButton("Statistics", self.Overview)
        self.buttonStatistics.setGeometry(520, 20, 111, 51)
        self.buttonStatistics.setFont(font_button)
        self.buttonStatistics.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(3))

        # === SIDE PANEL ===
        self.Panel = QtWidgets.QWidget(self.main)
        self.Panel.setGeometry(0, 0, 161, 481)

        self.verticalLayoutWidget = QtWidgets.QWidget(self.Panel)
        self.verticalLayoutWidget.setGeometry(0, 80, 161, 401)
        self.verticalLayout = QtWidgets.QVBoxLayout(self.verticalLayoutWidget)
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)

        # --- START BUTTON ---
        self.buttonStart = QtWidgets.QPushButton("START")
        self.buttonStart.setCheckable(True)
        self.buttonStart.setFixedSize(159, 80)
        self.verticalLayout.addWidget(self.buttonStart)
        self.buttonStart.toggled.connect(self.toggle_process)
        self.buttonStart.setStyleSheet("background-color: #27AE60")
        # --- PAUSE BUTTON ---
        self.buttonPause = QtWidgets.QPushButton("PAUSE")
        self.buttonPause.setCheckable(True)
        self.buttonPause.setEnabled(False)
        self.buttonPause.setFixedSize(159, 80)
        self.verticalLayout.addWidget(self.buttonPause)
        self.buttonPause.toggled.connect(self.toggle_pause)

        # --- PARAMETERS BUTTON ---
        self.buttonParameters = QtWidgets.QPushButton("PARAMETERS")
        self.buttonParameters.setFixedSize(159, 80)
        self.verticalLayout.addWidget(self.buttonParameters)
        self.buttonParameters.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(1))

        # --- SETTINGS BUTTON ---
        self.buttonSettings = QtWidgets.QPushButton("SETTINGS")
        self.buttonSettings.setFixedSize(159, 80)
        self.verticalLayout.addWidget(self.buttonSettings)
        self.buttonSettings.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(2))

        self.label_Status = QtWidgets.QLabel("Status", self.Panel)
        self.label_Status.setGeometry(15, 10, 55, 15)

        self.label_StatusState = QtWidgets.QLabel(" ", self.Panel)
        self.label_StatusState.setGeometry(10, 29, 121, 31)
        self.label_StatusState.setAlignment(QtCore.Qt.AlignCenter)

        self.stackedWidget.addWidget(self.main)

        # === PARAMETERS PAGE ===
        self.parameters = QtWidgets.QWidget()

        # --- Search Bar ---
        self.search_bar = QtWidgets.QLineEdit(self.parameters)
        self.search_bar.setPlaceholderText("Search food items...")
        self.search_bar.setGeometry(30, 20, 400, 40)
        self.search_bar.textChanged.connect(self.filter_cards)

        self.search_bar.setStyleSheet("""
        QLineEdit {
            color: black;
            background-color: white;
            border-radius: 8px;
            padding: 6px 10px;
            font-size: 14px;
        }
        QLineEdit::placeholder {
            color: gray;
        }
    """)


        # --- Return Button ---
        self.buttonReturnParameters = QtWidgets.QPushButton("RETURN", self.parameters)
        self.buttonReturnParameters.setGeometry(670, 20, 120, 50)
        self.buttonReturnParameters.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(0))

        # --- Scroll Area for Food Cards ---
        self.scroll_area = QtWidgets.QScrollArea(self.parameters)
        self.scroll_area.setGeometry(30, 80, 730, 360)
        self.scroll_area.setWidgetResizable(True)

        self.scroll_content = QtWidgets.QWidget()
        self.scroll_layout = QtWidgets.QHBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(10, 10, 10, 10)
        self.scroll_layout.setSpacing(15)

        self.scroll_area.setWidget(self.scroll_content)
        
        # --- Example Food Items ---
        base_path = os.path.dirname(os.path.abspath(__file__))
        images_path = os.path.join(base_path, "images")

        self.items = [

            {"title": "Okuu", "desc": "Highly Radioactive", "image": os.path.join(images_path, "okuu1.jpg")},
            {"title": "Utsohu", "desc": "Nuclearly Cute", "image": os.path.join(images_path, "okuu2.jpg")},
            {"title": "Nuke", "desc": "Radiant Sun of Happiness", "image": os.path.join(images_path, "okuu3.jpg")},
        ]
  

        # --- Create Card Widgets ---
        self.card_widgets = []
        for item in self.items:
            card = CardWidget(item["title"], item["desc"], item["image"])
            card.clicked.connect(self.display_product_info)
            self.scroll_layout.addWidget(card)
            self.card_widgets.append(card)

        self.stackedWidget.addWidget(self.parameters)


        # === SETTINGS PAGE ===
        self.settings = QtWidgets.QWidget()
        self.buttonReturnSettings = QtWidgets.QPushButton("RETURN", self.settings)
        self.buttonReturnSettings.setGeometry(670, 20, 120, 50)
        self.buttonReturnSettings.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(0))
        self.stackedWidget.addWidget(self.settings)

        # === STATISTICS PAGE ===
        self.statistics = QtWidgets.QWidget()
        self.buttonReturnStatistics = QtWidgets.QPushButton("RETURN", self.statistics)
        self.buttonReturnStatistics.setGeometry(670, 20, 120, 50)
        self.buttonReturnStatistics.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(0))
        self.stackedWidget.addWidget(self.statistics)

        MainWindow.setCentralWidget(self.centralwidget)
        self.stackedWidget.setCurrentIndex(0)

        # === CAMERA SETUP ===
        self.capture = None
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_frame)

    def display_product_info(self, title, description):
        """Updates product description on main page when a card is clicked."""
        self.textProductDescription.setHtml(f"<b>{title}</b><br>{description}")
        self.stackedWidget.setCurrentIndex(0)  # Go back to main page automatically

    # === CAMERA FUNCTIONS ===
    def start_camera(self):
        self.capture = cv2.VideoCapture(0)
        if not self.capture.isOpened():
            print("Camera not accessible!")
            return
        self.timer.start(30)
        print("Camera started")

    def update_frame(self):
        ret, frame = self.capture.read()
        if ret:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = QtGui.QImage(frame, frame.shape[1], frame.shape[0], QtGui.QImage.Format_RGB888)
            pixmap = QtGui.QPixmap.fromImage(image)
            self.CameraFeed.setPixmap(pixmap)

    def stop_camera(self):
        if self.timer.isActive():
            self.timer.stop()
            if self.capture:
                self.capture.release()
            self.CameraFeed.clear()
            print("Camera stopped")


    '''
    #picamera2 module
    
    '''
    # === BUTTON FUNCTIONS ===
    def toggle_process(self, checked):
        """Start/Stop toggle behavior."""
        if checked:
            # === START MODE ===
            self.start_camera()
            self.buttonStart.setText("STOP")
            self.label_StatusState.setText("In Operation")
            self.buttonStart.setStyleSheet("background-color: #E74C3C; color: white;")
            
            # Disable other buttons
            self.buttonParameters.setEnabled(False)
            self.buttonSettings.setEnabled(False)
            self.buttonStatistics.setEnabled(False)
            
            # Enable pause button
            self.buttonPause.setEnabled(True)
            self.buttonPause.setChecked(False)
            self.buttonPause.setText("PAUSE")
            self.buttonPause.setStyleSheet("background-color: #F1C40F; color: black;")
        else:
            # === STOP MODE ===
            self.stop_camera()
            self.buttonStart.setText("START")
            self.label_StatusState.setText("Stopped")
            self.buttonStart.setStyleSheet("background-color: #27AE60; color: white;")
            
            # Re-enable buttons
            self.buttonParameters.setEnabled(True)
            self.buttonSettings.setEnabled(True)
            self.buttonStatistics.setEnabled(True)
            
            # Disable pause button
            self.buttonPause.setEnabled(False)
            self.buttonPause.setChecked(False)
            self.buttonPause.setText("PAUSE")
            self.buttonPause.setStyleSheet("")

    def toggle_pause(self, checked):
        """Pause/Continue toggle behavior."""
        if checked:
            # === PAUSE MODE ===
            if self.timer.isActive():
                self.timer.stop()
            self.buttonPause.setText("CONTINUE")
            self.label_StatusState.setText("Paused")
            self.buttonPause.setStyleSheet("background-color: #5DADE2; color: white;")
        else:
            # === CONTINUE MODE ===
            if self.capture:
                self.timer.start(30)
            self.buttonPause.setText("PAUSE")
            self.label_StatusState.setText("In Operation")
            self.buttonPause.setStyleSheet("background-color: #F1C40F; color: black;")


    #Product Cards
    def filter_cards(self, text):
        for i, item in enumerate(self.items):
            if text.lower() in item["title"].lower() or text.lower() in item["desc"].lower():
                self.card_widgets[i].show()
            else:
                self.card_widgets[i].hide()

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    MainWindow = QtWidgets.QMainWindow()
    qss_path = os.path.join(os.path.dirname(__file__), "style.qss")
    if os.path.exists(qss_path):
        with open(qss_path, "r") as f:
            app.setStyleSheet(f.read())
        print("style.qss loaded")
    else:
        print("style.qss no within directory")
    ui = Ui_MainWindow()
    ui.setupUi(MainWindow)
    MainWindow.show()
    sys.exit(app.exec())
