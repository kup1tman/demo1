"""Окно входа

Логин/пароль берутся из БД или вход как гость
После успешного входа открывается главное окно по роли пользователя
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLineEdit, QPushButton, QLabel,
    QMessageBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

from DataBase.database import role_kind
from UserInterface.main_window import MainWindow
from UserInterface.product_card import logo_path


class LoginWindow(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self._main = None

        self.setWindowTitle("Вход в систему")
        self.resize(360, 220)
        self._build_ui()

    def _build_ui(self):
        self.setObjectName("screen")
        root = QVBoxLayout(self)

        # логотип
        logo = logo_path()
        if logo:
            pix = QPixmap(logo)
            if not pix.isNull():
                lbl = QLabel()
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl.setPixmap(pix.scaledToHeight(64, Qt.TransformationMode.SmoothTransformation))
                root.addWidget(lbl)

        title = QLabel("<h2>Авторизация</h2>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(title)

        form = QFormLayout()
        self.login = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Логин:", self.login)
        form.addRow("Пароль:", self.password)
        root.addLayout(form)

        login_btn = QPushButton("Войти")
        login_btn.setObjectName("accent")
        login_btn.clicked.connect(self._login)
        self.password.returnPressed.connect(self._login)
        guest_btn = QPushButton("Войти как гость")
        guest_btn.clicked.connect(self._guest)
        root.addWidget(login_btn)
        root.addWidget(guest_btn)

    def _open_main(self, user):
        self._main = MainWindow(self.db, user, on_logout=self.show)
        self._main.show()
        self.hide()

    def _login(self):
        login = self.login.text().strip()
        password = self.password.text()
        if not login or not password:
            QMessageBox.warning(self, "Проверка данных",
                                "Введите логин и пароль.")
            return
        try:
            user = self.db.authenticate(login, password)
        except Exception as e:
            self.db.conn.rollback()
            QMessageBox.critical(self, "Ошибка", str(e))
            return
        if not user:
            QMessageBox.critical(
                self, "Ошибка авторизации",
                "Неверный логин или пароль.\nПроверьте данные и повторите попытку.")
            return
        user["kind"] = role_kind(user["role"])
        self.password.clear()
        self._open_main(user)

    def _guest(self):
        user = {"id": None, "role": "Гость", "fio": "Гость", "kind": "guest"}
        self._open_main(user)