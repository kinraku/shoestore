import os
import uuid
import re
from flask import Flask, render_template, request, redirect, url_for, session, flash
from PIL import Image
from models import (
    db,
    User,
    Product,
    Role,
    Supplier,
    Manufacturer,
    Category,
    Order,
    OrderItem,
    PickupPoint,
)
from sqlalchemy.orm import joinedload

app = Flask(__name__)
app.config["SECRET_KEY"] = "your-secret-key-here"
app.config["SQLALCHEMY_DATABASE_URI"] = "postgresql://kai:@localhost/shoestoredb"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = os.path.join("static", "images")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

db.init_app(app)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_image(file, old_filename=None):
    if file and allowed_file(file.filename):
        if old_filename and old_filename != "picture.png":
            old_path = os.path.join(app.config["UPLOAD_FOLDER"], old_filename)
            if os.path.exists(old_path):
                os.remove(old_path)

        ext = file.filename.rsplit(".", 1)[1].lower()
        new_filename = f"{uuid.uuid4().hex}.{ext}"
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], new_filename)
        file.save(filepath)

        try:
            img = Image.open(filepath)
            img.thumbnail((300, 200), Image.Resampling.LANCZOS)
            img.save(filepath)
        except Exception as e:
            print(f"Ошибка обработки изображения: {e}")

        return new_filename
    return None


def generate_article():
    return f"ART-{uuid.uuid4().hex[:8].upper()}"


@app.context_processor
def inject_user():
    if "user_id" in session and session["user_id"]:
        user = User.query.get(session["user_id"])
        return dict(current_user_name=user.full_name if user else None)
    return dict(current_user_name=None)


@app.route("/")
def index():
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if "guest" in request.form:
            session["role"] = "Гость"
            session["user_id"] = None
            flash("Вы вошли как гость", "info")
            return redirect(url_for("products"))

        login = request.form.get("login")
        password = request.form.get("password")

        if not login or not password:
            flash("Пожалуйста, заполните логин и пароль", "error")
            return render_template("login.html")

        user = User.query.filter_by(login=login).first()
        if user and user.password == password:
            session["user_id"] = user.id
            session["role"] = user.role.name
            flash("Вход выполнен успешно", "success")
            if user.role.name == "Администратор":
                return redirect(url_for("admin_dashboard"))
            elif user.role.name == "Менеджер":
                return redirect(url_for("manager_dashboard"))
            elif user.role.name == "Авторизированный клиент":
                return redirect(url_for("client_dashboard"))
            else:
                return redirect(url_for("products"))
        else:
            flash("Неверный логин или пароль", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Вы вышли из системы", "info")
    return redirect(url_for("login"))


@app.route("/products")
def products():
    role = session.get("role")
    can_filter = role in ["Менеджер", "Администратор"]
    is_admin = role == "Администратор"

    products = Product.query.options(
        joinedload(Product.category),
        joinedload(Product.manufacturer),
        joinedload(Product.supplier),
    ).all()

    suppliers = Supplier.query.all() if can_filter else []

    return render_template(
        "products.html",
        products=products,
        can_filter=can_filter,
        is_admin=is_admin,
        suppliers=suppliers,
    )


@app.route("/products/filter")
def filter_products():
    if session.get("role") not in ["Менеджер", "Администратор"]:
        return {"error": "Access denied"}, 403

    search = request.args.get("search", "").strip()
    supplier_id = request.args.get("supplier_id", "")
    sort_by = request.args.get("sort", "")

    query = Product.query.options(
        joinedload(Product.category),
        joinedload(Product.manufacturer),
        joinedload(Product.supplier),
    )

    if search:
        # Разделяем по пробелам, запятым, точкам
        words = [w for w in re.split(r"[ ,.]+", search) if w]
        if words:
            conditions = []
            for word in words:
                word_condition = db.or_(
                    Product.name.ilike(f"%{word}%"),
                    Product.description.ilike(f"%{word}%"),
                    Product.article.ilike(f"%{word}%"),
                    Product.manufacturer.has(Manufacturer.name.ilike(f"%{word}%")),
                    Product.supplier.has(Supplier.name.ilike(f"%{word}%")),
                )
                conditions.append(word_condition)
            query = query.filter(db.and_(*conditions))

    # Фильтр по поставщику
    if supplier_id and supplier_id != "all":
        query = query.filter(Product.supplier_id == supplier_id)

    # Сортировка
    if sort_by == "asc":
        query = query.order_by(Product.stock_quantity.asc())
    elif sort_by == "desc":
        query = query.order_by(Product.stock_quantity.desc())

    products = query.all()
    is_admin = session.get("role") == "Администратор"
    return render_template("product_cards.html", products=products, is_admin=is_admin)


@app.route("/admin")
def admin_dashboard():
    if session.get("role") != "Администратор":
        flash("Доступ запрещен", "error")
        return redirect(url_for("products"))
    return render_template("admin_dashboard.html")


@app.route("/manager")
def manager_dashboard():
    if session.get("role") != "Менеджер":
        flash("Доступ запрещен", "error")
        return redirect(url_for("products"))
    return render_template("manager_dashboard.html")


@app.route("/client")
def client_dashboard():
    if session.get("role") != "Авторизированный клиент":
        flash("Доступ запрещен", "error")
        return redirect(url_for("products"))
    return render_template("client_dashboard.html")


# Управление товарами


@app.route("/product/add", methods=["GET", "POST"])
def add_product():
    if session.get("role") != "Администратор":
        flash("Доступ запрещен", "error")
        return redirect(url_for("products"))

    categories = Category.query.all()
    manufacturers = Manufacturer.query.all()
    suppliers = Supplier.query.all()

    if request.method == "POST":
        name = request.form.get("name")
        category_id = request.form.get("category_id")
        description = request.form.get("description")
        manufacturer_id = request.form.get("manufacturer_id")
        supplier_id = request.form.get("supplier_id")
        price = request.form.get("price")
        unit = request.form.get("unit")
        stock_quantity = request.form.get("stock_quantity")
        discount = request.form.get("discount")
        photo = request.files.get("photo")

        errors = []
        if not name:
            errors.append("Наименование товара обязательно")
        if not category_id:
            errors.append("Категория обязательна")
        if not manufacturer_id:
            errors.append("Производитель обязателен")
        if not supplier_id:
            errors.append("Поставщик обязателен")
        if not price or float(price) < 0:
            errors.append("Цена должна быть неотрицательной")
        if not unit:
            errors.append("Единица измерения обязательна")
        if not stock_quantity or int(stock_quantity) < 0:
            errors.append("Количество на складе не может быть отрицательным")
        if discount and (float(discount) < 0 or float(discount) > 100):
            errors.append("Скидка должна быть от 0 до 100")

        if errors:
            for error in errors:
                flash(error, "error")
            return render_template(
                "add_edit_product.html",
                product=None,
                categories=categories,
                manufacturers=manufacturers,
                suppliers=suppliers,
                title="Добавление товара",
            )

        photo_filename = None
        if photo and allowed_file(photo.filename):
            photo_filename = save_image(photo)
        else:
            photo_filename = "picture.png"

        article = generate_article()

        new_product = Product(
            article=article,
            name=name,
            unit=unit,
            price=price,
            supplier_id=supplier_id,
            manufacturer_id=manufacturer_id,
            category_id=category_id,
            discount=discount or 0,
            stock_quantity=stock_quantity or 0,
            description=description,
            photo=photo_filename,
        )

        try:
            db.session.add(new_product)
            db.session.commit()
            flash("Товар успешно добавлен", "success")
            return redirect(url_for("products"))
        except Exception as e:
            db.session.rollback()
            flash(f"Ошибка базы данных: {str(e)}", "error")
            return render_template(
                "add_edit_product.html",
                product=None,
                categories=categories,
                manufacturers=manufacturers,
                suppliers=suppliers,
                title="Добавление товара",
            )

    return render_template(
        "add_edit_product.html",
        product=None,
        categories=categories,
        manufacturers=manufacturers,
        suppliers=suppliers,
        title="Добавление товара",
    )


@app.route("/product/edit/<int:id>", methods=["GET", "POST"])
def edit_product(id):
    if session.get("role") != "Администратор":
        flash("Доступ запрещен", "error")
        return redirect(url_for("products"))

    product = Product.query.get_or_404(id)
    categories = Category.query.all()
    manufacturers = Manufacturer.query.all()
    suppliers = Supplier.query.all()

    if request.method == "POST":
        name = request.form.get("name")
        category_id = request.form.get("category_id")
        description = request.form.get("description")
        manufacturer_id = request.form.get("manufacturer_id")
        supplier_id = request.form.get("supplier_id")
        price = request.form.get("price")
        unit = request.form.get("unit")
        stock_quantity = request.form.get("stock_quantity")
        discount = request.form.get("discount")
        photo = request.files.get("photo")

        errors = []
        if not name:
            errors.append("Наименование товара обязательно")
        if not category_id:
            errors.append("Категория обязательна")
        if not manufacturer_id:
            errors.append("Производитель обязателен")
        if not supplier_id:
            errors.append("Поставщик обязателен")
        if not price or float(price) < 0:
            errors.append("Цена должна быть неотрицательной")
        if not unit:
            errors.append("Единица измерения обязательна")
        if not stock_quantity or int(stock_quantity) < 0:
            errors.append("Количество на складе не может быть отрицательным")
        if discount and (float(discount) < 0 or float(discount) > 100):
            errors.append("Скидка должна быть от 0 до 100")

        if errors:
            for error in errors:
                flash(error, "error")
            return render_template(
                "add_edit_product.html",
                product=product,
                categories=categories,
                manufacturers=manufacturers,
                suppliers=suppliers,
                title="Редактирование товара",
            )

        if photo and allowed_file(photo.filename):
            new_photo = save_image(photo, product.photo)
            if new_photo:
                product.photo = new_photo

        product.name = name
        product.category_id = category_id
        product.description = description
        product.manufacturer_id = manufacturer_id
        product.supplier_id = supplier_id
        product.price = price
        product.unit = unit
        product.stock_quantity = stock_quantity
        product.discount = discount or 0

        try:
            db.session.commit()
            flash("Товар успешно обновлен", "success")
            return redirect(url_for("products"))
        except Exception as e:
            db.session.rollback()
            flash(f"Ошибка базы данных: {str(e)}", "error")
            return render_template(
                "add_edit_product.html",
                product=product,
                categories=categories,
                manufacturers=manufacturers,
                suppliers=suppliers,
                title="Редактирование товара",
            )

    return render_template(
        "add_edit_product.html",
        product=product,
        categories=categories,
        manufacturers=manufacturers,
        suppliers=suppliers,
        title="Редактирование товара",
    )


@app.route("/product/delete/<int:id>", methods=["POST"])
def delete_product(id):
    if session.get("role") != "Администратор":
        flash("Доступ запрещен", "error")
        return redirect(url_for("products"))

    product = Product.query.get_or_404(id)

    order_items = OrderItem.query.filter_by(product_id=id).first()
    if order_items:
        flash("Невозможно удалить товар, так как он присутствует в заказах", "error")
        return redirect(url_for("products"))

    if product.photo and product.photo != "picture.png":
        photo_path = os.path.join(app.config["UPLOAD_FOLDER"], product.photo)
        if os.path.exists(photo_path):
            os.remove(photo_path)

    try:
        db.session.delete(product)
        db.session.commit()
        flash("Товар успешно удален", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Ошибка при удалении: {str(e)}", "error")

    return redirect(url_for("products"))


# Управление заказами
def parse_order_items(items_str):
    """
    Парсит строку вида "А112Т4,2;F635R4,2"
    Возвращает список кортежей (article, quantity)
    """
    items = []
    if not items_str:
        return items
    for part in items_str.split(";"):
        part = part.strip()
        if not part:
            continue
        if "," in part:
            article, qty = part.split(",", 1)
            article = article.strip()
            qty = qty.strip()
            try:
                quantity = int(qty)
            except ValueError:
                continue
            if article and quantity > 0:
                items.append((article, quantity))
    return items


@app.route("/orders")
def orders():
    role = session.get("role")
    if role not in ["Менеджер", "Администратор"]:
        flash("Доступ запрещен", "error")
        return redirect(url_for("products"))

    orders_list = (
        Order.query.options(
            joinedload(Order.pickup_point),
            joinedload(Order.user),
            joinedload(Order.items).joinedload(OrderItem.product),
        )
        .order_by(Order.order_date.desc())
        .all()
    )

    is_admin = role == "Администратор"

    return render_template("orders.html", orders=orders_list, is_admin=is_admin)


@app.route("/order/add", methods=["GET", "POST"])
def add_order():
    if session.get("role") != "Администратор":
        flash("Доступ запрещен", "error")
        return redirect(url_for("products"))

    pickup_points = PickupPoint.query.all()
    products = Product.query.all()

    if request.method == "POST":
        order_number_str = request.form.get("order_number")
        status = request.form.get("status")
        pickup_point_id = request.form.get("pickup_point_id")
        order_date = request.form.get("order_date")
        delivery_date = request.form.get("delivery_date")
        items_str = request.form.get("items", "")

        # Преобразование номера
        try:
            order_number = int(order_number_str)
        except (TypeError, ValueError):
            flash("Номер заказа должен быть числом", "error")
            return render_template(
                "add_edit_order.html",
                order=None,
                pickup_points=pickup_points,
                products=products,
                title="Добавление заказа",
            )

        errors = []
        if not order_number_str:
            errors.append("Номер заказа обязателен")
        else:
            existing = Order.query.filter_by(order_number=order_number).first()
            if existing:
                errors.append("Заказ с таким номером уже существует")
        if not status:
            errors.append("Статус заказа обязателен")
        if not pickup_point_id:
            errors.append("Пункт выдачи обязателен")
        if not order_date:
            errors.append("Дата заказа обязательна")
        if not items_str:
            errors.append("Артикулы товаров обязательны")

        # Парсим артикулы
        parsed_items = parse_order_items(items_str)
        if not parsed_items:
            errors.append(
                "Неверный формат артикулов. Используйте: артикул,количество; артикул,количество (без пробелов)"
            )

        if errors:
            for error in errors:
                flash(error, "error")
            return render_template(
                "add_edit_order.html",
                order=None,
                pickup_points=pickup_points,
                products=products,
                title="Добавление заказа",
                items_str=items_str,
            )

        # Проверяем, что все артикулы существуют
        for article, qty in parsed_items:
            product = Product.query.filter_by(article=article).first()
            if not product:
                flash(f'Товар с артикулом "{article}" не найден', "error")
                return render_template(
                    "add_edit_order.html",
                    order=None,
                    pickup_points=pickup_points,
                    products=products,
                    title="Добавление заказа",
                    items_str=items_str,
                )

        pickup_code = f"CODE-{order_number}"

        new_order = Order(
            order_number=order_number,
            order_date=order_date,
            delivery_date=delivery_date if delivery_date else None,
            pickup_point_id=pickup_point_id,
            user_id=session["user_id"],
            pickup_code=pickup_code,
            status=status,
        )

        try:
            db.session.add(new_order)
            db.session.flush()  # чтобы получить id заказа

            # Добавляем позиции
            for article, qty in parsed_items:
                product = Product.query.filter_by(article=article).first()
                order_item = OrderItem(
                    order_id=new_order.id, product_id=product.id, quantity=qty
                )
                db.session.add(order_item)

            db.session.commit()
            flash("Заказ успешно добавлен", "success")
            return redirect(url_for("orders"))
        except Exception as e:
            db.session.rollback()
            flash(f"Ошибка базы данных: {str(e)}", "error")
            return render_template(
                "add_edit_order.html",
                order=None,
                pickup_points=pickup_points,
                products=products,
                title="Добавление заказа",
                items_str=items_str,
            )

    return render_template(
        "add_edit_order.html",
        order=None,
        pickup_points=pickup_points,
        products=products,
        title="Добавление заказа",
        items_str="",
    )


@app.route("/order/edit/<int:id>", methods=["GET", "POST"])
def edit_order(id):
    if session.get("role") != "Администратор":
        flash("Доступ запрещен", "error")
        return redirect(url_for("products"))

    order = Order.query.get_or_404(id)
    pickup_points = PickupPoint.query.all()
    products = Product.query.all()

    # Формируем строку для существующих позиций
    existing_items_str = ";".join(
        [f"{item.product.article},{item.quantity}" for item in order.items]
    )

    if request.method == "POST":
        order_number_str = request.form.get("order_number")
        status = request.form.get("status")
        pickup_point_id = request.form.get("pickup_point_id")
        order_date = request.form.get("order_date")
        delivery_date = request.form.get("delivery_date")
        items_str = request.form.get("items", "")

        try:
            order_number = int(order_number_str)
        except (TypeError, ValueError):
            flash("Номер заказа должен быть числом", "error")
            return render_template(
                "add_edit_order.html",
                order=order,
                pickup_points=pickup_points,
                products=products,
                title="Редактирование заказа",
                items_str=items_str,
            )

        errors = []
        if not order_number_str:
            errors.append("Номер заказа обязателен")
        else:
            if order_number != order.order_number:
                existing = Order.query.filter_by(order_number=order_number).first()
                if existing:
                    errors.append("Заказ с таким номером уже существует")
        if not status:
            errors.append("Статус заказа обязателен")
        if not pickup_point_id:
            errors.append("Пункт выдачи обязателен")
        if not order_date:
            errors.append("Дата заказа обязательна")
        if not items_str:
            errors.append("Артикулы товаров обязательны")

        parsed_items = parse_order_items(items_str)
        if not parsed_items:
            errors.append(
                "Неверный формат артикулов. Используйте: артикул,количество; артикул,количество (без пробелов)"
            )

        if errors:
            for error in errors:
                flash(error, "error")
            return render_template(
                "add_edit_order.html",
                order=order,
                pickup_points=pickup_points,
                products=products,
                title="Редактирование заказа",
                items_str=items_str,
            )

        # Проверка существования товаров
        for article, qty in parsed_items:
            product = Product.query.filter_by(article=article).first()
            if not product:
                flash(f'Товар с артикулом "{article}" не найден', "error")
                return render_template(
                    "add_edit_order.html",
                    order=order,
                    pickup_points=pickup_points,
                    products=products,
                    title="Редактирование заказа",
                    items_str=items_str,
                )

        # Обновляем заказ
        order.order_number = order_number
        order.status = status
        order.pickup_point_id = pickup_point_id
        order.order_date = order_date
        order.delivery_date = delivery_date if delivery_date else None

        try:
            # Удаляем старые позиции
            for item in order.items:
                db.session.delete(item)
            db.session.flush()

            # Добавляем новые
            for article, qty in parsed_items:
                product = Product.query.filter_by(article=article).first()
                order_item = OrderItem(
                    order_id=order.id, product_id=product.id, quantity=qty
                )
                db.session.add(order_item)

            db.session.commit()
            flash("Заказ успешно обновлен", "success")
            return redirect(url_for("orders"))
        except Exception as e:
            db.session.rollback()
            flash(f"Ошибка базы данных: {str(e)}", "error")
            return render_template(
                "add_edit_order.html",
                order=order,
                pickup_points=pickup_points,
                products=products,
                title="Редактирование заказа",
                items_str=items_str,
            )

    return render_template(
        "add_edit_order.html",
        order=order,
        pickup_points=pickup_points,
        products=products,
        title="Редактирование заказа",
        items_str=existing_items_str,
    )


@app.route("/order/delete/<int:id>", methods=["POST"])
def delete_order(id):
    if session.get("role") != "Администратор":
        flash("Доступ запрещен", "error")
        return redirect(url_for("products"))

    order = Order.query.get_or_404(id)

    try:
        db.session.delete(order)
        db.session.commit()
        flash("Заказ успешно удален", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Ошибка при удалении: {str(e)}", "error")

    return redirect(url_for("orders"))


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
