#Solely Frontend withouth BackEnd connections
from PySide6 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg
import sys, os, time
#import subprocess # <-- for onscreen keyboard, pero di pa installed sa apt packages ng raspi
#from picamera2 import Picamera2
import numpy as np
import cv2
#   --->    Wala pang FireBase Connection :(    <--

#>>Parameters Page
# - Item Cards -
class CardWidget(QtWidgets.QFrame):
    clicked = QtCore.Signal(str, str, float) 

    def __init__(self, title, description, image_path=None, weight=0.0):
        super().__init__()
        self.title = title
        self.description = description
        self.weight = weight
        self.setFixedSize(200, 250)
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.setFrameShadow(QtWidgets.QFrame.Raised)

        #Style for item Cards
        self.setStyleSheet("""
            QFrame {
                background-color: #34495E;  /* greyish blue */
                border-radius: 12px;
                border: 2px solid #2C3E50;
            }
            QLabel {
                color: white;
                font-family: 'Segoe UI';
                border: transparent;
            }
            QScrollArea, 
            QScrollArea QWidget {
                background-color: rgba(43, 58, 85, 180); /* dark bluish with transparency */
                border: none;}
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setAlignment(QtCore.Qt.AlignTop)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Load Images Within the card
        if image_path and os.path.exists(image_path):
            pixmap = QtGui.QPixmap(image_path)
            pixmap = pixmap.scaled(180, 120, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            image_label = QtWidgets.QLabel()
            image_label.setPixmap(pixmap)
            image_label.setAlignment(QtCore.Qt.AlignCenter)
            layout.addWidget(image_label)

        # Title - Product Name or Brand Name
        title_label = QtWidgets.QLabel(title)
        title_label.setStyleSheet("""
            font-weight: bold;
            font-size: 15px;
            color: #ECF0F1;
        """)
        layout.addWidget(title_label)

        # Description of the Product
        desc_label = QtWidgets.QLabel(description)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #BDC3C7; font-size: 12px;")
        layout.addWidget(desc_label)

    #Avoids misclicks when choosing an item
    def mouseDoubleClickEvent(self, event):
        """Double-tap or double-click to activate"""
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit(self.title, self.description, self.weight)
        super().mouseDoubleClickEvent(event)

#eto ung kapag tinouch search bar lalabas ung keyboard
class SearchBar(QtWidgets.QLineEdit):
    def focusInEvent(self, event):
        super().focusInEvent(event)
        #Opens onboard Keyboard on Touch
        subprocess.Popen(["onboard"])
    
    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        # close keyboard when focus is lost
        subprocess.Popen(["pkill", "onboard"])

class TouchScrollArea(QtWidgets.QScrollArea):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.last_pos = None
        self.setStyleSheet("background: transparent; border: none;")

    def mousePressEvent(self, event):
        self.last_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.last_pos is not None:
            delta = event.pos() - self.last_pos
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            self.last_pos = event.pos()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.last_pos = None
        super().mouseReleaseEvent(event)

#<< Parameters Page

#>> Main Page

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

        #<-- Needs Backend throught decision making based on the Straight Bar Load Cell
        #<-- Increments when Item is approved
        self.label_ApprovedCount = QtWidgets.QLabel("0", self.Overview)
        self.label_ApprovedCount.setGeometry(540, 110, 47, 21)
        self.label_ApprovedCount.setFont(font16)

        self.label_Rejected = QtWidgets.QLabel("Rejected", self.Overview)
        self.label_Rejected.setGeometry(530, 140, 81, 21)
        self.label_Rejected.setFont(font14)

        #<-- Needs Backend throught decision making based on the Straight Bar Load Cell
        #<-- Increments when Item is rejected
        self.label_RejectedCount = QtWidgets.QLabel("0", self.Overview)
        self.label_RejectedCount.setGeometry(540, 170, 47, 21)
        self.label_RejectedCount.setFont(font16)

    
        self.label_weightThreshold = QtWidgets.QLabel("Threshold", self.Overview)
        self.label_weightThreshold.setGeometry(530, 210, 81, 21)
        self.label_weightThreshold.setFont(font14)
        self.label_weightThreshold.setAlignment(QtCore.Qt.AlignCenter)

        #<-- Standard Weight of Selected Product
        #<-- Should reflect on the backend as the reference on comparision between sensor readings
        self.label_threshold = QtWidgets.QLabel("0", self.Overview)
        self.label_threshold.setGeometry(540, 250, 41, 21)
        self.label_threshold.setFont(font16)

        #<-- Can be changed to be dynamic that changes when over 1000 grams and be convetred to
        #<-- the next weighting unit
        self.label_thresholdunit = QtWidgets.QLabel("g", self.Overview)
        self.label_thresholdunit.setGeometry(590, 250, 41, 31)
        self.label_thresholdunit.setFont(font16)


        self.label_Measured = QtWidgets.QLabel("Measured", self.Overview)
        self.label_Measured.setGeometry(530, 300, 81, 21)
        self.label_Measured.setFont(font14)
        self.label_Measured.setAlignment(QtCore.Qt.AlignCenter)

        #<-- Connected to the output of sensor reading(weight) and is sent to the decision
        self.label_measuredWeight = QtWidgets.QLabel("0", self.Overview)
        self.label_measuredWeight.setGeometry(540, 340, 41, 21)
        self.label_measuredWeight.setFont(font16)

        self.label_measuredunit = QtWidgets.QLabel("g", self.Overview)
        self.label_measuredunit.setGeometry(590, 340, 41, 31)
        self.label_measuredunit.setFont(font16)

        self.label_Product = QtWidgets.QLabel("Product", self.Overview)
        self.label_Product.setGeometry(20, 380, 71, 16)
        self.label_Product.setFont(font14)

        self.textProductDescription = QtWidgets.QTextBrowser(self.Overview)
        self.textProductDescription.setGeometry(20, 410, 561, 51)
        self.textProductDescription.setHtml("<p></p>")

        # === CAMERA FEED === <-- need kumonek sa raspi cam3
        self.CameraFeed = QtWidgets.QLabel(self.Overview)
        self.CameraFeed.setGeometry(30, 80, 471, 271)
        self.CameraFeed.setAlignment(QtCore.Qt.AlignCenter)

        #<-- Outcome ng Object Detection ng Camera <-- Accepted <-- Rejeected <-- Others
        self.camera_outcome = QtWidgets.QLabel("-", self.Overview)
        self.camera_outcome.setGeometry(100, 20, 471, 41)
        self.camera_outcome.setAlignment(QtCore.Qt.AlignCenter)

        # === DATE & TIME DISPLAY on Main Page ===
        self.label_datetime_main = QtWidgets.QLabel(self.Overview)
        self.label_datetime_main.setGeometry(20, 20, 300, 30)
        self.label_datetime_main.setStyleSheet("color: white; font-size: 16px; font-weight: bold;")
        self.label_datetime_main.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        self.label_maintime_main = QtWidgets.QLabel(self.Overview)
        self.label_maintime_main.setGeometry(20, 40, 300, 30)
        self.label_maintime_main.setStyleSheet("color: white; font-size: 16px; font-weight: bold;")
        self.label_maintime_main.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)



        #<-- Goes to Statistics Page
        font_button = QtGui.QFont("Arial", 10, QtGui.QFont.Bold)
        self.buttonStatistics = QtWidgets.QPushButton("Statistics", self.Overview)
        self.buttonStatistics.setGeometry(520, 20, 111, 51)
        self.buttonStatistics.setFont(font_button)
        self.buttonStatistics.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(3))


        #<-- Side Panel from the Main Page

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
        self.verticalLayout.addWidget(self.buttonStart)             #<-- sa Camera Function
        self.buttonStart.toggled.connect(self.toggle_process)       #<-- sa Camera
        self.buttonStart.setStyleSheet("background-color: #27AE60")

        # --- PAUSE BUTTON ---
        self.buttonPause = QtWidgets.QPushButton("PAUSE")
        self.buttonPause.setCheckable(True)
        self.buttonPause.setEnabled(False)
        self.buttonPause.setFixedSize(159, 80)
        self.verticalLayout.addWidget(self.buttonPause)             #<-- Halt ung System 
        self.buttonPause.toggled.connect(self.toggle_pause)         #<-- Stop Operation

        # --- PARAMETERS BUTTON ---
        self.buttonParameters = QtWidgets.QPushButton("PARAMETERS")
        self.buttonParameters.setFixedSize(159, 80)
        self.verticalLayout.addWidget(self.buttonParameters)        #<-- Goes to Parameters Page
        self.buttonParameters.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(1)) 

        # --- SETTINGS BUTTON ---
        self.buttonSettings = QtWidgets.QPushButton("SETTINGS")
        self.buttonSettings.setFixedSize(159, 80)
        self.verticalLayout.addWidget(self.buttonSettings)          #<-- Goes to Settings Page
        self.buttonSettings.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(2))

        #<--  Dictates the Systems Operational State >In Operation > Halted 

        self.label_Status = QtWidgets.QLabel("Status", self.Panel)
        self.label_Status.setGeometry(15, 10, 60, 15)

        self.label_StatusState = QtWidgets.QLabel(" ", self.Panel)
        self.label_StatusState.setGeometry(10, 29, 121, 31)
        self.label_StatusState.setAlignment(QtCore.Qt.AlignCenter)
        self.stackedWidget.addWidget(self.main)

       # === PARAMETERS PAGE ===
        self.parameters = QtWidgets.QWidget()

        # --- Search Bar with On-Screen Keyboard ---
        self.search_bar = SearchBar(self.parameters)

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
        
        # --- Scroll Area for Food Cards ---
        self.scroll_area = TouchScrollArea(self.parameters)
        self.scroll_area.setGeometry(30, 80, 730, 400)
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
            {"title": "CDO", "desc": "Chicken Nuggets - 200 grams", "image": os.path.join(images_path, "CDO - CHICKEN NUGGETS.png"), "weight": 200.0},
            {"title": "CDO FUNTASTYK", "desc": "Young Pork Tocino - 450 grams", "image": os.path.join(images_path, "CDO FUNTASTYK - YOUNG PORK.png"), "weight": 450.0},
            {"title": "CDO IDOL", "desc": "Cheesedog Jumbo - 1 kg", "image": os.path.join(images_path, "CDO IDOL - CHEESEDOG - JUMBO.png"), "weight": 1000},
            {"title": "CDO", "desc": "Crispy Burger - 228 grams", "image": os.path.join(images_path, "CDO-Crispy Burger.png"), "weight": 228},
        ]

        # --- Create Card Widgets ---
        self.card_widgets = []
        for item in self.items:
            card = CardWidget(item["title"], item["desc"], item["image"], item["weight"])
            card.clicked.connect(self.display_product_info)
            self.scroll_layout.addWidget(card)
            self.card_widgets.append(card)
        self.stackedWidget.addWidget(self.parameters)


        # --- Return Button ---
        self.buttonReturnParameters = QtWidgets.QPushButton("RETURN", self.parameters)
        self.buttonReturnParameters.setGeometry(670, 20, 120, 50)
        self.buttonReturnParameters.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(0))

        # === SETTINGS PAGE ===
        self.settings = QtWidgets.QWidget()
        self.buttonReturnSettings = QtWidgets.QPushButton("RETURN", self.settings)
        self.buttonReturnSettings.setGeometry(670, 20, 120, 50)
        self.buttonReturnSettings.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(0))
        self.stackedWidget.addWidget(self.settings)


        self.buttonExit = QtWidgets.QPushButton("EXIT PROGRAM", self.settings)
        self.buttonExit.setGeometry(650, 390, 130, 60)
        self.buttonExit.clicked.connect(self.show_exit_popup)
        
        # === POPUP OVERLAY ===
        self.popup = QtWidgets.QFrame(self.settings)
        self.popup.setObjectName("popupOverlay")
        self.popup.setGeometry(0, 0, 800, 480)
        self.popup.hide()

        # --- Inner box ---
        self.popup_box = QtWidgets.QFrame(self.popup)
        self.popup_box.setObjectName("popupBox")
        self.popup_box.setGeometry(210, 160, 380, 180)

        self.labelPopup = QtWidgets.QLabel("Are you sure you want to exit?", self.popup_box)
        self.labelPopup.setObjectName("labelPopup")
        self.labelPopup.setGeometry(50, 40, 300, 30)

        self.yes_btn = QtWidgets.QPushButton("YES", self.popup_box)
        self.yes_btn.setObjectName("yesBtn")
        self.yes_btn.setGeometry(80, 100, 100, 40)
        self.yes_btn.clicked.connect(QtWidgets.QApplication.quit)

        self.no_btn = QtWidgets.QPushButton("NO", self.popup_box)
        self.no_btn.setObjectName("noBtn")
        self.no_btn.setGeometry(220, 100, 100, 40)
        self.no_btn.clicked.connect(self.popup.hide)

        # === UPTIME TRACKER ===
        self.start_time = time.time()
        self.uptime_timer = QtCore.QTimer()
        self.uptime_timer.timeout.connect(self.update_uptime)
        self.uptime_timer.start(1000)

        self.datetime_timer = QtCore.QTimer()
        self.datetime_timer.timeout.connect(self.update_datetime)
        self.datetime_timer.start(1000)

        

        # Uptime Label
        self.label_uptime = QtWidgets.QLabel("Uptime: 00:00:00", self.settings)
        self.label_uptime.setGeometry(30, 40, 300, 50)
        self.label_uptime.setFont(QtGui.QFont("Arial", 14))
        self.label_uptime.setStyleSheet("color: white;")
        self.label_uptime.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        # Date and Time Display
        self.label_datetime = QtWidgets.QLabel(self.settings)
        self.label_datetime.setGeometry(30, 20, 400, 40)
        self.label_datetime.setStyleSheet("color: white; font-size: 16px; font-weight: bold;")
        self.label_datetime.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)


        # === STATISTICS PAGE ===
        self.statistics = QtWidgets.QWidget()
        self.buttonReturnStatistics = QtWidgets.QPushButton("RETURN", self.statistics)
        self.buttonReturnStatistics.setGeometry(670, 20, 120, 50)
        self.buttonReturnStatistics.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(0))
        self.stackedWidget.addWidget(self.statistics)

        #<-- I have no Idea what is this
        MainWindow.setCentralWidget(self.centralwidget)
        self.stackedWidget.setCurrentIndex(0)
        self.setup_statistics_dashboard()



#       <<<---      Functions       --->>>

    #Main Page Functions

        self.capture = None
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_frame)


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
        self.picam2 = None
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_frame)
    '''
    '''
    # === CAMERA FUNCTIONS ===
    def start_camera(self):
        try:
            self.picam2 = Picamera2()
            config = self.picam2.create_preview_configuration(
                main={"size": (640, 480), "format": "RGB888"}
            )
            self.picam2.configure(config)
            self.picam2.start()
            self.timer.start(30)
            print(" PiCamera2 started successfully")
        except Exception as e:
            print(" Error starting PiCamera2:", e)

    def update_frame(self):
        if hasattr(self, 'picam2') and self.picam2:
            try:
                frame = self.picam2.capture_array()
                if frame is not None:
                    # frame is already RGB888
                    image = QtGui.QImage(
                        frame.data,
                        frame.shape[1],
                        frame.shape[0],
                        frame.strides[0],
                        QtGui.QImage.Format_RGB888
                    )
                    pixmap = QtGui.QPixmap.fromImage(image)
                    self.CameraFeed.setPixmap(pixmap)
            except Exception as e:
                print("Frame update error:", e)

    def stop_camera(self):
        if self.timer.isActive():
            self.timer.stop()
        if hasattr(self, 'picam2') and self.picam2:
            try:
                self.picam2.stop()
                self.picam2.close()
                self.picam2 = None
                print("🛑 PiCamera2 stopped")
            except Exception as e:
                print("❌ Error stopping PiCamera2:", e)
        self.CameraFeed.clear()

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

    #Paramters Function

    def display_product_info(self, title, description, weight):
        """Updates product description and threshold weight."""
        self.textProductDescription.setHtml(f"<b>{title}</b><br>{description}")
        self.label_threshold.setText(f"{weight:.0f}")  # update threshold value
        self.label_thresholdunit.setText("g")           # optional: use grams
        self.stackedWidget.setCurrentIndex(0)           # return to main page

    #Product Cards
    def filter_cards(self, text):
        for i, item in enumerate(self.items):
            if text.lower() in item["title"].lower() or text.lower() in item["desc"].lower():
                self.card_widgets[i].show()
            else:
                self.card_widgets[i].hide()

    
    #Settings Function

    def update_uptime(self):
        """Updates only the uptime label"""
        elapsed_seconds = int(time.time() - self.start_time)
        hours, remainder = divmod(elapsed_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"Uptime: {hours:02d}:{minutes:02d}:{seconds:02d}"
        self.label_uptime.setText(uptime_str)



    def update_datetime(self):
        """Updates both Settings and Main Page date/time labels"""
        current_time = time.strftime("%Y-%m-%d %I:%M %p")
        main_date = time.strftime("%A, %B %d, %Y")
        main_time = time.strftime("%I:%M %p")

        # Update Settings Page
        self.label_datetime.setText(f"{current_time}")

        # Update Main Overview Page
        if hasattr(self, "label_datetime_main"):
            self.label_datetime_main.setText(main_date)
        if hasattr(self, "label_maintime_main"):
            self.label_maintime_main.setText(main_time)

    
    def show_exit_popup(self):
        self.popup.show()


    #Statistic Function

    # --- STATISTICS PAGE DASHBOARD ---
    def setup_statistics_dashboard(self):
        # Background frame
        self.stats_frame = QtWidgets.QFrame(self.statistics)
        self.stats_frame.setGeometry(10, 80, 780, 380)
        self.stats_frame.setStyleSheet("background-color: #2C3E50; border-radius: 10px;")
        
        # Summary Cards
        self.card_approved = QtWidgets.QLabel("Approved: 0", self.stats_frame)
        self.card_approved.setGeometry(20, 10, 150, 40)
        self.card_approved.setStyleSheet("background-color: #27AE60; color: white; font-weight: bold; border-radius: 8px;")
        self.card_approved.setAlignment(QtCore.Qt.AlignCenter)

        self.card_rejected = QtWidgets.QLabel("Rejected: 0", self.stats_frame)
        self.card_rejected.setGeometry(200, 10, 150, 40)
        self.card_rejected.setStyleSheet("background-color: #E74C3C; color: white; font-weight: bold; border-radius: 8px;")
        self.card_rejected.setAlignment(QtCore.Qt.AlignCenter)

        # PyQtGraph Plot Widget
        self.stats_plot = pg.PlotWidget(self.stats_frame)
        self.stats_plot.setGeometry(20, 60, 740, 300)
        self.stats_plot.setBackground("#34495E")
        
        # X-axis: Days
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        self.stats_plot.getPlotItem().getAxis('bottom').setTicks([list(enumerate(days))])

        # Y-axis: Quantity
        self.stats_plot.setLabel('left', 'Quantity')
        self.stats_plot.setLabel('bottom', 'Day')
        self.stats_plot.showGrid(x=True, y=True, alpha=0.3)

        # Lines for Accepted and Rejected
        self.accepted_line = self.stats_plot.plot([], [], pen=pg.mkPen(color="#27AE60", width=3), symbol='o', symbolSize=8, name="Accepted")
        self.rejected_line = self.stats_plot.plot([], [], pen=pg.mkPen(color="#E74C3C", width=3), symbol='x', symbolSize=8, name="Rejected")

        # Toggle checkboxes
        self.checkbox_accepted = QtWidgets.QCheckBox("Show Accepted", self.stats_frame)
        self.checkbox_accepted.setGeometry(400, 10, 120, 30)
        self.checkbox_accepted.setChecked(True)
        self.checkbox_accepted.stateChanged.connect(lambda: self.accepted_line.setVisible(self.checkbox_accepted.isChecked()))

        self.checkbox_rejected = QtWidgets.QCheckBox("Show Rejected", self.stats_frame)
        self.checkbox_rejected.setGeometry(530, 10, 120, 30)
        self.checkbox_rejected.setChecked(True)
        self.checkbox_rejected.stateChanged.connect(lambda: self.rejected_line.setVisible(self.checkbox_rejected.isChecked()))

        # Example static data (replace later with your weight sensor data)
        x = np.arange(7)  # Days
        accepted = np.random.randint(5, 20, size=7)
        rejected = np.random.randint(0, 5, size=7)

        self.update_statistics_plot(x, accepted, rejected)

    def update_statistics_plot(self, x, accepted, rejected):
        self.accepted_line.setData(x, accepted)
        self.rejected_line.setData(x, rejected)
        self.card_approved.setText(f"Approved: {sum(accepted)}")
        self.card_rejected.setText(f"Rejected: {sum(rejected)}")


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    MainWindow = QtWidgets.QMainWindow()
    qss_path = os.path.join(os.path.dirname(__file__), "style.qss")
    if os.path.exists(qss_path):
        with open(qss_path, "r") as f:
            app.setStyleSheet(f.read())
        print("style.qss loaded")
    else:
        print("style.qss not found within directory")
    ui = Ui_MainWindow()
    ui.setupUi(MainWindow)
    
    MainWindow.setWindowFlags(QtCore.Qt.FramelessWindowHint)
    MainWindow.setFixedSize(800, 480) # <-- self.setWindowFlags(QtCore.Qt.FramelessWindowHint) if raspi
    MainWindow.show() #<-- change to self.showFullScreen() if raspi
    sys.exit(app.exec())
