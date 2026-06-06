"""Окно списка заказов. Просмотр для менеджер и администратор
Добавление / редактирование / удаление. только администратор
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QMessageBox, QAbstractItemView, QHeaderView, QFrame,
)
from PySide6.QtCore import Qt

from UserInterface.order_form import OrderForm


class OrdersWindow(QWidget):
    def __init__(self, db, user, on_back):
        super().__init__()
        self.db = db
        self.user = user
        self.on_back = on_back
        self.is_admin = user["kind"] == "admin"

        self.setWindowTitle("Заказы")
        self.resize(760, 480)
        self._build_ui()
        self.reload()

    def _build_ui(self):
        self.setObjectName("screen")
        root = QVBoxLayout(self)

        topbar = QFrame()
        topbar.setObjectName("topbar")
        top = QHBoxLayout(topbar)
        back = QPushButton("← Назад")
        back.clicked.connect(self._go_back)
        top.addWidget(back)
        top.addWidget(QLabel("<b>Список заказов</b>"))
        top.addStretch()
        top.addWidget(QLabel(self.user["fio"]))
        root.addWidget(topbar)

        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(
            ["№", "Артикул заказа", "Статус", "Адрес пункта выдачи",
             "ФИО клиента", "Код", "Дата заказа", "Дата выдачи"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        # убираем лишнюю нумерацию строк слева (есть столбец «№»)
        self.table.verticalHeader().setVisible(False)
        # столбцы узкие под содержимое, широкие текстовые тянутся под ширину окна
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        for col in (1, 3, 4):   # Артикул заказа, Адрес пункта выдачи, ФИО клиента
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        self.table.cellDoubleClicked.connect(self._edit_selected)
        root.addWidget(self.table)

        if self.is_admin:
            bar = QHBoxLayout()
            add = QPushButton("Добавить заказ")
            add.setObjectName("accent")
            add.clicked.connect(self._add)
            edit = QPushButton("Редактировать")
            edit.clicked.connect(self._edit_selected)
            delete = QPushButton("Удалить заказ")
            delete.clicked.connect(self._delete)
            bar.addWidget(add)
            bar.addWidget(edit)
            bar.addWidget(delete)
            bar.addStretch()
            root.addLayout(bar)

    def reload(self):
        orders = self.db.get_orders()
        self.table.setRowCount(len(orders))
        for r, o in enumerate(orders):
            values = [
                o["id"], o["article"], o["status"], o["pickup_address"],
                o.get("client_fio"), o.get("pickup_code"),
                o["order_date"].isoformat() if o["order_date"] else "",
                o["delivery_date"].isoformat() if o["delivery_date"] else "",
            ]
            for c, val in enumerate(values):
                item = QTableWidgetItem("" if val is None else str(val))
                if c != 1:  # артикул оставляем по левому краю
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(r, c, item)

    def _selected_id(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        return int(self.table.item(row, 0).text())

    def _add(self):
        if OrderForm(self.db, parent=self).exec():
            self.reload()

    def _edit_selected(self, *args):
        if not self.is_admin:
            return
        order_id = self._selected_id()
        if order_id is None:
            QMessageBox.information(self, "Заказы",
                                    "Выберите заказ для редактирования.")
            return
        if OrderForm(self.db, order_id=order_id, parent=self).exec():
            self.reload()

    def _delete(self):
        order_id = self._selected_id()
        if order_id is None:
            QMessageBox.information(self, "Заказы", "Выберите заказ для удаления.")
            return
        ok = QMessageBox.question(
            self, "Подтверждение",
            f"Удалить заказ №{order_id}? Действие необратимо.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if ok != QMessageBox.StandardButton.Yes:
            return
        try:
            self.db.delete_order(order_id)
        except Exception as e:
            self.db.conn.rollback()
            QMessageBox.critical(self, "Ошибка удаления", str(e))
            return
        self.reload()

    def _go_back(self):
        self.on_back()
        self.close()