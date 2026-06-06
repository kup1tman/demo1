"""список товаров

Доступно всем ролям (гость, клиент, менеджер, администратор)
Поиск / сортировка / фильтр по поставщику для менеджера и администратора
Добавление / редактирование / удаление товара для администратора
Кнопка «Заказы» для менеджер и администратор
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QListWidgetItem, QLineEdit, QComboBox, QMessageBox, QFrame,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap

from UserInterface.product_card import ProductCard, logo_path
from UserInterface.product_form import ProductForm
from UserInterface.orders_window import OrdersWindow


class MainWindow(QWidget):
    def __init__(self, db, user, on_logout):
        super().__init__()
        self.db = db
        self.user = user
        self.on_logout = on_logout
        self.kind = user["kind"]
        self.is_admin = self.kind == "admin"
        self.can_manage = self.kind in ("admin", "manager")  # поиск/сорт/фильтр/заказы

        self._edit_window = None     # запрет более одного окна редактирования
        self._orders_window = None

        self.setWindowTitle("Список товаров")
        self.resize(760, 560)
        self._build_ui()
        self.reload()

    # ------------------------------------------------------------------ #
    def _build_ui(self):
        self.setObjectName("screen")
        root = QVBoxLayout(self)

        # верхняя панель логотип + заголовок + ФИО + выход
        topbar = QFrame()
        topbar.setObjectName("topbar")
        top = QHBoxLayout(topbar)
        logo = logo_path()
        if logo:
            pix = QPixmap(logo)
            if not pix.isNull():
                logo_lbl = QLabel()
                # масштаб с сохранением пропорций, цвет не меняется
                logo_lbl.setPixmap(pix.scaledToHeight(
                    40, Qt.TransformationMode.SmoothTransformation))
                top.addWidget(logo_lbl)
        top.addWidget(QLabel("<b>Список товаров</b>"))
        top.addStretch()
        top.addWidget(QLabel(self.user["fio"]))
        logout = QPushButton("Выход")
        logout.clicked.connect(self._logout)
        top.addWidget(logout)
        root.addWidget(topbar)

        # панель действий ролей
        actions = QHBoxLayout()
        if self.can_manage:
            orders_btn = QPushButton("Заказы")
            orders_btn.clicked.connect(self._open_orders)
            actions.addWidget(orders_btn)
        if self.is_admin:
            add_btn = QPushButton("Добавить товар")
            add_btn.setObjectName("accent")
            add_btn.clicked.connect(self._add_product)
            actions.addWidget(add_btn)
        actions.addStretch()
        if self.is_admin:
            actions.addWidget(QLabel("Клик по товару — редактирование"))
        root.addLayout(actions)

        # панель поиска/сортировки/фильтра. только менеджер и админ
        if self.can_manage:
            tools = QHBoxLayout()
            self.search = QLineEdit()
            self.search.setPlaceholderText("Поиск по всем полям…")
            self.search.textChanged.connect(self.reload)

            self.sort = QComboBox()
            self.sort.addItems([
                "Без сортировки",
                "Цена ↑", "Цена ↓",
                "Количество ↑", "Количество ↓",
            ])
            self.sort.currentIndexChanged.connect(self.reload)

            self.supplier_filter = QComboBox()
            self.supplier_filter.currentIndexChanged.connect(self.reload)

            tools.addWidget(QLabel("Поиск:"))
            tools.addWidget(self.search, stretch=1)
            tools.addWidget(QLabel("Сортировка:"))
            tools.addWidget(self.sort)
            tools.addWidget(QLabel("Поставщик:"))
            tools.addWidget(self.supplier_filter)
            root.addLayout(tools)
            self._refresh_suppliers()
        else:
            self.search = None
            self.sort = None
            self.supplier_filter = None

        self.list_widget = QListWidget()
        root.addWidget(self.list_widget)

    def _refresh_suppliers(self):
        if self.supplier_filter is None:
            return
        current = self.supplier_filter.currentText()
        self.supplier_filter.blockSignals(True)
        self.supplier_filter.clear()
        self.supplier_filter.addItem("Все поставщики")  # сброс фильтра
        self.supplier_filter.addItems(self.db.get_suppliers())
        idx = self.supplier_filter.findText(current)
        self.supplier_filter.setCurrentIndex(idx if idx >= 0 else 0)
        self.supplier_filter.blockSignals(False)


    def _sort_params(self):
        if self.sort is None:
            return None, "ASC"
        mapping = {
            "Цена ↑": ("price", "ASC"),
            "Цена ↓": ("price", "DESC"),
            "Количество ↑": ("stock", "ASC"),
            "Количество ↓": ("stock", "DESC"),
        }
        return mapping.get(self.sort.currentText(), (None, "ASC"))

    def reload(self):
        search = self.search.text().strip() if self.search else ""
        supplier = self.supplier_filter.currentText() if self.supplier_filter else None
        sort_field, sort_dir = self._sort_params()

        try:
            products = self.db.get_products(search, supplier, sort_field, sort_dir)
        except Exception as e:
            self.db.conn.rollback()
            QMessageBox.critical(self, "Ошибка", f"Не удалось получить данные:\n{e}")
            return

        self.list_widget.clear()
        for product in products:
            try:
                card = ProductCard(product, is_admin=self.is_admin)
            except Exception as e:
                print("Ошибка карточки товара:", e, file=__import__("sys").stderr)
                continue
            if self.is_admin:
                # QueuedConnection открытие формы и reload() произойдут ПОСЛЕ
                # того, как событие клика по карточке полностью завершится
                # иначе карточка удаляется в reload() прямо во время своего
                # же mousePressEvent  access violation (0xC0000005).
                card.clicked.connect(self._edit_product,
                                     Qt.ConnectionType.QueuedConnection)
                card.delete_clicked.connect(self._delete_product,
                                            Qt.ConnectionType.QueuedConnection)
            item = QListWidgetItem(self.list_widget)
            item.setSizeHint(card.sizeHint())
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, card)


    #  Действия администратора

    def _add_product(self):
        if self._edit_window is not None:
            QMessageBox.warning(self, "Внимание",
                                "Уже открыто окно редактирования товара.")
            return
        self._open_product_form(None)

    def _edit_product(self, product_id):
        if self._edit_window is not None:
            QMessageBox.warning(self, "Внимание",
                                "Уже открыто окно редактирования товара.")
            return
        self._open_product_form(product_id)

    def _open_product_form(self, product_id):
        try:
            form = ProductForm(self.db, product_id=product_id, parent=self)
            self._edit_window = form
            result = form.exec()
            self._edit_window = None
            if result:
                if self.can_manage:
                    self._refresh_suppliers()
                self.reload()
        except Exception as e:
            self._edit_window = None
            try:
                self.db.conn.rollback()
            except Exception:
                pass
            QMessageBox.critical(self, "Ошибка", f"Не удалось открыть форму товара:\n{e}")

    def _delete_product(self, product_id):
        product = self.db.get_product(product_id)
        article = product.get("article") if product else None
        if article and self.db.is_product_in_order(article):
            QMessageBox.warning(
                self, "Удаление невозможно",
                "Этот товар присутствует в заказе и не может быть удалён.")
            return
        ok = QMessageBox.question(
            self, "Подтверждение удаления",
            f"Удалить товар №{product_id}? Действие необратимо.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if ok != QMessageBox.StandardButton.Yes:
            return
        try:
            self.db.delete_product(product_id)
        except Exception as e:
            self.db.conn.rollback()
            QMessageBox.critical(self, "Ошибка удаления", str(e))
            return
        self.reload()


    def _open_orders(self):
        self.hide()
        self._orders_window = OrdersWindow(self.db, self.user, on_back=self.show)
        self._orders_window.show()

    def _logout(self):
        self.on_logout()
        self.close()