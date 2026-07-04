# test-sample-app

テストケース・テストデータの作成を練習するための対象アプリ。注文金額計算を題材に、検索画面・詳細画面の2画面と、意図的に複雑な分岐・ループを多数持つService層メソッドを実装している。

## 技術スタック

| 技術 | 内容 |
|------|------|
| バックエンド | Java 17, Spring Boot 2.7.18, MyBatis (mybatis-spring-boot-starter 2.3.2) |
| フロントエンド | JSP + JSTL |
| データベース | H2（インメモリ） |
| ビルド | Gradle (Gradle Wrapper 8.7) |
| カバレッジ計測 | Jacoco |

詳細な仕様は [docs/design.md](docs/design.md) を参照。

## 起動方法

```powershell
cd test-sample-app
.\gradlew.bat bootRun
```

起動後、ブラウザで以下にアクセスする。

- 注文検索画面: http://localhost:8081/order/search
- ルート（`/`）にアクセスすると注文検索画面にリダイレクトされる

H2はインメモリDBのため、アプリ起動時に `schema.sql` → `data.sql` で自動初期化される（再起動するとデータはリセットされる）。

## ビルド・テスト

```powershell
.\gradlew.bat clean build
.\gradlew.bat test jacocoTestReport
```

Jacocoはビルド設定のみ用意している（テストコード自体は本アプリのスコープ外）。

## ディレクトリ構成

```
test-sample-app/
├── build.gradle
├── settings.gradle
├── docs/design.md              外部仕様書（金額計算ロジック仕様を含む）
└── src/main/
    ├── java/com/example/testsampleapp/
    │   ├── TestSampleAppApplication.java
    │   ├── controller/OrderSearchController.java
    │   ├── service/OrderCalculationService(Impl).java
    │   ├── dao/{Order,OrderItem,Customer,Product}Dao.java
    │   └── model/{Customer,Product,Order,OrderItem,OrderSearchCriteria,OrderCalculationResult,Coupon}.java
    ├── resources/
    │   ├── application.properties
    │   ├── mapper/{Order,OrderItem,Customer,Product}Mapper.xml
    │   ├── schema.sql
    │   └── data.sql
    └── webapp/WEB-INF/views/order/{search.jsp, detail.jsp}
```
