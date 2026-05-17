# テスト設計方針

## 1. 目的と背景

既存のソースコードと各種設計書よりテストケースをリバース生成し、品質の可視化と将来的な回帰テスト基盤の構築を目指す。
アプリはサンプルであるため、完全網羅よりも **「設計の学習・例示」** としての整合性を優先する。

---

## 2. テスト対象と除外範囲

### 対象

| 層 | 具体的なクラス/ファイル |
|---|---|
| Service | `UserServiceImpl`, `ProductServiceImpl`, `OrderServiceImpl` |
| Controller | `UserController`, `ProductController`, `OrderController` |
| DAO | `UserDao`, `ProductDao`, `OrderDao`（MyBatis Mapper） |
| JavaScript | `common.js`, `product.js`, `order.js` |

### 除外

| 除外対象 | 理由 |
|---|---|
| JSP のレンダリング | 画面確認は E2E テスト（Playwright 等）で実施 |
| Model クラス | getter/setter のみ（ロジックなし） |
| Spring 設定ファイル | コンテナ起動は統合テストで担保 |
| MyBatis XML マッパーの SQL 正確性 | DAO 統合テストで担保 |

---

## 3. テスト種別の定義

```
┌────────────────────────────────────────────────────┐
│  JavaScript 単体テスト (Jest)                        │
│  └─ AJAX 関数・バリデーション・カート操作               │
├────────────────────────────────────────────────────┤
│  Service 単体テスト (JUnit 5 + Mockito)              │
│  └─ DAO をモック化・ビジネスロジックに集中              │
├────────────────────────────────────────────────────┤
│  Controller グレーボックステスト (MockMvc)            │
│  └─ HTTP リクエスト/レスポンス・セッション・例外処理    │
├────────────────────────────────────────────────────┤
│  DAO 統合テスト (@MybatisTest + H2)                  │
│  └─ SQL の正確性・マッパーの動作確認                   │
└────────────────────────────────────────────────────┘
```

| 層 | ツール | ホワイトボックス観点 | ブラックボックス観点 |
|---|---|---|---|
| Service | JUnit 5 + Mockito 4 | AST 抽出の分岐を C1 基準で網羅 | 正常/異常の同値分割・境界値 |
| Controller | MockMvc + Mockito | 認証・null チェック等の条件分岐 T/F | HTTP メソッド・ステータスコード・パラメータ値 |
| DAO | @MybatisTest + H2 | WHERE 条件・SQL パスの網羅 | CRUD 操作の入出力・件数確認 |
| JavaScript | Jest 29 + jsdom | 関数内の if / try-catch 分岐 T/F | 入力値の境界・AJAX 成功/失敗 |

[ホワイトボックス](whitebox-case-derivation.md)・[ブラックボックス](blackbox-case-derivation.md)は**どの層にも両方適用する**。
ホワイトボックスは「どのパスを通すか」（テストケースの構造）を、ブラックボックスは「どの値を与えるか」（テストデータの選択）を決定する補完的な技法である。

---

## 4. ホワイトボックス設計基準（全層共通） → [テストケース導出方法](whitebox-case-derivation.md)

### 採用基準: 分岐網羅（C1）

AST 解析で抽出した全分岐点について、条件が **true / false の両方を通過するテスト** を最低 1 つずつ用意する。全層に適用し、層ごとの主な観点は以下の通り。

| 層 | ホワイトボックスで着目する分岐 |
|---|---|
| Service | if/else・ループ内 if・複合条件（&&/\|\|） |
| Controller | 認証チェック（session == null）・例外 catch |
| DAO | MyBatis の `<if>`・`<choose>` などの動的 SQL |
| JavaScript | if/else・コールバック内の条件・`\|\|` による短絡 |

```
C0（命令網羅）: 全文を少なくとも 1 回実行する
C1（分岐網羅）: 全分岐の T/F を各 1 回通過する  ← 採用
C2（条件網羅）: 複合条件の各要素の T/F を各 1 回通過する
MC/DC          : 各条件が独立して判定に影響する  ← 安全クリティカルでは必要、本サンプルでは参考扱い
```

---

## 5. ブラックボックス設計基準（全層共通） → [テストケース導出方法](blackbox-case-derivation.md)

全層に **同値分割**・**境界値分析**・**デシジョンテーブル** を適用する。
技法ごとの導出ルールと具体例は [blackbox-case-derivation.md](blackbox-case-derivation.md) を参照。

---

## 6. ツール選定

### Java

| ツール | バージョン（参考） | 用途 |
|---|---|---|
| JUnit 5 (Jupiter) | 5.10 | テストランナー・アノテーション |
| Mockito | 4.x | モックオブジェクト生成 |
| Spring Test | 5.3 | MockMvc, @SpringBootTest |
| H2 Database | 2.x | DAO 統合テスト用インメモリ DB |
| AssertJ | 3.x | 読みやすいアサーション |

pom.xml への追加（テストスコープ）：

```xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.10.0</version>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.mockito</groupId>
    <artifactId>mockito-core</artifactId>
    <version>4.11.0</version>
    <scope>test</scope>
</dependency>
```

### JavaScript

| ツール | バージョン（参考） | 用途 |
|---|---|---|
| Jest | 29 | テストランナー |
| jsdom | Jest 付属 | DOM API のシミュレーション |
| jest-fetch-mock / xhr-mock | - | XMLHttpRequest のモック |

---

## 7. テストの配置先（実装時の参考）

```
sample-app/
└── src/
    └── test/
        └── java/com/example/sampleapp/
            ├── service/
            │   ├── UserServiceImplTest.java
            │   ├── ProductServiceImplTest.java
            │   └── OrderServiceImplTest.java
            ├── controller/
            │   ├── UserControllerTest.java
            │   ├── ProductControllerTest.java
            │   └── OrderControllerTest.java
            └── dao/
                ├── UserDaoTest.java
                ├── ProductDaoTest.java
                └── OrderDaoTest.java

src/main/webapp/js/__tests__/
    ├── common.test.js
    ├── product.test.js
    └── order.test.js
```

---

## 8. カバレッジ目標（参考）

本サンプルでは厳密な数値目標よりも「全分岐点の T/F を網羅できているか」を確認する。

| 層 | 目標 | 備考 |
|---|---|---|
| Service | 分岐網羅 100% | AST 抽出の全 B-ID を網羅 |
| Controller | 主要分岐 100% | MockMvc でリクエスト/レスポンスを検証 |
| DAO | CRUD 全操作 | SQL の正確性をインメモリ DB で確認 |
| JS | 主要関数の分岐 100% | ajaxGet/ajaxPost・カート操作・バリデーション |
