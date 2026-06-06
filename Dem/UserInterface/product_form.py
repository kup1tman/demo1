"""Форма добавления / редактирования товара в отдельное окно.
артикул, категория и поставщик (категория/поставщик выпадающие списки);
цена с сотыми долями и не отрицательная; количество не отрицательное;
ID не показывается при добавлении, только для чтения при редактировании;
загрузка/замена фото с ограничением 300x200, сохранение в папку Sources,
хранение имени файла в БД, удаление старого файла при замене.
"""

import os
from uuid import uuid4

from PySide6.QtWidgets import (
    QDialog, QFormLayout, QVBoxLayout, QHBoxLayout, QLineEdit, QTextEdit,
    QComboBox, QDoubleSpinBox, QSpinBox, QPushButton, QLabel, QFileDialog,
    QMessageBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

from UserInterface.product_card import resolve_image, placeholder, sources_dir


class ProductForm(QDialog):
    def __init__(self, db, product_id=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.product_id = product_id          # None -> добавление
        self.is_edit = product_id is not None
        self._photo_path = None               # значение, которое уйдёт в БД
        self._old_photo = None                # старый файл (для удаления при замене)

        self.setWindowTitle("Редактирование товара" if self.is_edit
                            else "Добавление товара")
        self.resize(420, 620)
        self._build_ui()
        if self.is_edit:
            self._load()

    def _build_ui(self):
        self.setObjectName("screen")
        root = QVBoxLayout(self)
        form = QFormLayout()

        # фото
        self.preview = QLabel()
        self.preview.setFixedSize(300, 200)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setStyleSheet("border: 1px solid #999;")
        self._set_preview(None)
        photo_btn = QPushButton("Выбрать изображение…")
        photo_btn.clicked.connect(self._choose_photo)

        self.id_label = QLabel("—")
        if self.is_edit:
            form.addRow("ID:", self.id_label)

        self.article = QLineEdit()
        self.name = QLineEdit()

        self.category = QComboBox()
        self.category.setEditable(True)
        self.category.addItems(self.db.get_categories())

        self.description = QTextEdit()
        self.description.setFixedHeight(60)

        self.manufacturer = QLineEdit()

        self.supplier = QComboBox()
        self.supplier.setEditable(True)
        self.supplier.addItems(self.db.get_suppliers())

        self.price = QDoubleSpinBox()
        self.price.setDecimals(2)
        self.price.setMaximum(1_000_000_000)
        self.price.setMinimum(0)            # не отрицательная

        self.unit = QLineEdit()

        self.stock = QSpinBox()
        self.stock.setMaximum(1_000_000_000)
        self.stock.setMinimum(0)            # не отрицательное

        self.discount = QSpinBox()
        self.discount.setMaximum(100)
        self.discount.setMinimum(0)

        form.addRow("Фото:", self.preview)
        form.addRow("", photo_btn)
        form.addRow("Артикул:", self.article)
        form.addRow("Наименование:", self.name)
        form.addRow("Категория:", self.category)
        form.addRow("Описание:", self.description)
        form.addRow("Производитель:", self.manufacturer)
        form.addRow("Поставщик:", self.supplier)
        form.addRow("Цена:", self.price)
        form.addRow("Ед. измерения:", self.unit)
        form.addRow("Количество на складе:", self.stock)
        form.addRow("Действующая скидка, %:", self.discount)
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

    def _set_preview(self, photo):
        chosen = resolve_image(photo) or placeholder()
        pm = QPixmap(chosen) if chosen else None
        if pm is not None and not pm.isNull():
            self.preview.setPixmap(pm.scaled(
                300, 200, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
        else:
            self.preview.setText("Нет фото")

    def _choose_photo(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите изображение", "",
            "Изображения (*.png *.jpg *.jpeg *.bmp)")
        if not path:
            return
        pix = QPixmap(path)
        if pix.isNull():
            QMessageBox.warning(self, "Ошибка",
                                "Не удалось загрузить изображение.")
            return
        # ограничение размера 300x200
        pix = pix.scaled(300, 200, Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
        folder = sources_dir()                      # папка Sources рядом с модулями
        filename = f"{uuid4().hex}.png"
        full = os.path.join(folder, filename)
        pix.save(full, "PNG")
        # в БД храним только имя файла
        self._photo_path = filename
        self._set_preview(filename)

    def _load(self):
        p = self.db.get_product(self.product_id)
        if not p:
            QMessageBox.critical(self, "Ошибка", "Товар не найден.")
            self.reject()
            return
        self.id_label.setText(str(p["id"]))
        self.article.setText(p.get("article") or "")
        self.name.setText(p["name"] or "")
        self.category.setCurrentText(p["category"] or "")
        self.description.setPlainText(p["description"] or "")
        self.manufacturer.setText(p["manufacturer"] or "")
        self.supplier.setCurrentText(p["supplier"] or "")
        self.price.setValue(float(p["price"] or 0))
        self.unit.setText(p["unit"] or "")
        self.stock.setValue(int(p["stock"] or 0))
        self.discount.setValue(int(p["discount"] or 0))
        self._old_photo = p["photo"]
        self._photo_path = p["photo"]
        self._set_preview(p["photo"])

    def _save(self):
        if not self.name.text().strip():
            QMessageBox.warning(self, "Проверка данных",
                                "Укажите наименование товара.")
            return

        data = {
            "article": self.article.text().strip(),
            "name": self.name.text().strip(),
            "category": self.category.currentText().strip(),
            "description": self.description.toPlainText().strip(),
            "manufacturer": self.manufacturer.text().strip(),
            "supplier": self.supplier.currentText().strip(),
            "price": round(self.price.value(), 2),
            "discount": self.discount.value(),
            "unit": self.unit.text().strip(),
            "stock": self.stock.value(),
            "photo": self._photo_path,
        }
        try:
            if self.is_edit:
                self.db.update_product(self.product_id, data)
                # удалить старый файл, если фото заменили
                if (self._old_photo and self._old_photo != self._photo_path):
                    old = resolve_image(self._old_photo)
                    if old and os.path.exists(old):
                        try:
                            os.remove(old)
                        except OSError:
                            pass
            else:
                self.db.add_product(data)
        except Exception as e:
            self.db.conn.rollback()
            QMessageBox.critical(self, "Ошибка сохранения", str(e))
            return
        self.accept()