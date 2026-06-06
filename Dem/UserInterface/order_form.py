"""Форма добавления и редактирования заказа.

Поля по ТЗ: артикул, статус заказа (выпадающий список), адрес пункта выдачи
(выпадающий список из пунктов выдачи), дата заказа, дата выдачи
ФИО клиента и код получения из данных сохраняются (read-only)
"""

from PySide6.QtWidgets import (
    QDialog, QFormLayout, QVBoxLayout, QHBoxLayout, QLineEdit, QComboBox,
    QDateEdit, QPushButton, QLabel, QMessageBox,
)
from PySide6.QtCore import QDate


class OrderForm(QDialog):
    def __init__(self, db, order_id=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.order_id = order_id
        self.is_edit = order_id is not None

        self.setWindowTitle("Редактирование заказа" if self.is_edit
                            else "Добавление заказа")
        self.resize(440, 360)
        self._build_ui()
        if self.is_edit:
            self._load()

    def _build_ui(self):
        self.setObjectName("screen")
        root = QVBoxLayout(self)
        form = QFormLayout()

        self.id_label = QLabel("—")
        if self.is_edit:
            form.addRow("Номер заказа:", self.id_label)

        self.article = QLineEdit()
        self.article.setPlaceholderText("например: PMEZMH, 2, BPV4MM, 2")

        self.status = QComboBox()
        self.status.addItems(self.db.get_statuses())

        self.pickup_address = QComboBox()
        self.pickup_address.setEditable(True)
        self.pickup_address.addItems(self.db.get_pickup_points())

        self.client_fio = QLineEdit()
        self.pickup_code = QLineEdit()

        self.order_date = QDateEdit()
        self.order_date.setCalendarPopup(True)
        self.order_date.setDate(QDate.currentDate())

        self.delivery_date = QDateEdit()
        self.delivery_date.setCalendarPopup(True)
        self.delivery_date.setDate(QDate.currentDate())

        form.addRow("Артикул заказа:", self.article)
        form.addRow("Статус заказа:", self.status)
        form.addRow("Адрес пункта выдачи:", self.pickup_address)
        form.addRow("ФИО клиента:", self.client_fio)
        form.addRow("Код для получения:", self.pickup_code)
        form.addRow("Дата заказа:", self.order_date)
        form.addRow("Дата выдачи:", self.delivery_date)
        root.addLayout(form)

        buttons = QHBoxLayout()
        save = QPushButton("Сохранить")
        save.setObjectName("accent")
        save.clicked.connect(self._save)
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        buttons.addStretch()
        buttons.addWidget(save)
        buttons.addWidget(cancel)
        root.addLayout(buttons)

    def _load(self):
        o = self.db.get_order(self.order_id)
        if not o:
            QMessageBox.critical(self, "Ошибка", "Заказ не найден.")
            self.reject()
            return
        self.id_label.setText(str(o["id"]))
        self.article.setText(o["article"] or "")
        idx = self.status.findText((o["status"] or "").strip())
        self.status.setCurrentIndex(idx if idx >= 0 else 0)
        self.pickup_address.setCurrentText(o["pickup_address"] or "")
        self.client_fio.setText(o.get("client_fio") or "")
        self.pickup_code.setText(o.get("pickup_code") or "")
        if o["order_date"]:
            d = o["order_date"]
            self.order_date.setDate(QDate(d.year, d.month, d.day))
        if o["delivery_date"]:
            d = o["delivery_date"]
            self.delivery_date.setDate(QDate(d.year, d.month, d.day))

    def _save(self):
        if not self.article.text().strip():
            QMessageBox.warning(self, "Проверка данных",
                                "Укажите артикул заказа.")
            return
        data = {
            "article": self.article.text().strip(),
            "status": self.status.currentText(),
            "pickup_address": self.pickup_address.currentText().strip(),
            "client_fio": self.client_fio.text().strip(),
            "pickup_code": self.pickup_code.text().strip(),
            "order_date": self.order_date.date().toPython(),
            "delivery_date": self.delivery_date.date().toPython(),
        }
        try:
            if self.is_edit:
                self.db.update_order(self.order_id, data)
            else:
                self.db.add_order(data)
        except Exception as e:
            self.db.conn.rollback()
            QMessageBox.critical(self, "Ошибка сохранения", str(e))
            return
        self.accept()