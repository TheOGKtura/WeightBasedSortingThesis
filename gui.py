
from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QApplication, QFrame, QLabel, QMainWindow,
    QPushButton, QSizePolicy, QStackedWidget, QWidget)

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        if not MainWindow.objectName():
            MainWindow.setObjectName(u"MainWindow")

        MainWindow.resize(800, 480)
        MainWindow.setMinimumSize(QSize(800, 480))
        MainWindow.setMaximumSize(QSize(800, 480))
        self.centralwidget = QWidget(MainWindow)
        self.centralwidget.setObjectName(u"centralwidget")

        self.stackedWidget = QStackedWidget(self.centralwidget)
        self.stackedWidget.setObjectName(u"stackedWidget")
        self.stackedWidget.setGeometry(QRect(0, 0, 800, 480))
        self.stackedWidget.setMinimumSize(QSize(800, 480))
        self.stackedWidget.setMaximumSize(QSize(800, 480))

        self.page_main = QWidget()
        self.page_main.setObjectName(u"page_main")

        self.frame_camera = QFrame(self.page_main)
        self.frame_camera.setObjectName(u"frame_camera")
        self.frame_camera.setGeometry(QRect(300, 30, 477, 365))
        self.frame_camera.setFrameShape(QFrame.Shape.StyledPanel)
        self.frame_camera.setFrameShadow(QFrame.Shadow.Raised)
        
        self.frame_product_name = QFrame(self.page_main)
        self.frame_product_name.setObjectName(u"frame_product_name")
        self.frame_product_name.setGeometry(QRect(20, 30, 255, 42))
        self.frame_product_name.setFrameShape(QFrame.Shape.StyledPanel)
        self.frame_product_name.setFrameShadow(QFrame.Shadow.Raised)

        self.label_product = QLabel(self.frame_product_name)
        self.label_product.setObjectName(u"label_product")
        self.label_product.setGeometry(QRect(10, 12, 200, 16))

        self.frame_sys_time = QFrame(self.page_main)
        self.frame_sys_time.setObjectName(u"frame_sys_time")
        self.frame_sys_time.setGeometry(QRect(20, 80, 255, 27))
        self.frame_sys_time.setFrameShape(QFrame.Shape.StyledPanel)
        self.frame_sys_time.setFrameShadow(QFrame.Shadow.Raised)

        self.label_uptime = QLabel(self.frame_sys_time)
        self.label_uptime.setObjectName(u"label_uptime")
        self.label_uptime.setGeometry(QRect(10, 5, 49, 16))

        self.label_date = QLabel(self.frame_sys_time)
        self.label_date.setObjectName(u"label_date")
        self.label_date.setGeometry(QRect(130, 5, 49, 16))

        self.frame_green_ind = QFrame(self.page_main)
        self.frame_green_ind.setObjectName(u"frame_green_ind")
        self.frame_green_ind.setGeometry(QRect(50, 120, 61, 62))
        self.frame_green_ind.setFrameShape(QFrame.Shape.StyledPanel)
        self.frame_green_ind.setFrameShadow(QFrame.Shadow.Raised)

        self.frame_red_ind = QFrame(self.page_main)
        self.frame_red_ind.setObjectName(u"frame_red_ind")
        self.frame_red_ind.setGeometry(QRect(180, 120, 61, 62))
        self.frame_red_ind.setFrameShape(QFrame.Shape.StyledPanel)
        self.frame_red_ind.setFrameShadow(QFrame.Shadow.Raised)

        self.frame_product_description = QFrame(self.page_main)
        self.frame_product_description.setObjectName(u"frame_product_description")
        self.frame_product_description.setGeometry(QRect(20, 200, 255, 139))
        self.frame_product_description.setFrameShape(QFrame.Shape.StyledPanel)
        self.frame_product_description.setFrameShadow(QFrame.Shadow.Raised)
        
        self.label_product_weight = QLabel(self.frame_product_description)
        self.label_product_weight.setObjectName(u"label_product_weight")
        self.label_product_weight.setGeometry(QRect(100, 30, 49, 16))

        self.label_product_count = QLabel(self.frame_product_description)
        self.label_product_count.setObjectName(u"label_product_count")
        self.label_product_count.setGeometry(QRect(100, 85, 49, 16))

        self.pushButton_start = QPushButton(self.page_main)
        self.pushButton_start.setObjectName(u"pushButton_start")
        self.pushButton_start.setGeometry(QRect(640, 410, 131, 55))

        self.pushButton_calibrate = QPushButton(self.page_main)
        self.pushButton_calibrate.setObjectName(u"pushButton_calibrate")
        self.pushButton_calibrate.setGeometry(QRect(330, 410, 141, 55))

        self.pushButton_home = QPushButton(self.page_main)
        self.pushButton_home.setObjectName(u"pushButton_signout") # Change to "home" to "signout"
        self.pushButton_home.setGeometry(QRect(10, 410, 131, 55))

        self.frame_account = QFrame(self.page_main)
        self.frame_account.setObjectName(u"frame_account")
        self.frame_account.setGeometry(QRect(20, 350, 251, 51))
        self.frame_account.setFrameShape(QFrame.Shape.StyledPanel)
        self.frame_account.setFrameShadow(QFrame.Shadow.Raised)

        self.label_account = QLabel(self.frame_account)
        self.label_account.setObjectName(u"label_account")
        self.label_account.setGeometry(QRect(10, 18, 49, 16))

        self.stackedWidget.addWidget(self.page_main)

        MainWindow.setCentralWidget(self.centralwidget)

        self.retranslateUi(MainWindow)

        self.stackedWidget.setCurrentIndex(0)

        QMetaObject.connectSlotsByName(MainWindow)
    # setupUi

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QCoreApplication.translate("MainWindow", u"MainWindow", None))
        self.label_product.setText(QCoreApplication.translate("MainWindow", u"No Product Detected", None))
        self.label_uptime.setText(QCoreApplication.translate("MainWindow", u" ", None))
        self.label_date.setText(QCoreApplication.translate("MainWindow", u" ", None))
        self.label_product_weight.setText(QCoreApplication.translate("MainWindow", u"Weight: -", None))
        self.label_product_count.setText(QCoreApplication.translate("MainWindow", u"Count: -", None))
        self.pushButton_start.setText(QCoreApplication.translate("MainWindow", u"Start", None))
        self.pushButton_calibrate.setText(QCoreApplication.translate("MainWindow", u"Calibrate", None))
        self.pushButton_home.setText(QCoreApplication.translate("MainWindow", u"Signout", None))
        self.label_account.setText(QCoreApplication.translate("MainWindow", u"", None))
    # retranslateUi
