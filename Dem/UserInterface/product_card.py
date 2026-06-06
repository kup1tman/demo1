"""Карточка одного товара для списка с подсветкой
скидка > 17%        -> фон #FFDEAD
товара нет на складе -> фон голубой (#ADD8E6)
цена снижена         -> старая цена зачёркнута красным, итоговая чёрным

Поиск изображений фото из БД  ищется в папке Sources рядом с модулем
"""

import os

from PySide6.QtWidgets import (
    QFrame, QLabel, QHBoxLayout, QVBoxLayout, QPushButton, QWidget,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap

#  Поиск файлов изображений (не зависит от рабочей папки и регистра имени)

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCES_DIR = os.path.join(MODULE_DIR, "Sources")
PLACEHOLDER_NAME = "picture.png"
_SUBDIRS = ["Sources", "images", "Resources", ""]


def _base_dirs():
    dirs = []
    for d in (MODULE_DIR, os.getcwd()):
        if d and d not in dirs:
            dirs.append(d)
    return dirs


def resolve_image(photo):
    """Возвращает  путь к изображению или None

    Учитывает подпапку Sources и регистр имени
    """
    if not photo:
        return None
    if os.path.isabs(photo) and os.path.isfile(photo):
        return photo
    base = os.path.basename(str(photo))
    if not base:
        return None
    base_low = base.lower()
    for d in _base_dirs():
        for sub in _SUBDIRS:
            folder = os.path.join(d, sub) if sub else d
            direct = os.path.join(folder, base)
            if os.path.isfile(direct):
                return direct
            try:
                for fn in os.listdir(folder):
                    if fn.lower() == base_low:
                        return os.path.join(folder, fn)
            except OSError:
                pass
    return None


def placeholder():
    """Путь к картинке-заглушке picture.png """
    return resolve_image(PLACEHOLDER_NAME)


def icon_path():
    """Путь к иконке приложения .ico"""
    return resolve_image("icon.ico") or resolve_image("icon.png")


def logo_path():
    """Путь к логотипу. Ищет logo.* / логотип.*, иначе использует icon.png."""
    for name in ("logo.png", "logo.jpg", "logo.jpeg", "logo.bmp", "logo.ico",
                 "логотип.png", "логотип.jpg", "Логотип.png"):
        p = resolve_image(name)
        if p:
            return p
    return resolve_image("icon.png") or resolve_image("icon.ico")


def sources_dir():
    """Папка Sources рядом с модулями (создаётся при необходимости)."""
    os.makedirs(SOURCES_DIR, exist_ok=True)
    return SOURCES_DIR


class ProductCard(QFrame):
    clicked = Signal(int)         # id товара (открыть редактирование)
    delete_clicked = Signal(int)  # id товара (удалить)

    def __init__(self, product: dict, is_admin: bool = False):
        super().__init__()
        self.product = product
        self.product_id = product["id"]
        self.is_admin = is_admin

        self.setFrameShape(QFrame.Shape.Box)
        self.setObjectName("card")
        layout = QHBoxLayout(self)

        # фото
        photo = QLabel()
        photo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        photo.setFixedSize(100, 100)
        photo.setFrameShape(QFrame.Shape.Box)
        chosen = resolve_image(product.get("photo")) or placeholder()
        pm = QPixmap(chosen) if chosen else None
        if pm is not None and not pm.isNull():
            photo.setPixmap(pm.scaled(
                100, 100, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
        else:
            photo.setText("Фото")

        # центральный блок
        center = QVBoxLayout()
        header = QLabel(f'{product.get("category", "")} | {product["name"]}')
        header.setStyleSheet("font-weight: bold;")
        header.setWordWrap(True)
        center.addWidget(header)
        if product.get("article"):
            center.addWidget(QLabel(f'Артикул: {product["article"]}'))
        desc = QLabel(f'Описание: {product.get("description", "")}')
        desc.setWordWrap(True)
        center.addWidget(desc)
        center.addWidget(QLabel(f'Производитель: {product.get("manufacturer", "")}'))
        center.addWidget(QLabel(f'Поставщик: {product.get("supplier", "")}'))

        price_label = QLabel()
        price_label.setText(self._price_html(product))
        center.addWidget(price_label)

        center.addWidget(QLabel(f'Ед. измерения: {product.get("unit", "")}'))
        center.addWidget(QLabel(f'Количество на складе: {product.get("stock", 0)}'))

        # правый блок: скидка + кнопки админа
        right = QVBoxLayout()
        discount = QLabel(f'Действующая скидка\n{product.get("discount", 0)}%')
        discount.setAlignment(Qt.AlignmentFlag.AlignCenter)
        discount.setFixedWidth(120)
        discount.setFrameShape(QFrame.Shape.Box)
        right.addWidget(discount)

        if is_admin:
            del_btn = QPushButton("Удалить")
            del_btn.clicked.connect(lambda: self.delete_clicked.emit(self.product_id))
            right.addWidget(del_btn)
        right.addStretch()

        right_box = QWidget()
        right_box.setLayout(right)

        layout.addWidget(photo)
        layout.addLayout(center, stretch=1)
        layout.addWidget(right_box)

        self._apply_background(product)

    def _price_html(self, product) -> str:
        price = float(product.get("price", 0) or 0)
        discount = int(product.get("discount", 0) or 0)
        if discount > 0:
            final = price * (1 - discount / 100)
            return (f'Цена: <span style="text-decoration: line-through; color: red;">'
                    f'{price:.2f} руб.</span> '
                    f'<span style="color: black;">{final:.2f} руб.</span>')
        return f'Цена: {price:.2f} руб.'

    def _apply_background(self, product):
        stock = int(product.get("stock", 0) or 0)
        discount = int(product.get("discount", 0) or 0)
        color = None
        if stock <= 0:
            color = "#ADD8E6"        # нет на складе цвет голубой
        elif discount > 17:
            color = "#FFDEAD"        # большая скидка
        if color:
            self.setStyleSheet(f"#card {{ background-color: {color}; }}")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.product_id)
        super().mousePressEvent(event)