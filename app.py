import os
import uuid
import re
from flask import Flask, render_template, request, redirect, url_for, session, flash
from PIL import Image
from models import (
    db,
    User,
    Product,
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


def validate_product_data(data):
    errors = []
    if not data.get("name"):
        errors.append("Наименование товара обязательно")
    if not data.get("category_id"):
        errors.append("Категория обязательна")
    if not data.get("manufacturer_id"):
        errors.append("Производитель обязателен")
    if not data.get("supplier_id"):
        errors.append("Поставщик обязателен")

    # Обработка цены с проверкой на число
    price_str = data.get("price")
    if not price_str:
        errors.append("Цена обязательна")
    else:
        try:
            price = float(price_str)
            if price < 0:
                errors.append("Цена должна быть неотрицательной")
        except ValueError:
            errors.append("Цена должна быть числом")

    if not data.get("unit"):
        errors.append("Единица измерения обязательна")

    # Обработка количества с проверкой на число
    stock_str = data.get("stock_quantity")
    if not stock_str:
        errors.append("Количество на складе обязательно")
    else:
        try:
            stock = int(stock_str)
            if stock < 0:
                errors.append("Количество на складе не может быть отрицательным")
        except ValueError:
            errors.append("Количество на складе должно быть целым числом")

    discount = data.get("discount")
    if discount:
        try:
            discount_val = float(discount)
            if discount_val < 0 or discount_val > 100:
                errors.append("Скидка должна быть от 0 до 100")
        except ValueError:
            errors.append("Скидка должна быть числом")
    return errors


def parse_order_items(items_str):
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


def validate_order_data(data, exclude_unique_check=False):
    errors = []
    order_number = None
    order_number_str = data.get("order_number")
    if not order_number_str:
        errors.append("Номер заказа обязателен")
    else:
        try:
            order_number = int(order_number_str)
        except ValueError:
            errors.append("Номер заказа должен быть числом")
        else:
            if (
                    not exclude_unique_check
                    and Order.query.filter_by(order_number=order_number).first()
            ):
                errors.append("Заказ с таким номером уже существует")

    if not data.get("status"):
        errors.append("Статус заказа обязателен")
    if not data.get("pickup_point_id"):
        errors.append("Пункт выдачи обязателен")
    if not data.get("order_date"):
        errors.append("Дата заказа обязательна")

    items_str = data.get("items", "")
    parsed_items = parse_order_items(items_str)
    if not parsed_items:
        errors.append(
            "Неверный формат артикулов. Используйте: артикул,количество; артикул,количество (без пробелов)"
        )
    else:
        for article, _ in parsed_items:
            if not Product.query.filter_by(article=article).first():
                errors.append(f'Товар с артикулом "{article}" не найден')
    return errors, parsed_items, order_number


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
    # Сбрасываем флаг редактирования при выходе
    session.pop("editing_product_id", None)
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
                    # Добавляем поиск по категории
                    Product.category.has(Category.name.ilike(f"%{word}%")),
                )
                conditions.append(word_condition)
            query = query.filter(db.and_(*conditions))

    if supplier_id and supplier_id != "all":
        query = query.filter(Product.supplier_id == supplier_id)

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
        data = {
            "name": request.form.get("name"),
            "category_id": request.form.get("category_id"),
            "manufacturer_id": request.form.get("manufacturer_id"),
            "supplier_id": request.form.get("supplier_id"),
            "price": request.form.get("price"),
            "unit": request.form.get("unit"),
            "stock_quantity": request.form.get("stock_quantity"),
            "discount": request.form.get("discount"),
        }
        errors = validate_product_data(data)
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

        photo = request.files.get("photo")
        photo_filename = "picture.png"
        if photo and allowed_file(photo.filename):
            photo_filename = save_image(photo)

        article = generate_article()
        new_product = Product(
            article=article,
            name=data["name"],
            unit=data["unit"],
            price=float(data["price"]),
            supplier_id=data["supplier_id"],
            manufacturer_id=data["manufacturer_id"],
            category_id=data["category_id"],
            discount=float(data["discount"]) if data["discount"] else 0,
            stock_quantity=int(data["stock_quantity"]),
            description=request.form.get("description"),
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

    # Защита от открытия нескольких окон редактирования
    editing_product_id = session.get("editing_product_id")
    if editing_product_id and editing_product_id != id:
        flash("Нельзя открыть более одного окна редактирования. Сначала закройте текущее редактирование.", "error")
        return redirect(url_for("products"))

    product = Product.query.get_or_404(id)
    categories = Category.query.all()
    manufacturers = Manufacturer.query.all()
    suppliers = Supplier.query.all()

    if request.method == "POST":
        data = {
            "name": request.form.get("name"),
            "category_id": request.form.get("category_id"),
            "manufacturer_id": request.form.get("manufacturer_id"),
            "supplier_id": request.form.get("supplier_id"),
            "price": request.form.get("price"),
            "unit": request.form.get("unit"),
            "stock_quantity": request.form.get("stock_quantity"),
            "discount": request.form.get("discount"),
        }
        errors = validate_product_data(data)
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

        photo = request.files.get("photo")
        if photo and allowed_file(photo.filename):
            new_photo = save_image(photo, product.photo)
            if new_photo:
                product.photo = new_photo

        product.name = data["name"]
        product.category_id = data["category_id"]
        product.description = request.form.get("description")
        product.manufacturer_id = data["manufacturer_id"]
        product.supplier_id = data["supplier_id"]
        product.price = float(data["price"])
        product.unit = data["unit"]
        product.stock_quantity = int(data["stock_quantity"])
        product.discount = float(data["discount"]) if data["discount"] else 0

        try:
            db.session.commit()
            # Сбрасываем флаг после успешного сохранения
            session.pop("editing_product_id", None)
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

    # Устанавливаем флаг при GET-запросе на редактирование
    session["editing_product_id"] = id
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

    if OrderItem.query.filter_by(product_id=id).first():
        flash("Невозможно удалить товар, так как он присутствует в заказах", "error")
        return redirect(url_for("products"))

    if product.photo and product.photo != "picture.png":
        photo_path = os.path.join(app.config["UPLOAD_FOLDER"], product.photo)
        if os.path.exists(photo_path):
            os.remove(photo_path)

    try:
        db.session.delete(product)
        db.session.commit()
        # Если удаляемый товар редактировался, сбрасываем флаг
        if session.get("editing_product_id") == id:
            session.pop("editing_product_id", None)
        flash("Товар успешно удален", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Ошибка при удалении: {str(e)}", "error")

    return redirect(url_for("products"))


# Управление заказами


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
        data = {
            "order_number": request.form.get("order_number"),
            "status": request.form.get("status"),
            "pickup_point_id": request.form.get("pickup_point_id"),
            "order_date": request.form.get("order_date"),
            "delivery_date": request.form.get("delivery_date"),
            "items": request.form.get("items", ""),
        }
        errors, parsed_items, order_number = validate_order_data(data)

        if errors:
            for error in errors:
                flash(error, "error")
            return render_template(
                "add_edit_order.html",
                order=None,
                pickup_points=pickup_points,
                products=products,
                title="Добавление заказа",
                items_str=data["items"],
            )

        new_order = Order(
            order_number=order_number,
            order_date=data["order_date"],
            delivery_date=data["delivery_date"] or None,
            pickup_point_id=data["pickup_point_id"],
            user_id=session["user_id"],
            pickup_code=f"CODE-{order_number}",
            status=data["status"],
        )

        try:
            db.session.add(new_order)
            db.session.flush()
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
                items_str=data["items"],
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
    existing_items_str = ";".join(
        [f"{item.product.article},{item.quantity}" for item in order.items]
    )

    if request.method == "POST":
        data = {
            "order_number": request.form.get("order_number"),
            "status": request.form.get("status"),
            "pickup_point_id": request.form.get("pickup_point_id"),
            "order_date": request.form.get("order_date"),
            "delivery_date": request.form.get("delivery_date"),
            "items": request.form.get("items", ""),
        }
        errors, parsed_items, order_number = validate_order_data(
            data, exclude_unique_check=True
        )

        # Дополнительная проверка уникальности номера при изменении
        if not errors and order_number and order_number != order.order_number:
            if Order.query.filter_by(order_number=order_number).first():
                errors.append("Заказ с таким номером уже существует")

        if errors:
            for error in errors:
                flash(error, "error")
            return render_template(
                "add_edit_order.html",
                order=order,
                pickup_points=pickup_points,
                products=products,
                title="Редактирование заказа",
                items_str=data["items"],
            )

        order.order_number = order_number
        order.status = data["status"]
        order.pickup_point_id = data["pickup_point_id"]
        order.order_date = data["order_date"]
        order.delivery_date = data["delivery_date"] or None

        try:
            for item in order.items:
                db.session.delete(item)
            db.session.flush()

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
                items_str=data["items"],
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
    