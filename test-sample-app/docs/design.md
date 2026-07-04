# test-sample-app 外部仕様書

## 概要

test-sample-app は Spring Boot + MyBatis + H2 + Gradle で構築された、**テストケース・テストデータの作成練習**のための対象アプリ。
画面は検索画面・詳細画面の2つのみで、Service層に意図的に複雑な金額計算ロジック（多数の分岐・ループを持つ1メソッド）を持たせている。

| 技術 | 内容 |
|------|------|
| バックエンド | Java 17, Spring Boot 2.7.18, MyBatis (mybatis-spring-boot-starter 2.3.2) |
| フロントエンド | JSP + JSTL |
| データベース | H2（インメモリ） |
| ビルド | Gradle (Gradle Wrapper 8.7) |
| カバレッジ計測 | Jacoco（設定のみ。テストコードは本アプリのスコープ外） |
| ローカル起動 | Spring Boot 内蔵Tomcat（`gradlew bootRun`、ポート8081） |

ソースコードを変更した場合は、本ファイル（特に「金額計算ロジック仕様」節）を必ず更新すること。

---

## 画面一覧

| 画面名 | URL | 説明 |
|--------|-----|------|
| 注文検索画面 | `/order/search` | 顧客名・注文日範囲・会員ランクで注文を検索し一覧表示 |
| 注文詳細画面 | `/order/detail/{id}` | 選択した注文の明細と金額計算結果を表示 |

### 1. 注文検索画面 (`/order/search`)

**表示内容**
- 検索フォーム（GET）: 顧客名（部分一致）、注文日From、注文日To、会員ランク（ドロップダウン）
- 検索結果テーブル: 注文ID（詳細へのリンク）、顧客名、会員ランク、注文日、支払方法
- 0件時は「該当する注文がありません」を表示

**処理フロー**

| 操作 | 処理 | 遷移先 |
|------|------|--------|
| 画面初回表示 | 条件なしで全件検索 | 同画面 |
| 検索ボタン押下 | 入力条件でGETサブミットし再検索 | 同画面（結果更新） |
| 注文IDリンク押下 | — | 注文詳細画面 |

### 2. 注文詳細画面 (`/order/detail/{id}`)

**表示内容**
- 注文基本情報: 注文ID、顧客名、会員ランク、注文日、支払方法、クーポンコード、配送地域
- 注文明細テーブル: 商品名、カテゴリ、単価、数量、明細小計
- 金額計算結果: 小計、割引合計、税額、配送料、決済手数料、特典合計、合計金額、獲得ポイント
- 検索画面への戻りリンク

---

## データモデル概要

```
customers
  id, name, member_rank(BRONZE/SILVER/GOLD/PLATINUM), birth_month(1-12),
  region(KANTO/KANSAI/HOKKAIDO/OKINAWA等), first_order_flag, registered_at

products
  id, name, category(FOOD/ELECTRONICS/CLOTHING/BOOK/LUXURY),
  unit_price, weight_gram, tax_included_flag

coupons
  code, discount_type(FIXED/RATE/FREE_SHIPPING), discount_value, valid_from, valid_to

orders
  id, customer_id, order_date, coupon_code(NULL可), payment_method(CREDIT_CARD/BANK_TRANSFER/COD/POINT), status

order_items
  id, order_id, product_id, quantity, unit_price（注文時単価のスナップショット）
```

**注:** H2 インメモリDBのためアプリ再起動でデータはリセットされる（`schema.sql` → `data.sql` の順で自動初期化）。

**注（文字エンコーディング）:** `application.properties` に `spring.sql.init.encoding=UTF-8` を明示している。これを指定しない場合、`data.sql`（UTF-8で記述）の読み込みにJVMのデフォルトエンコーディング（Windows環境ではShift_JIS系になりがち）が使われてしまい、日本語の氏名等が文字化けしたままDBに格納される不具合があった。

---

## 金額計算ロジック仕様（`OrderCalculationServiceImpl#calculateOrderAmount`）

意図的に1メソッドへ集約した手続き型の長大メソッド。以下のSTEP番号はソースコード中の `// STEP n:` コメントと対応する。

| STEP | 内容 | 分岐/ループ種別 |
|------|------|------|
| 1 | Order/Customer/OrderItem一覧/Productを取得。存在しない場合は `IllegalArgumentException` | 分岐(1) |
| 2 | 商品明細ループ開始 | ループ(1) |
| 3 | カテゴリ別税率判定: FOOD=8%, BOOK=8%, CLOTHING=10%, ELECTRONICS=10%, LUXURY=10%+贅沢税2%=12% | 分岐(2)〜(6) |
| 4 | 内税/外税判定: `tax_included_flag=true`なら税抜き金額=単価/(1+税率)、falseなら単価そのものが税抜き | 分岐(7) |
| 5 | 数量帯ボリュームディスカウント: 1-4個=0%, 5-9個=3%, 10-19個=5%, 20個以上=8% | 分岐(8)〜(10) |
| 6 | 明細小計（税抜き×数量−ボリューム割引）を加算してループ終了、小計確定 | — |
| 7 | 季節キャンペーン判定: 注文月が12月または7-8月なら追加2%割引、それ以外0% | 分岐(11) |
| 8 | 会員ランク別割引: BRONZE=0%, SILVER=2%, GOLD=4%, PLATINUM=6% | 分岐(12) |
| 9 | クーポン判定: コード未設定なら適用なし。設定時は有効期限チェック→種別判定(FIXED=固定額減算/RATE=率減算/FREE_SHIPPING=配送料無料フラグ) | 分岐(13)〜(16) |
| 10 | 地域別基本配送料: KANTO=500円, KANSAI=600円, HOKKAIDO=1000円, OKINAWA=1200円, その他=800円 | 分岐(17) |
| 11 | 重量帯別追加配送料（明細重量×数量の合計）: 0-1000g=+0円, 1000-5000g=+300円, 5000-10000g=+600円, 10000g以上=+1000円 | 分岐(18) |
| 12 | 配送料無料判定: 割引後小計が10,000円以上 または FREE_SHIPPINGクーポン → 配送料0円 | 分岐(19) |
| 13 | 支払方法別手数料: CREDIT_CARD=0円, BANK_TRANSFER=200円, POINT=0円, COD=基本300円（確定額が10,000円以上なら500円） | 分岐(20)〜(21) |
| 14 | 誕生月特典: 注文月＝顧客誕生月なら獲得ポイント+300 | 分岐(22) |
| 15 | 初回注文特典: `first_order_flag=true`なら小計の5%を追加割引 | 分岐(23) |
| 16 | 大量注文特典: 明細種類数が3以上 または 合計数量が15以上なら追加500円割引 | 分岐(24) |
| 17 | ポイント計算ループ: ランク別倍率（BRONZE=1%, SILVER=1.5%, GOLD=2%, PLATINUM=3%）を確定金額に乗算。季節キャンペーン中はポイント倍率を2倍 | 分岐(25)、ループ(2) |
| 18 | ラウンディング: 税額は四捨五入、割引額は切り捨て | 分岐(26) |
| 19 | 合計金額確定: 小計−割引合計＋税額＋配送料＋決済手数料。0円未満は0円にガード | 分岐(27) |
| 20 | `OrderCalculationResult` 構築（小計/割引合計/税額/配送料/決済手数料/特典合計/合計金額/獲得ポイント） | — |

分岐・ループ要素は計27で「20程度」の要件を満たす。

---

## 初期データ一覧（`data.sql`）と分岐カバレッジ対応

| 顧客 | ランク/地域/誕生月/初回 | 注文 | 注文日 | クーポン | 支払方法 | 主に確認できる分岐 |
|------|------|------|--------|----------|----------|------|
| 田中太郎 | BRONZE/KANTO/1月/false | #1 | 2025-12-15 | WINTER500(FIXED) | CREDIT_CARD | 冬季キャンペーン、固定額クーポン、FOOD+CLOTHING混在 |
| 鈴木花子 | SILVER/KANSAI/6月/false | #2 | 2025-07-20 | SUMMER10(RATE) | BANK_TRANSFER | 夏季キャンペーン、率クーポン、ELECTRONICS外税 |
| 佐藤健一 | GOLD/HOKKAIDO/12月/false | #3 | 2025-12-10 | なし | COD | 誕生月特典(12月一致)、北海道配送料、BOOK内税 |
| 山田美咲 | PLATINUM/OKINAWA/8月/false | #4 | 2025-03-05 | FREESHIP | POINT | 送料無料クーポン、沖縄配送料、LUXURY贅沢税 |
| 伊藤直樹 | BRONZE/KANTO/3月/**true** | #5 | 2025-05-01 | なし | CREDIT_CARD | 初回注文特典 |
| 渡辺由美 | GOLD/KANSAI/12月/false | #6 | 2025-12-25 | EXPIRED50(期限切れ) | COD | 期限切れクーポン無視、誕生月+冬季キャンペーン重複、大量注文特典、COD金額帯(高額) |
| 田中太郎 | （同上） | #7 | 2025-09-10 | なし | BANK_TRANSFER | キャンペーン期間外、数量帯10-19のボリュームディスカウント |
| 佐藤健一 | （同上） | #8 | 2025-01-15 | なし | COD | 数量帯20+のボリュームディスカウント |
