"""Вход в приложение."""

import sys
import faulthandler
import traceback

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QFont, QIcon

from DataBase.database import Database
from UserInterface.login_window import LoginWindow
from UserInterface.product_card import icon_path

faulthandler.enable()

# Палитра:
#основной фон    — белый (#FFFFFF)
#дополнительный  — #F5DEB3 (панели, обычные кнопки)
#акцент действия — #DEB887 (целевые кнопки: Войти, Сохранить, Добавить…)
#скидка > 17%    — #FFDEAD (задаётся в карточке товара)
APP_STYLESHEET = """
QWidget#screen { background-color: #FFFFFF; }
QFrame#topbar, QFrame#toolbar { background-color: #F5DEB3; }
QPushButton {
    background-color: #F5DEB3;
    border: 1px solid #DEB887;
    border-radius: 4px;
    padding: 4px 12px;
}
QPushButton:hover { background-color: #DEB887; }
QPushButton#accent {
    background-color: #DEB887;
    border: 1px solid #CDAA7D;
    font-weight: bold;
}
QPushButton#accent:hover { background-color: #CDAA7D; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QDateEdit {
    background-color: #FFFFFF;
}
"""


def _excepthook(exc_type, exc_value, exc_tb):
    """Перехватывает исключения в слотах Qt: показывает их и не роняет процесс."""
    text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    print(text, file=sys.stderr)
    try:
        QMessageBox.critical(None, "Необработанная ошибка",
                             f"{exc_type.__name__}: {exc_value}")
    except Exception:
        pass


sys.excepthook = _excepthook


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)

    # шрифт для всего приложения
    app.setFont(QFont("Arial", 10))
    # иконка приложения, если найдена
    ico = icon_path()
    if ico:
        app.setWindowIcon(QIcon(ico))
    # цветовая схема
    app.setStyleSheet(APP_STYLESHEET)

    try:
        db = Database()
    except Exception as e:
        QMessageBox.critical(
            None, "Ошибка подключения к БД",
            f"Не удалось подключиться к базе данных:\n{e}\n\n"
            "Проверьте настройки в constants.py и что PostgreSQL запущен.")
        sys.exit(1)

    window = LoginWindow(db)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()