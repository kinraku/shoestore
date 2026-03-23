-- CREATE DATABASE IF NOT EXISTS shoestoredb;

-- \c shoestoredb;

CREATE TABLE Роли (
    ID_роли SERIAL PRIMARY KEY,
    Роль_сотрудника VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE Производители (
    ID_производителя SERIAL PRIMARY KEY,
    Производитель VARCHAR(255) NOT NULL UNIQUE
);

CREATE TABLE Поставщики (
    ID_поставщика SERIAL PRIMARY KEY,
    Поставщик VARCHAR(255) NOT NULL UNIQUE
);

CREATE TABLE Категории (
    ID_категории SERIAL PRIMARY KEY,
    Категория_товара VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE ПунктыВыдачи (
    ID_пункта SERIAL PRIMARY KEY,
    Адрес_пункта_выдачи VARCHAR(500) NOT NULL UNIQUE
);

CREATE TABLE Пользователи (
    ID_пользователя SERIAL PRIMARY KEY,
    ФИО VARCHAR(200) NOT NULL,
    Логин VARCHAR(50) NOT NULL UNIQUE,
    Пароль VARCHAR(255) NOT NULL,
    ID_роли INT NOT NULL REFERENCES Роли(ID_роли)
);

CREATE TABLE Товар (
    ID_товара SERIAL PRIMARY KEY,
    Артикул VARCHAR(100) NOT NULL UNIQUE,
    Наименование_товара VARCHAR(255) NOT NULL,
    Единица_измерения VARCHAR(20) NOT NULL,
    Цена DECIMAL(10, 2) NOT NULL CHECK (Цена >= 0),
    ID_поставщика INT NOT NULL REFERENCES Поставщики(ID_поставщика),
    ID_производителя INT NOT NULL REFERENCES Производители(ID_производителя),
    ID_категории INT NOT NULL REFERENCES Категории(ID_категории),
    Действующая_скидка DECIMAL(5, 2) NOT NULL DEFAULT 0 CHECK (Действующая_скидка >= 0 AND Действующая_скидка <= 100),
    Кол_во_на_складе INT NOT NULL DEFAULT 0 CHECK (Кол_во_на_складе >= 0),
    Описание_товара TEXT,
    Фото VARCHAR(500)
);

CREATE TABLE Заказ (
    ID_заказа SERIAL PRIMARY KEY,
    Номер_заказа INT NOT NULL,
    Дата_заказа DATE NOT NULL,
    Дата_доставки DATE,
    ID_пункта_выдачи INT NOT NULL REFERENCES ПунктыВыдачи(ID_пункта),
    ID_пользователя INT NOT NULL REFERENCES Пользователи(ID_пользователя),
    Код_для_получения VARCHAR(20),
    Статус_заказа VARCHAR(50) NOT NULL
);

CREATE TABLE СоставЗаказа (
    ID_состава SERIAL PRIMARY KEY,
    ID_заказа INT NOT NULL REFERENCES Заказ(ID_заказа) ON DELETE CASCADE,
    ID_товара INT NOT NULL REFERENCES Товар(ID_товара),
    Количество INT NOT NULL CHECK (Количество > 0)
);

CREATE INDEX idx_товар_артикул ON Товар(Артикул);
CREATE INDEX idx_товар_поставщик ON Товар(ID_поставщика);
CREATE INDEX idx_товар_производитель ON Товар(ID_производителя);
CREATE INDEX idx_товар_категория ON Товар(ID_категории);

CREATE INDEX idx_заказ_номер ON Заказ(Номер_заказа);
CREATE INDEX idx_заказ_пользователь ON Заказ(ID_пользователя);
CREATE INDEX idx_заказ_пункт ON Заказ(ID_пункта_выдачи);

CREATE INDEX idx_состав_заказ ON СоставЗаказа(ID_заказа);
CREATE INDEX idx_состав_товар ON СоставЗаказа(ID_товара);

CREATE INDEX idx_пользователи_фио ON Пользователи(ФИО);
CREATE INDEX idx_пользователи_логин ON Пользователи(Логин);