DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS coupons;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS customers;

CREATE TABLE customers (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    name              VARCHAR(100) NOT NULL,
    member_rank       VARCHAR(20)  NOT NULL,
    birth_month       INT          NOT NULL,
    region            VARCHAR(50)  NOT NULL,
    first_order_flag  BOOLEAN      NOT NULL DEFAULT FALSE,
    registered_at     TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE products (
    id                 INT AUTO_INCREMENT PRIMARY KEY,
    name               VARCHAR(200) NOT NULL,
    category           VARCHAR(50)  NOT NULL,
    unit_price         INT          NOT NULL,
    weight_gram        INT          NOT NULL,
    tax_included_flag  BOOLEAN      NOT NULL DEFAULT FALSE
);

CREATE TABLE coupons (
    code            VARCHAR(50) PRIMARY KEY,
    discount_type   VARCHAR(20)    NOT NULL,
    discount_value  DECIMAL(10,2)  NOT NULL,
    valid_from      DATE           NOT NULL,
    valid_to        DATE           NOT NULL
);

CREATE TABLE orders (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    customer_id     INT NOT NULL,
    order_date      DATE NOT NULL,
    coupon_code     VARCHAR(50),
    payment_method  VARCHAR(20) NOT NULL,
    status          VARCHAR(20) NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    FOREIGN KEY (coupon_code) REFERENCES coupons(code)
);

CREATE TABLE order_items (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    order_id    INT NOT NULL,
    product_id  INT NOT NULL,
    quantity    INT NOT NULL,
    unit_price  INT NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(id),
    FOREIGN KEY (product_id) REFERENCES products(id)
);
