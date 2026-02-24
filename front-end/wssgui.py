
from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QApplication, QFrame, QLabel, QMainWindow,
    QPushButton, QSizePolicy, QStackedWidget, QWidget, QSlider)

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        if not MainWindow.objectName():
            MainWindow.setObjectName(u"MainWindow")
        MainWindow.resize(800, 480)
        MainWindow.setMinimumSize(QSize(800, 480))
        MainWindow.setMaximumSize(QSize(800, 480))
        self.centralwidget_app_background = QWidget(MainWindow)
        self.centralwidget_app_background.setObjectName(u"centralwidget_app_background")

        self.frame_background = QFrame(self.centralwidget_app_background)
        self.frame_background.setObjectName(u"frame_background")
        self.frame_background.setGeometry(QRect(10, 10, 782, 460))
        self.frame_background.setMinimumSize(QSize(782, 460))
        self.frame_background.setMaximumSize(QSize(782, 460))
        self.frame_background.setFrameShape(QFrame.Shape.StyledPanel)
        self.frame_background.setFrameShadow(QFrame.Shadow.Raised)

        self.stackedWidget_page_selector = QStackedWidget(self.frame_background)
        self.stackedWidget_page_selector.setObjectName(u"stackedWidget_page_selector")
        self.stackedWidget_page_selector.setGeometry(QRect(10, 10, 762, 376))

        self.page_mainpage = QWidget()
        self.page_mainpage.setObjectName(u"page_mainpage")

        self.cameraFeed = QLabel(self.page_mainpage)
        self.cameraFeed.setObjectName(u"cameraFeed")
        self.cameraFeed.setGeometry(QRect(180, 30, 420, 360))
        #self.cameraFeed.setScaledContents(True)
        self.cameraFeed.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.frame_notif = QFrame(self.page_mainpage)
        self.frame_notif.setObjectName(u"frame_notif")
        self.frame_notif.setGeometry(QRect(25, 10, 712, 37))
        self.frame_notif.setFrameShape(QFrame.Shape.StyledPanel)
        self.frame_notif.setFrameShadow(QFrame.Shadow.Raised)

        self.label_detected_goods = QLabel(self.frame_notif)
        self.label_detected_goods.setObjectName(u"label_detected_goods")
        self.label_detected_goods.setGeometry(QRect(15, 10, 201, 16))

        self.label_time = QLabel(self.frame_notif)
        self.label_time.setObjectName(u"label_time")
        self.label_time.setGeometry(QRect(575, 10, 150, 16))

        self.label_runtime = QLabel(self.frame_notif)
        self.label_runtime.setObjectName(u"label_runtime")
        self.label_runtime.setGeometry(QRect(500, 10, 60, 16))

        self.frame_redIndicator = QFrame(self.page_mainpage)
        self.frame_redIndicator.setObjectName(u"frame_redIndicator")
        self.frame_redIndicator.setGeometry(QRect(5, 10, 16, 16))
        self.frame_redIndicator.setFrameShape(QFrame.Shape.StyledPanel)
        self.frame_redIndicator.setFrameShadow(QFrame.Shadow.Raised)

        self.frame_greenIndicator = QFrame(self.page_mainpage)
        self.frame_greenIndicator.setObjectName(u"frame_greenIndicator")
        self.frame_greenIndicator.setGeometry(QRect(5, 30, 16, 16))
        self.frame_greenIndicator.setFrameShape(QFrame.Shape.StyledPanel)
        self.frame_greenIndicator.setFrameShadow(QFrame.Shadow.Raised)
        self.stackedWidget_page_selector.addWidget(self.page_mainpage)

        #=================================
        self.page_analytics = QWidget()
        self.page_analytics.setObjectName(u"page_analytics")
        self.stackedWidget_page_selector.addWidget(self.page_analytics)


        #=================================
        self.page_logistics = QWidget()
        self.page_logistics.setObjectName(u"page_logistics")
        self.stackedWidget_page_selector.addWidget(self.page_logistics)

        #=================================
        self.page_settings = QWidget()
        self.page_settings.setObjectName(u"page_settings")
        self.stackedWidget_page_selector.addWidget(self.page_settings)

        self.slider_worktime = QSlider(Qt.Horizontal, self.page_settings)
        self.slider_worktime.setObjectName(u"slider_worktime")
        self.slider_worktime.setGeometry(QRect(20, 20, 160, 22))
        
        self.slider_worktime.setMinimum(0)
        self.slider_worktime.setMaximum(3)
        self.slider_worktime.setSingleStep(1)
        self.slider_worktime.setPageStep(1)
        self.slider_worktime.setTickInterval(1)
        self.slider_worktime.setTickPosition(QSlider.TicksBelow)
        self.slider_worktime.setValue(0) 
        
        self.slider_label = QLabel(self.page_settings)
        self.slider_label.setObjectName(u"slider_label")
        self.slider_label.setGeometry(QRect(20, 50, 200, 16))
        self.slider_label.setText("Set Worktime (hours): 2")

        self.pushButton_logout = QPushButton(self.page_settings)
        self.pushButton_logout.setObjectName(u"pushButton_logout")
        self.pushButton_logout.setGeometry(QRect(20, 90, 200, 55))


        #=============================
        bar_y = 385
        bar_h = 65
        left = 10
        gap = 10
        btn_w = 145  # 5 buttons across: 5*150 + 4*6 + 2*10 = 794 (fits)

        # Settings
        self.pushButton_settings = QPushButton(self.frame_background)
        self.pushButton_settings.setObjectName(u"pushButton_settings")
        self.pushButton_settings.setGeometry(QRect(left + (btn_w + gap) * 0, bar_y, btn_w, bar_h))

        # Home (NEW)
        self.pushButton_home = QPushButton(self.frame_background)
        self.pushButton_home.setObjectName(u"pushButton_home")
        self.pushButton_home.setGeometry(QRect(left + (btn_w + gap) * 1, bar_y, btn_w, bar_h))

        # Logistics
        self.pushButton_logistics = QPushButton(self.frame_background)
        self.pushButton_logistics.setObjectName(u"pushButton_logistics")
        self.pushButton_logistics.setGeometry(QRect(left + (btn_w + gap) * 2, bar_y, btn_w, bar_h))

        # Analytics
        self.pushButton_analytics = QPushButton(self.frame_background)
        self.pushButton_analytics.setObjectName(u"pushButton_analytics")
        self.pushButton_analytics.setGeometry(QRect(left + (btn_w + gap) * 3, bar_y, btn_w, bar_h))

        # Start
        self.pushButton_start = QPushButton(self.frame_background)
        self.pushButton_start.setObjectName(u"pushButton_start")
        self.pushButton_start.setGeometry(QRect(left + (btn_w + gap) * 4, bar_y, btn_w, bar_h))


        MainWindow.setCentralWidget(self.centralwidget_app_background)

        self.retranslateUi(MainWindow)

        self.stackedWidget_page_selector.setCurrentIndex(0)


        QMetaObject.connectSlotsByName(MainWindow)
    # setupUi

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QCoreApplication.translate("MainWindow", u"MainWindow", None))
        self.cameraFeed.setText(QCoreApplication.translate("MainWindow", u"Camera Feed", None))

        self.label_detected_goods.setText(QCoreApplication.translate("MainWindow", u"No Goods Detected", None))
        self.label_time.setText(QCoreApplication.translate("MainWindow", u"Time", None))
       
        self.label_runtime.setText(QCoreApplication.translate("MainWindow", u"Uptime", None))
        self.pushButton_start.setText(QCoreApplication.translate("MainWindow", u"Start", None))
        self.pushButton_analytics.setText(QCoreApplication.translate("MainWindow", u"Analytics", None))
        self.pushButton_logistics.setText(QCoreApplication.translate("MainWindow", u"Logistics", None))
        self.pushButton_settings.setText(QCoreApplication.translate("MainWindow", u"Settings", None))
        self.pushButton_logout.setText(QCoreApplication.translate("MainWindow", u"Logout", None))
        self.pushButton_home.setText(QCoreApplication.translate("MainWindow", u"Home", None))
    # retranslateUi

