# sample-app

Spring MVC + MyBatis + H2（インメモリDB）で構築した EC サイトのサンプルアプリケーション。  
ユーザー管理・商品管理・注文管理の 3 機能を持つ。

## 技術スタック

| 区分 | 内容 |
|------|------|
| 言語 | Java 11 |
| フレームワーク | Spring MVC 5.3 |
| O/R マッパー | MyBatis 3.5 |
| DB | H2（インメモリ） |
| ビュー | JSP + JSTL |
| サーバー | Apache Tomcat 9 |

## 前提条件

- Windows 上に WSL2（Ubuntu-24.04）が導入済みであること
- Ubuntu-24.04 上に Docker がインストール済みであること

## 起動方法

`ast-analyzer/sample-app/` にある bat ファイルを実行する。

| ファイル | 操作 |
|----------|------|
| `up.bat` | イメージをビルドしてコンテナをバックグラウンド起動 |
| `down.bat` | コンテナを停止・削除 |
| `logs.bat` | ログをリアルタイム表示（終了: `Ctrl+C`） |

```bat
up.bat      # 起動
logs.bat    # ログ確認
down.bat    # 停止
```

起動後、ブラウザで以下にアクセスする。

```
http://localhost:8080/product/list
```

> H2 インメモリ DB のため、コンテナ再起動でデータはリセットされる。

## 画面一覧

| 画面 | URL |
|------|-----|
| 商品一覧 | `http://localhost:8080/product/list` |
| 商品詳細 | `http://localhost:8080/product/detail/{id}` |
| 商品編集 | `http://localhost:8080/product/edit/{id}` |
| 新規商品登録 | `http://localhost:8080/product/new` |
| ログイン | `http://localhost:8080/user/login` |
| 新規ユーザー登録 | `http://localhost:8080/user/register` |
| マイページ | `http://localhost:8080/user/mypage` |
| 注文履歴 | `http://localhost:8080/order/list` |
| 注文詳細 | `http://localhost:8080/order/detail/{id}` |

## 初期データ

### ユーザー

| username | email | role |
|----------|-------|------|
| admin | admin@example.com | ADMIN |
| user1 | user1@example.com | USER |

> パスワード認証は実装されていない。ユーザー名のみでログインできる。

### 商品

| 商品名 | 価格 | 在庫 | カテゴリ |
|--------|------|------|----------|
| ノートPC | 150,000 円 | 10 | 電子機器 |
| スマートフォン | 80,000 円 | 20 | 電子機器 |
| Tシャツ | 2,000 円 | 50 | 衣類 |
| ジーンズ | 5,000 円 | 30 | 衣類 |
| りんご | 500 円 | 100 | 食品 |
| 緑茶 | 800 円 | 200 | 食品 |

## ディレクトリ構成

```
sample-app/
├── src/main/
│   ├── java/com/example/sampleapp/
│   │   ├── controller/   # Spring MVC コントローラ
│   │   ├── service/      # ビジネスロジック
│   │   ├── dao/          # MyBatis DAO インターフェース
│   │   └── model/        # エンティティクラス
│   ├── resources/
│   │   ├── mapper/       # MyBatis XML マッパー
│   │   ├── schema.sql    # テーブル定義 DDL
│   │   └── data.sql      # 初期データ
│   └── webapp/
│       ├── WEB-INF/views/  # JSP ファイル
│       └── js/             # JavaScript ファイル
├── Dockerfile
├── docker-compose.yml
├── up.bat
├── down.bat
├── logs.bat
└── pom.xml
```
