import os
import warnings

import pandas as pd
import psycopg2 as pc2

from constants import db_user, db_password, db_name, db_host, db_port


DEFAULT_STATUSES = ["Новый", "В обработке", "В пути", "Готов к выдаче",
                    "Завершен", "Отменён"]

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))



#  Вспомогательные функции

def role_kind(role: str) -> str:
    r = (role or "").lower()
    if "админ" in r:
        return "admin"
    if "менедж" in r:
        return "manager"
    if "клиент" in r or "client" in r:
        return "client"
    return "client"


def _norm_name(s):
    return s.lower().replace("_", "").replace(" ", "")


def find_file(*candidates):
    """Ищет файл рядом с database.py и в рабочей папке (без учёта регистра/пробелов)."""
    search_dirs = []
    for d in (os.getcwd(), MODULE_DIR):
        if d and d not in search_dirs:
            search_dirs.append(d)
    for d in search_dirs:
        for name in candidates:
            p = os.path.join(d, name)
            if os.path.exists(p):
                return p
    norm = [_norm_name(c) for c in candidates]
    for d in search_dirs:
        try:
            files = os.listdir(d)
        except OSError:
            continue
        for fn in files:
            nfn = _norm_name(fn)
            for nc in norm:
                if nfn.endswith(nc):
                    return os.path.join(d, fn)
    return None


def to_date(value):
    """Любое значение (дата, Timestamp, строка, пусто) -> date или None."""
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if value is None:
        return None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ts = pd.to_datetime(value, errors="coerce", dayfirst=True)
    return ts.date() if pd.notna(ts) else None


def order_codes(article_str):
    """Только коды товаров из строки 'PMEZMH, 2, BPV4MM, 2'."""
    return [c for c, _ in order_items(article_str)]


def order_items(article_str):
    """Пары (артикул, количество) из строки 'PMEZMH, 2, BPV4MM, 2'."""
    toks = [t.strip() for t in str(article_str or "").split(",") if t.strip()]
    items, i = [], 0
    while i < len(toks):
        code = toks[i]
        if code.isdigit():
            i += 1
            continue
        count = 1
        if i + 1 < len(toks) and toks[i + 1].isdigit():
            count = int(toks[i + 1]); i += 2
        else:
            i += 1
        items.append((code, count))
    return items


def get_connection():
    return pc2.connect(dbname=db_name, user=db_user, password=db_password,
                       host=db_host, port=db_port)



class Database:
    def __init__(self):
        self.conn = get_connection()
        self.init_schema()
        self.import_users()
        self.import_pickup_points()
        self.import_products()
        self.import_orders()


    #  Схема
    def init_schema(self):
        with self.conn.cursor() as cur:
            cur.execute("CREATE TABLE IF NOT EXISTS roles ("
                        "id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL)")
            cur.execute("CREATE TABLE IF NOT EXISTS categories ("
                        "id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL)")
            cur.execute("CREATE TABLE IF NOT EXISTS manufacturers ("
                        "id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL)")
            cur.execute("CREATE TABLE IF NOT EXISTS suppliers ("
                        "id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL)")
            cur.execute("CREATE TABLE IF NOT EXISTS pickup_points ("
                        "id SERIAL PRIMARY KEY, address TEXT NOT NULL)")
            cur.execute("CREATE TABLE IF NOT EXISTS order_statuses ("
                        "id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL)")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id       SERIAL PRIMARY KEY,
                    role_id  INTEGER REFERENCES roles(id),
                    fio      TEXT NOT NULL,
                    login    TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL
                )""")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id              SERIAL PRIMARY KEY,
                    article         TEXT UNIQUE,
                    name            TEXT NOT NULL,
                    category_id     INTEGER REFERENCES categories(id),
                    manufacturer_id INTEGER REFERENCES manufacturers(id),
                    supplier_id     INTEGER REFERENCES suppliers(id),
                    description     TEXT,
                    price           NUMERIC(10, 2) NOT NULL DEFAULT 0 CHECK (price >= 0),
                    discount        INTEGER        NOT NULL DEFAULT 0 CHECK (discount >= 0),
                    unit            TEXT,
                    stock           INTEGER        NOT NULL DEFAULT 0 CHECK (stock >= 0),
                    photo           TEXT
                )""")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id              SERIAL PRIMARY KEY,
                    article         TEXT,
                    status_id       INTEGER REFERENCES order_statuses(id),
                    pickup_point_id INTEGER REFERENCES pickup_points(id),
                    client_fio      TEXT,
                    pickup_code     TEXT,
                    order_date      DATE,
                    delivery_date   DATE
                )""")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS order_products (
                    order_id   INTEGER REFERENCES orders(id) ON DELETE CASCADE,
                    product_id INTEGER REFERENCES products(id),
                    count      INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY (order_id, product_id)
                )""")

            # стандартные статусы (на случай, если в данных их нет)
            for st in DEFAULT_STATUSES:
                cur.execute("INSERT INTO order_statuses(name) VALUES (%s) "
                            "ON CONFLICT (name) DO NOTHING", (st,))
        self.conn.commit()


    #  Справочники получить id по имени (создать при отсутствии)

    @staticmethod
    def _lookup_id(cur, table, name, column="name"):
        name = (name or "").strip()
        if not name:
            return None
        cur.execute(f"SELECT id FROM {table} WHERE {column}=%s", (name,))
        row = cur.fetchone()
        if row:
            return row[0]
        cur.execute(f"INSERT INTO {table}({column}) VALUES (%s) RETURNING id", (name,))
        return cur.fetchone()[0]

    def _is_empty(self, table):
        with self.conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            return cur.fetchone()[0] == 0


    #  Импорт из Excel

    def import_users(self):
        if not self._is_empty("users"):
            return
        file = find_file("user_import.xlsx")
        if not file:
            print("[users] user_import.xlsx не найден — пропуск")
            return
        df = pd.read_excel(file).rename(columns={
            "Роль сотрудника": "role", "ФИО": "fio",
            "Логин": "login", "Пароль": "password"})
        with self.conn.cursor() as cur:
            for _, r in df.iterrows():
                role_id = self._lookup_id(cur, "roles", str(r.get("role") or ""))
                cur.execute(
                    "INSERT INTO users(role_id, fio, login, password) "
                    "VALUES (%s,%s,%s,%s) ON CONFLICT (login) DO NOTHING",
                    (role_id, str(r.get("fio") or ""), str(r.get("login") or ""),
                     str(r.get("password") or "")))
        self.conn.commit()
        print("[users] импортировано")

    def import_pickup_points(self):
        if not self._is_empty("pickup_points"):
            return
        file = find_file("Пункты выдачи import.xlsx", "Пункты_выдачи_import.xlsx")
        if not file:
            print("[pickup] файл пунктов выдачи не найден — пропуск")
            return
        df = pd.read_excel(file, header=None)
        addresses = [(str(x).strip(),) for x in df[0].tolist() if str(x).strip()]
        with self.conn.cursor() as cur:
            cur.executemany("INSERT INTO pickup_points(address) VALUES (%s)", addresses)
        self.conn.commit()
        print(f"[pickup] импортировано {len(addresses)}")

    def import_products(self):
        if not self._is_empty("products"):
            return
        file = find_file("Tovar.xlsx")
        if not file:
            print("[products] Tovar.xlsx не найден — пропуск")
            return
        df = pd.read_excel(file).rename(columns={
            "Артикул": "article", "Наименование товара": "name",
            "Единица измерения": "unit", "Цена": "price", "Поставщик": "supplier",
            "Производитель": "manufacturer", "Категория товара": "category",
            "Действующая скидка": "discount", "Кол-во на складе": "stock",
            "Описание товара": "description", "Фото": "photo"})
        with self.conn.cursor() as cur:
            for _, r in df.iterrows():
                cat = self._lookup_id(cur, "categories", r.get("category"))
                man = self._lookup_id(cur, "manufacturers", r.get("manufacturer"))
                sup = self._lookup_id(cur, "suppliers", r.get("supplier"))
                cur.execute(
                    "INSERT INTO products(article, name, category_id, "
                    "manufacturer_id, supplier_id, description, price, discount, "
                    "unit, stock, photo) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT (article) DO NOTHING",
                    (str(r.get("article") or "") or None, str(r.get("name") or ""),
                     cat, man, sup, str(r.get("description") or ""),
                     float(r.get("price") or 0), int(r.get("discount") or 0),
                     str(r.get("unit") or ""), int(r.get("stock") or 0),
                     str(r.get("photo") or "") or None))
        self.conn.commit()
        print("[products] импортировано")

    def import_orders(self):
        if not self._is_empty("orders"):
            return
        file = find_file("Заказ_import.xlsx", "Заказ import.xlsx")
        if not file:
            print("[orders] файл заказов не найден — пропуск")
            return
        df = pd.read_excel(file)
        with self.conn.cursor() as cur:
            cur.execute("SELECT id, address FROM pickup_points ORDER BY id")
            pickup = {i: pid for i, (pid, _) in
                      enumerate([(r[0], r[1]) for r in cur.fetchall()], start=1)}
            for _, r in df.iterrows():
                status_id = self._lookup_id(
                    cur, "order_statuses", str(r.get("Статус заказа") or "").strip())
                num = r.get("Адрес пункта выдачи")
                try:
                    pp_id = pickup.get(int(num))
                except (ValueError, TypeError):
                    pp_id = None
                article = str(r.get("Артикул заказа") or "")
                cur.execute(
                    "INSERT INTO orders(article, status_id, pickup_point_id, "
                    "client_fio, pickup_code, order_date, delivery_date) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                    (article, status_id, pp_id,
                     str(r.get("ФИО авторизированного клиента") or ""),
                     str(r.get("Код для получения") or ""),
                     to_date(r.get("Дата заказа")), to_date(r.get("Дата доставки"))))
                order_id = cur.fetchone()[0]
                self._sync_order_products(cur, order_id, article)
        self.conn.commit()
        print("[orders] импортировано")

    def _sync_order_products(self, cur, order_id, article):
        """Перестраивает связи заказ товар из строки артикул, кол-во ...'."""
        cur.execute("DELETE FROM order_products WHERE order_id=%s", (order_id,))
        for code, count in order_items(article):
            cur.execute("SELECT id FROM products WHERE article=%s", (code,))
            row = cur.fetchone()
            if row:
                cur.execute(
                    "INSERT INTO order_products(order_id, product_id, count) "
                    "VALUES (%s,%s,%s) ON CONFLICT (order_id, product_id) "
                    "DO UPDATE SET count=EXCLUDED.count",
                    (order_id, row[0], count))


    #  Пользователи

    def authenticate(self, login, password):
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT u.id, r.name, u.fio FROM users u "
                "LEFT JOIN roles r ON r.id = u.role_id "
                "WHERE u.login=%s AND u.password=%s", (login, password))
            row = cur.fetchone()
        return {"id": row[0], "role": row[1], "fio": row[2]} if row else None


    #  Товары

    _PRODUCT_SELECT = (
        "SELECT p.id, p.article, p.name, c.name AS category, p.description, "
        "m.name AS manufacturer, s.name AS supplier, p.price, p.discount, "
        "p.unit, p.stock, p.photo "
        "FROM products p "
        "LEFT JOIN categories c ON c.id = p.category_id "
        "LEFT JOIN manufacturers m ON m.id = p.manufacturer_id "
        "LEFT JOIN suppliers s ON s.id = p.supplier_id")

    def _rows_to_products(self, cur):
        cols = [d[0] for d in cur.description]
        out = []
        for row in cur.fetchall():
            item = dict(zip(cols, row))
            item["price"] = float(item["price"]) if item["price"] is not None else 0.0
            out.append(item)
        return out

    def get_products(self, search="", supplier=None, sort_field=None, sort_dir="ASC"):
        query = self._PRODUCT_SELECT
        conditions, params = [], []
        if search:
            like = f"%{search}%"
            conditions.append(
                "(p.article ILIKE %s OR p.name ILIKE %s OR c.name ILIKE %s "
                "OR p.description ILIKE %s OR m.name ILIKE %s OR s.name ILIKE %s "
                "OR p.unit ILIKE %s)")
            params += [like] * 7
        if supplier and supplier != "Все поставщики":
            conditions.append("s.name = %s")
            params.append(supplier)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        if sort_field in ("price", "stock"):
            direction = "DESC" if str(sort_dir).upper() == "DESC" else "ASC"
            query += f" ORDER BY p.{sort_field} {direction}, p.id"
        else:
            query += " ORDER BY p.id"
        with self.conn.cursor() as cur:
            cur.execute(query, params)
            return self._rows_to_products(cur)

    def get_product(self, product_id):
        with self.conn.cursor() as cur:
            cur.execute(self._PRODUCT_SELECT + " WHERE p.id=%s", (product_id,))
            items = self._rows_to_products(cur)
        return items[0] if items else None

    def get_categories(self):
        with self.conn.cursor() as cur:
            cur.execute("SELECT name FROM categories ORDER BY name")
            return [r[0] for r in cur.fetchall()]

    def get_suppliers(self):
        with self.conn.cursor() as cur:
            cur.execute("SELECT name FROM suppliers ORDER BY name")
            return [r[0] for r in cur.fetchall()]

    def add_product(self, data):
        with self.conn.cursor() as cur:
            cat = self._lookup_id(cur, "categories", data.get("category"))
            man = self._lookup_id(cur, "manufacturers", data.get("manufacturer"))
            sup = self._lookup_id(cur, "suppliers", data.get("supplier"))
            cur.execute(
                "INSERT INTO products(article, name, category_id, manufacturer_id, "
                "supplier_id, description, price, discount, unit, stock, photo) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (data.get("article") or None, data["name"], cat, man, sup,
                 data.get("description"), data.get("price", 0),
                 data.get("discount", 0), data.get("unit"),
                 data.get("stock", 0), data.get("photo")))
            new_id = cur.fetchone()[0]
        self.conn.commit()
        return new_id

    def update_product(self, product_id, data):
        with self.conn.cursor() as cur:
            cat = self._lookup_id(cur, "categories", data.get("category"))
            man = self._lookup_id(cur, "manufacturers", data.get("manufacturer"))
            sup = self._lookup_id(cur, "suppliers", data.get("supplier"))
            cur.execute(
                "UPDATE products SET article=%s, name=%s, category_id=%s, "
                "manufacturer_id=%s, supplier_id=%s, description=%s, price=%s, "
                "discount=%s, unit=%s, stock=%s, photo=%s WHERE id=%s",
                (data.get("article") or None, data["name"], cat, man, sup,
                 data.get("description"), data.get("price", 0),
                 data.get("discount", 0), data.get("unit"), data.get("stock", 0),
                 data.get("photo"), product_id))
        self.conn.commit()

    def is_product_in_order(self, article):
        if not article:
            return False
        with self.conn.cursor() as cur:
            cur.execute("SELECT 1 FROM order_products op "
                        "JOIN products p ON p.id = op.product_id "
                        "WHERE p.article=%s LIMIT 1", (article,))
            return cur.fetchone() is not None

    def delete_product(self, product_id):
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM products WHERE id=%s", (product_id,))
        self.conn.commit()


    #  Пункты выдачи, статусы, заказы

    def get_pickup_points(self):
        with self.conn.cursor() as cur:
            cur.execute("SELECT address FROM pickup_points ORDER BY id")
            return [r[0] for r in cur.fetchall()]

    def get_statuses(self):
        with self.conn.cursor() as cur:
            cur.execute("SELECT name FROM order_statuses ORDER BY id")
            return [r[0] for r in cur.fetchall()]

    _ORDER_SELECT = (
        "SELECT o.id, o.article, st.name AS status, pp.address AS pickup_address, "
        "o.client_fio, o.pickup_code, o.order_date, o.delivery_date "
        "FROM orders o "
        "LEFT JOIN order_statuses st ON st.id = o.status_id "
        "LEFT JOIN pickup_points pp ON pp.id = o.pickup_point_id")

    def _rows_to_orders(self, cur):
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def get_orders(self):
        with self.conn.cursor() as cur:
            cur.execute(self._ORDER_SELECT + " ORDER BY o.id")
            return self._rows_to_orders(cur)

    def get_order(self, order_id):
        with self.conn.cursor() as cur:
            cur.execute(self._ORDER_SELECT + " WHERE o.id=%s", (order_id,))
            items = self._rows_to_orders(cur)
        return items[0] if items else None

    def _pickup_id(self, cur, address):
        return self._lookup_id(cur, "pickup_points", address, column="address")

    def add_order(self, data):
        with self.conn.cursor() as cur:
            status_id = self._lookup_id(cur, "order_statuses", data.get("status"))
            pp_id = self._pickup_id(cur, data.get("pickup_address"))
            cur.execute(
                "INSERT INTO orders(article, status_id, pickup_point_id, "
                "client_fio, pickup_code, order_date, delivery_date) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (data.get("article"), status_id, pp_id, data.get("client_fio"),
                 data.get("pickup_code"), data.get("order_date"),
                 data.get("delivery_date")))
            order_id = cur.fetchone()[0]
            self._sync_order_products(cur, order_id, data.get("article"))
        self.conn.commit()
        return order_id

    def update_order(self, order_id, data):
        with self.conn.cursor() as cur:
            status_id = self._lookup_id(cur, "order_statuses", data.get("status"))
            pp_id = self._pickup_id(cur, data.get("pickup_address"))
            cur.execute(
                "UPDATE orders SET article=%s, status_id=%s, pickup_point_id=%s, "
                "client_fio=%s, pickup_code=%s, order_date=%s, delivery_date=%s "
                "WHERE id=%s",
                (data.get("article"), status_id, pp_id, data.get("client_fio"),
                 data.get("pickup_code"), data.get("order_date"),
                 data.get("delivery_date"), order_id))
            self._sync_order_products(cur, order_id, data.get("article"))
        self.conn.commit()

    def delete_order(self, order_id):
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM orders WHERE id=%s", (order_id,))
        self.conn.commit()

    def close(self):
        self.conn.close()