from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Role(db.Model):
    __tablename__ = "Роли"
    id = db.Column("id_роли", db.Integer, primary_key=True)
    name = db.Column("Роль_сотрудника", db.String(50), unique=True, nullable=False)

    users = db.relationship("User", backref="role", lazy=True)


class User(db.Model):
    __tablename__ = "Пользователи"
    id = db.Column("id_пользователя", db.Integer, primary_key=True)
    full_name = db.Column("ФИО", db.String(200), nullable=False)
    login = db.Column("Логин", db.String(50), unique=True, nullable=False)
    password = db.Column("Пароль", db.String(255), nullable=False)
    role_id = db.Column(
        "id_роли", db.Integer, db.ForeignKey("Роли.id_роли"), nullable=False
    )


class Manufacturer(db.Model):
    __tablename__ = "Производители"
    id = db.Column("id_производителя", db.Integer, primary_key=True)
    name = db.Column("Производитель", db.String(255), unique=True, nullable=False)

    products = db.relationship("Product", backref="manufacturer", lazy=True)


class Supplier(db.Model):
    __tablename__ = "Поставщики"
    id = db.Column("id_поставщика", db.Integer, primary_key=True)
    name = db.Column("Поставщик", db.String(255), unique=True, nullable=False)

    products = db.relationship("Product", backref="supplier", lazy=True)


class Category(db.Model):
    __tablename__ = "Категории"
    id = db.Column("id_категории", db.Integer, primary_key=True)
    name = db.Column("Категория_товара", db.String(100), unique=True, nullable=False)

    products = db.relationship("Product", backref="category", lazy=True)


class Product(db.Model):
    __tablename__ = "Товар"
    id = db.Column("id_товара", db.Integer, primary_key=True)
    article = db.Column("Артикул", db.String(100), unique=True, nullable=False)
    name = db.Column("Наименование_товара", db.String(255), nullable=False)
    unit = db.Column("Единица_измерения", db.String(20), nullable=False)
    price = db.Column("Цена", db.Numeric(10, 2), nullable=False)
    supplier_id = db.Column(
        "id_поставщика",
        db.Integer,
        db.ForeignKey("Поставщики.id_поставщика"),
        nullable=False,
    )
    manufacturer_id = db.Column(
        "id_производителя",
        db.Integer,
        db.ForeignKey("Производители.id_производителя"),
        nullable=False,
    )
    category_id = db.Column(
        "id_категории",
        db.Integer,
        db.ForeignKey("Категории.id_категории"),
        nullable=False,
    )
    discount = db.Column(
        "Действующая_скидка", db.Numeric(5, 2), nullable=False, default=0
    )
    stock_quantity = db.Column(
        "Кол_во_на_складе", db.Integer, nullable=False, default=0
    )
    description = db.Column("Описание_товара", db.Text)
    photo = db.Column("Фото", db.String(500))

    @property
    def discounted_price(self):
        if self.discount and self.discount > 0:
            return float(self.price) * (1 - float(self.discount) / 100)
        return float(self.price)

    @property
    def has_discount(self):
        return self.discount and self.discount > 0

    @property
    def discount_above_15(self):
        return self.discount and self.discount > 15

    @property
    def out_of_stock(self):
        return self.stock_quantity == 0

    @property
    def photo_path(self):
        if self.photo:
            return f"/static/images/{self.photo}"
        return "/static/images/picture.png"


class PickupPoint(db.Model):
    __tablename__ = "ПунктыВыдачи"
    id = db.Column("id_пункта", db.Integer, primary_key=True)
    address = db.Column(
        "Адрес_пункта_выдачи", db.String(500), unique=True, nullable=False
    )

    orders = db.relationship("Order", backref="pickup_point", lazy=True)


class Order(db.Model):
    __tablename__ = "Заказ"
    id = db.Column("id_заказа", db.Integer, primary_key=True)
    order_number = db.Column("Номер_заказа", db.Integer, nullable=False)
    order_date = db.Column("Дата_заказа", db.Date, nullable=False)
    delivery_date = db.Column("Дата_доставки", db.Date)
    pickup_point_id = db.Column(
        "id_пункта_выдачи",
        db.Integer,
        db.ForeignKey("ПунктыВыдачи.id_пункта"),
        nullable=False,
    )
    user_id = db.Column(
        "id_пользователя",
        db.Integer,
        db.ForeignKey("Пользователи.id_пользователя"),
        nullable=False,
    )
    pickup_code = db.Column("Код_для_получения", db.String(20))
    status = db.Column("Статус_заказа", db.String(50), nullable=False)

    user = db.relationship("User", backref="orders")
    items = db.relationship(
        "OrderItem", backref="order", lazy=True, cascade="all, delete-orphan"
    )


class OrderItem(db.Model):
    __tablename__ = "СоставЗаказа"
    id = db.Column("id_состава", db.Integer, primary_key=True)
    order_id = db.Column(
        "id_заказа", db.Integer, db.ForeignKey("Заказ.id_заказа"), nullable=False
    )
    product_id = db.Column(
        "id_товара", db.Integer, db.ForeignKey("Товар.id_товара"), nullable=False
    )
    quantity = db.Column("Количество", db.Integer, nullable=False)

    product = db.relationship("Product", backref="order_items")
