-- 顧客: 会員ランク・地域・誕生月・初回注文フラグの組み合わせを網羅
INSERT INTO customers (name, member_rank, birth_month, region, first_order_flag) VALUES ('田中太郎', 'BRONZE', 1, 'KANTO', FALSE);
INSERT INTO customers (name, member_rank, birth_month, region, first_order_flag) VALUES ('鈴木花子', 'SILVER', 6, 'KANSAI', FALSE);
INSERT INTO customers (name, member_rank, birth_month, region, first_order_flag) VALUES ('佐藤健一', 'GOLD', 12, 'HOKKAIDO', FALSE);
INSERT INTO customers (name, member_rank, birth_month, region, first_order_flag) VALUES ('山田美咲', 'PLATINUM', 8, 'OKINAWA', FALSE);
INSERT INTO customers (name, member_rank, birth_month, region, first_order_flag) VALUES ('伊藤直樹', 'BRONZE', 3, 'KANTO', TRUE);
INSERT INTO customers (name, member_rank, birth_month, region, first_order_flag) VALUES ('渡辺由美', 'GOLD', 12, 'KANSAI', FALSE);

-- 商品: カテゴリ・重量帯・内税/外税の組み合わせを網羅
INSERT INTO products (name, category, unit_price, weight_gram, tax_included_flag) VALUES ('国産りんご 1kg', 'FOOD', 300, 1000, TRUE);
INSERT INTO products (name, category, unit_price, weight_gram, tax_included_flag) VALUES ('緑茶セット', 'FOOD', 800, 500, TRUE);
INSERT INTO products (name, category, unit_price, weight_gram, tax_included_flag) VALUES ('ノートPC', 'ELECTRONICS', 120000, 2000, FALSE);
INSERT INTO products (name, category, unit_price, weight_gram, tax_included_flag) VALUES ('スマートフォン', 'ELECTRONICS', 90000, 200, FALSE);
INSERT INTO products (name, category, unit_price, weight_gram, tax_included_flag) VALUES ('Tシャツ', 'CLOTHING', 3000, 300, TRUE);
INSERT INTO products (name, category, unit_price, weight_gram, tax_included_flag) VALUES ('ジーンズ', 'CLOTHING', 8000, 600, TRUE);
INSERT INTO products (name, category, unit_price, weight_gram, tax_included_flag) VALUES ('小説', 'BOOK', 1500, 400, TRUE);
INSERT INTO products (name, category, unit_price, weight_gram, tax_included_flag) VALUES ('漫画全巻セット', 'BOOK', 12000, 3000, TRUE);
INSERT INTO products (name, category, unit_price, weight_gram, tax_included_flag) VALUES ('高級腕時計', 'LUXURY', 500000, 300, FALSE);
INSERT INTO products (name, category, unit_price, weight_gram, tax_included_flag) VALUES ('ブランドバッグ', 'LUXURY', 300000, 800, FALSE);

-- クーポン: 固定額/率/送料無料/期限切れを網羅
INSERT INTO coupons (code, discount_type, discount_value, valid_from, valid_to) VALUES ('WINTER500', 'FIXED', 500, '2025-12-01', '2025-12-31');
INSERT INTO coupons (code, discount_type, discount_value, valid_from, valid_to) VALUES ('SUMMER10', 'RATE', 0.10, '2025-07-01', '2025-08-31');
INSERT INTO coupons (code, discount_type, discount_value, valid_from, valid_to) VALUES ('FREESHIP', 'FREE_SHIPPING', 0, '2025-01-01', '2025-12-31');
INSERT INTO coupons (code, discount_type, discount_value, valid_from, valid_to) VALUES ('EXPIRED50', 'RATE', 0.50, '2024-01-01', '2024-01-31');

-- 注文1: 田中太郎(BRONZE/KANTO) 冬季キャンペーン中 + 固定額クーポン
INSERT INTO orders (customer_id, order_date, coupon_code, payment_method, status) VALUES (1, '2025-12-15', 'WINTER500', 'CREDIT_CARD', 'CONFIRMED');
INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (1, 1, 3, 300);
INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (1, 5, 1, 3000);

-- 注文2: 鈴木花子(SILVER/KANSAI) 夏季キャンペーン中 + 率クーポン、ELECTRONICS中心
INSERT INTO orders (customer_id, order_date, coupon_code, payment_method, status) VALUES (2, '2025-07-20', 'SUMMER10', 'BANK_TRANSFER', 'CONFIRMED');
INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (2, 3, 1, 120000);
INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (2, 4, 1, 90000);

-- 注文3: 佐藤健一(GOLD/HOKKAIDO) 誕生月(12月)と注文月が一致、クーポンなし、COD決済
INSERT INTO orders (customer_id, order_date, coupon_code, payment_method, status) VALUES (3, '2025-12-10', NULL, 'COD', 'CONFIRMED');
INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (3, 8, 2, 12000);
INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (3, 7, 5, 1500);

-- 注文4: 山田美咲(PLATINUM/OKINAWA) 送料無料クーポン、LUXURY、POINT決済
INSERT INTO orders (customer_id, order_date, coupon_code, payment_method, status) VALUES (4, '2025-03-05', 'FREESHIP', 'POINT', 'CONFIRMED');
INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (4, 9, 1, 500000);

-- 注文5: 伊藤直樹(BRONZE/KANTO, 初回注文) 初回特典確認用
INSERT INTO orders (customer_id, order_date, coupon_code, payment_method, status) VALUES (5, '2025-05-01', NULL, 'CREDIT_CARD', 'CONFIRMED');
INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (5, 5, 1, 3000);
INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (5, 6, 1, 8000);

-- 注文6: 渡辺由美(GOLD/KANSAI) 誕生月(12月)+冬季キャンペーン重複、期限切れクーポン、大量注文特典、COD金額帯
INSERT INTO orders (customer_id, order_date, coupon_code, payment_method, status) VALUES (6, '2025-12-25', 'EXPIRED50', 'COD', 'CONFIRMED');
INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (6, 10, 1, 300000);
INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (6, 1, 20, 300);

-- 注文7: 田中太郎(BRONZE/KANTO) キャンペーン期間外、数量帯10-19のボリュームディスカウント確認
INSERT INTO orders (customer_id, order_date, coupon_code, payment_method, status) VALUES (1, '2025-09-10', NULL, 'BANK_TRANSFER', 'CONFIRMED');
INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (7, 2, 10, 800);
INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (7, 3, 1, 120000);

-- 注文8: 佐藤健一(GOLD/HOKKAIDO) 数量帯20+のボリュームディスカウント確認
INSERT INTO orders (customer_id, order_date, coupon_code, payment_method, status) VALUES (3, '2025-01-15', NULL, 'COD', 'CONFIRMED');
INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (8, 1, 25, 300);
