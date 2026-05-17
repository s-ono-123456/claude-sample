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

---

## 9. クライアント側バリデーションのテスト方針

### 対象パターン

実システムでは HTML タグの `data-*` 属性にバリデーション条件を記載し、フレームワーク共通 JS がその属性を読み取ってバリデーションを実行するパターンが使われている。

```html
<!-- 例: data-* 属性でルールを定義し、共通 JS が処理する -->
<input type="text" name="username"
       data-required="true"
       data-maxlength="20"
       data-pattern="[a-zA-Z0-9]+">
```

### 共通 JS の扱い

フレームワーク側が提供する共通 JS のバリデーションロジック自体はテスト対象外とする。

### 確認対象の分離

クライアント側バリデーションで確認すべきことは性質が異なる 2 つに分かれる。

| 確認対象 | 問い | 手段 | 工程 |
|---|---|---|---|
| **JSP 属性の記述が正しいか** | 設計書の仕様通りに `data-maxlength="20"` 等が書かれているか | 静的解析（`extract_metadata.py`） | 単体テスト |
| **実際にバリデーションが動くか** | 上限値+1 を入力したときにエラーが出るか | Playwright E2E | 連結テスト以降 |

### 単体テスト工程での確認（静的解析）

`extract_metadata.py` が JSP をパースする際に `data-*` 属性も抽出し、`screens.yaml` の `client_validation` として記録する。設計書（バリデーション仕様）との差異は `validation_discrepancies` に記録する。

```yaml
# screens/register.yaml の記録イメージ
inputs:
  - name: username
    client_validation:
      required: true     # data-required="true" から抽出
      maxlength: 20      # data-maxlength="20" から抽出
    validation_discrepancies:
      - "設計書: maxlength=30, JSP: maxlength=20 → 不一致"
```

`validation_discrepancies` が空であることを確認することで、「JSP に正しいバリデーション属性が書かれているか」を単体テスト工程で担保する。

### 連結テスト以降での動作確認（Playwright）

実ブラウザでの動作確認（属性が書かれていても共通 JS が正しく処理するか）は Playwright に委ねる。`screens.yaml` にバリデーション情報が含まれていれば、境界値シナリオ（上限値／上限値+1 の入力）を自動生成できる。

```
単体テスト工程
  └── 静的解析: JSP属性 vs 設計書 → 属性記述の正しさを担保
        ↓（screens.yaml にバリデーション情報が正しく入った状態）
連結テスト工程
  └── Playwright: バリデーション境界値シナリオを自動生成・実行
        → 実ブラウザでの動作を担保
```

> **現行との対応**: 従来「手動で画面を起動して上限値を入力して確認」していた作業のうち、  
> 「属性が正しく書かれているか」は静的解析で、「実際の動作」は Playwright 実行で代替する。
