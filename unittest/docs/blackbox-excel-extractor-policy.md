# Excel設計書抽出ツール 実装方針（openpyxl 版）

`ast-analyzer/` とは独立し、`branch-extractor/` と同一ツール群として Python + openpyxl で
画面設計書・チェック仕様からインベントリを抽出するツールを構築する方針をまとめる。

---

## 1. 配置とプロジェクト構成

```
C:\claude\
├── ast-analyzer/              ← 既存（Neo4j グラフ構築）
├── unittest/                  ← ユニットテスト支援ツール群
│   ├── branch-extractor/      ← 同一ツール群（AST 分岐抽出）
│   ├── excel-extractor/       ← 本ツール（Excel 設計書抽出）
│   │   ├── excel_extractor.py ← 抽出ロジック本体
│   │   ├── excel_extract.py   ← CLI エントリポイント
│   │   ├── config.yaml        ← シート名・列マッピング設定
│   │   └── README.md
│   └── docs/                  ← ツール群共通の設計書
└── pyproject.toml             ← 共有環境に openpyxl を追加
```

`branch-extractor/` のコードには依存しない。

---

## 2. セットアップ

### 依存追加

```toml
# pyproject.toml に追記
dependencies = [
    ...
    "openpyxl>=3.1",
    "pyyaml>=6.0",
]
```

```powershell
uv sync
```

---

## 3. 対象シートと列マッピング設計

### 3.1 設計思想

実際の Excel 設計書はプロジェクトごとにシート名・列構成が異なる。
そのため、シート名と列インデックスのマッピングは `config.yaml` で設定可能にする。
ツール本体はマッピングにのみ依存し、Excel フォーマットに直接依存しない。

### 3.2 config.yaml の形式

```yaml
# excel-extractor/config.yaml
item_sheet:
  sheet_name: "画面項目定義"        # 項目定義が記載されているシート名
  header_row: 3                    # ヘッダー行（1始まり）
  data_start_row: 4                # データ開始行（1始まり）
  columns:
    item_name: 1                   # 列A: 項目名
    data_type: 2                   # 列B: データ型
    required: 3                    # 列C: 必須/任意（○/×/必須/任意 など）
    min_value: 4                   # 列D: 最小値または最小長
    max_value: 5                   # 列E: 最大値または最大長
    allowed_values: 6              # 列F: 許容値・書式（カンマ区切り可）
    note: 7                        # 列G: 備考
  required_marker: ["○", "必須"]   # 必須を示す値のリスト

check_sheet:
  sheet_name: "チェック仕様"       # チェック仕様が記載されているシート名
  header_row: 2
  data_start_row: 3
  columns:
    check_id: 1                    # 列A: チェックID
    button_name: 2                 # 列B: ボタン名（イベント処理名）。複数の場合はセル内改行区切り
    check_target: 3                # 列C: チェック対象項目
    check_condition: 4             # 列D: チェック条件
    error_message: 5               # 列E: エラーメッセージ
    related_items: 6               # 列F: 関連項目（カンマ区切り可）
    note: 7                        # 列G: 備考
```

### 3.3 抽出対象フィールドの詳細

**項目定義シート（item_sheet）**

| フィールド | 説明 | 補正ルール |
|---|---|---|
| item_name | 項目名 | 空行はスキップ |
| data_type | データ型 | 「整数」「数値」「文字列」「日付」等をそのまま取得 |
| required | 必須/任意 | `required_marker` に一致すれば `必須`、それ以外は `任意` に正規化 |
| min_value | 最小値/最小長 | 数値セルは int/float で取得。文字列セルはそのまま |
| max_value | 最大値/最大長 | 同上 |
| allowed_values | 許容値・書式 | カンマ区切りの場合はリストに分解して格納 |
| note | 備考 | テキストそのまま |

**チェック仕様シート（check_sheet）**

| フィールド | 説明 | 補正ルール |
|---|---|---|
| check_id | チェックID | 空行はスキップ |
| button_name | ボタン名（イベント処理名） | セル内改行（`\n`）で分割してリスト化。空欄は全ボタン共通チェックとして扱う |
| check_target | チェック対象項目 | テキストそのまま |
| check_condition | チェック条件の記述 | テキストそのまま |
| error_message | エラーメッセージ | テキストそのまま |
| related_items | 関連項目 | カンマ区切りの場合はリストに分解 |
| note | 備考 | テキストそのまま |

---

## 4. 処理フロー

```
extract(excel_path, button_name, config) → tuple[list[ItemInfo], list[CheckInfo]]

  1. config.yaml を読み込み、シート設定を取得

  2. openpyxl.load_workbook(excel_path, data_only=True) でワークブックを開く
     data_only=True: 数式ではなく計算済みの値を取得する

  3. 項目定義シートの処理（extract_items）
     a. wb[item_sheet.sheet_name] でシートを取得
        シートが存在しない場合は ValueError を発生させてツールを終了
     b. header_row でヘッダーを確認（ログ出力のみ）
     c. data_start_row からデータ行をイテレーション
        - 全列が空の行はスキップ（終端判定）
        - item_name が空の行はスキップ
     d. セル結合の補正（後述）
     e. 各行から ItemInfo を生成し I-ID を採番

  4. チェック仕様シートの処理（extract_checks）
     a. wb[check_sheet.sheet_name] でシートを取得
     b. data_start_row からデータ行をイテレーション
        - check_id が空の行はスキップ
        - button_names が空リスト（全ボタン共通）の行は常に含める
        - button_names に button_name が含まれる行のみ含める
     c. 各行から CheckInfo を生成し C-ID を採番

  5. (list[ItemInfo], list[CheckInfo]) をタプルで返す
```

---

## 5. データクラス定義

```python
from dataclasses import dataclass, field

@dataclass
class ItemInfo:
    item_id: str          # I-XXXXXX
    item_name: str
    data_type: str
    required: str         # "必須" または "任意"
    min_value: str        # 数値・文字列長の最小値（str で統一。数値は str 変換）
    max_value: str        # 数値・文字列長の最大値
    allowed_values: list[str]
    note: str
    row_number: int       # Excelの行番号（デバッグ用）

@dataclass
class CheckInfo:
    check_id_internal: str  # C-XXXXXX（内部ID）
    check_id: str           # 設計書上のチェックID（例: CHK-001）
    button_names: list[str] # ボタン名（イベント処理名）のリスト（セル内改行で分割）。空リストは全ボタン共通
    check_target: str
    check_condition: str
    error_message: str
    related_items: list[str]
    note: str
    row_number: int
```

---

## 6. ID 採番規則

### I-ID（項目定義インベントリ）

`I-{6桁16進数}` 形式。以下のキー文字列の MD5 ダイジェスト先頭 6 文字を使用する。

```
キー = "{item_name}::{n}"
```

- `n` は同一ファイル内で同一 `item_name` が何番目か（0始まり）
- 通常は同一設計書内に同名項目は存在しないため `n=0` が大半

### C-ID（チェック仕様インベントリ）

`C-{6桁16進数}` 形式。以下のキー文字列の MD5 ダイジェスト先頭 6 文字を使用する。

```
キー = "{check_id}::{n}"
```

```python
import hashlib
from collections import defaultdict

def make_item_id(item_name: str, counter: dict) -> str:
    key_base = item_name
    n = counter[key_base]
    counter[key_base] += 1
    digest = hashlib.md5(f"{key_base}::{n}".encode()).hexdigest()
    return f"I-{digest[:6]}"

def make_check_id(check_id: str, counter: dict) -> str:
    key_base = check_id
    n = counter[key_base]
    counter[key_base] += 1
    digest = hashlib.md5(f"{key_base}::{n}".encode()).hexdigest()
    return f"C-{digest[:6]}"
```

### 安定性

- 設計書の前後に行を追加・削除しても、同一項目名（またはチェックID）が変わらない限り ID は不変
- 同名項目の前に行を追加した場合のみ `n` がずれる

---

## 7. セル結合の補正処理

Excel では項目グループ等をセル結合で表現することがある。結合セル内の非左上セルは `None` を返すため、補正が必要。

```python
from openpyxl.utils import get_column_letter

def get_merged_cell_value(ws, row: int, col: int):
    """セル結合範囲内の場合、左上セルの値を返す"""
    cell_value = ws.cell(row=row, column=col).value
    if cell_value is not None:
        return cell_value
    # 結合セルの確認
    for merged_range in ws.merged_cells.ranges:
        if (merged_range.min_row <= row <= merged_range.max_row and
                merged_range.min_col <= col <= merged_range.max_col):
            # 左上セルの値を返す
            return ws.cell(
                row=merged_range.min_row,
                column=merged_range.min_col
            ).value
    return None
```

---

## 8. CLI インターフェース

```
uv run python unittest/excel-extractor/excel_extract.py <excel_file> --button <button_name> [options]

引数:
  excel_file              解析対象の Excel ファイル（.xlsx）

必須オプション:
  --button / -b           チェックを絞り込むボタン名（イベント処理名）。1つのみ指定

オプション:
  --config / -c           config.yaml のパス（省略時: excel-extractor/config.yaml）
  --output / -o           出力先 .md ファイル（省略時: 標準出力）
```

使用例：

```powershell
# 登録ボタンのインベントリを標準出力に表示
uv run python unittest/excel-extractor/excel_extract.py design.xlsx --button 登録

# 登録ボタンのインベントリを Markdown ファイルに出力
uv run python unittest/excel-extractor/excel_extract.py design.xlsx --button 登録 `
  --output unittest/docs/inventory-register.md

# 更新ボタンのインベントリを別ファイルに出力
uv run python unittest/excel-extractor/excel_extract.py design.xlsx --button 更新 `
  --output unittest/docs/inventory-update.md

# 別の config を使用（設計書フォーマットが異なる場合）
uv run python unittest/excel-extractor/excel_extract.py design.xlsx --button 登録 `
  --config unittest/excel-extractor/config-format2.yaml
```

---

## 9. Markdown 出力フォーマット

```markdown
# インベントリ: <対象 Excel パス> / ボタン: <button_name>

**抽出日時**: YYYY-MM-DD HH:MM

## 項目定義一覧

**総項目数**: N

| I-ID     | 項目名 | データ型   | 必須 | 最小値/最小長 | 最大値/最大長 | 許容値・書式 | 備考 |
|----------|--------|------------|------|--------------|--------------|--------------|------|
| I-a1b2c3 | 在庫数 | 数値(整数) | 必須 | 0            | 9999         | -            | |
| I-d4e5f6 | 商品名 | 文字列     | 必須 | 1            | 50           | -            | |

> 「担当 TC-ID」列はテストケース設計時にこの Markdown に追記する

## チェック仕様一覧

**対象ボタン**: <button_name>（空欄＝全ボタン共通のチェックを含む）  
**総チェック数**: N

| C-ID     | チェックID | チェック対象 | チェック条件              | エラーメッセージ           | 関連項目 | 備考 |
|----------|-----------|------------|-------------------------|--------------------------|--------|------|
| C-j1k2l3 | CHK-001   | 在庫数      | 在庫数 < 発注点（10）    | 発注点を下回っています     | -      | |
| C-m4n5o6 | CHK-002   | 在庫数      | 在庫数 > 最大保管数（1000） | 最大保管数を超えています | -      | |

> 「担当 TC-ID」列はテストケース設計時にこの Markdown に追記する

## 警告

以下の行で取り込みに問題が発生した。確認してください。

| 行番号 | 問題内容 |
|--------|--------|
| 12 | item_name が空のためスキップ |
| 25 | min_value が数値として解釈できない（値: "入力必須"） |
```

---

## 10. 既知の制限事項

| 制限 | 内容 | 対処方針 |
|---|---|---|
| 複数行ヘッダー | ヘッダーが2行に分かれている場合、`header_row` は上段のみ参照し下段は無視 | config で `data_start_row` を正確に指定する |
| セル結合（縦・横） | 横方向の結合（例: 項目名が複数列にまたがる）は左端列のみ参照 | 設計書側で横結合を避けてもらう |
| 数式セル | `data_only=True` で計算値を取得するが、未計算の場合は `None` になる | Excel を一度開いて保存し直すことで計算値を確定させる |
| 文字コード | `.xlsx` のみ対応。`.xls`（旧形式）は非対応 | xlrd ライブラリを別途追加すれば対応可能（初版では対象外） |
| 画像・図形内テキスト | openpyxl は画像/図形内のテキストを読めない | 設計書のチェック条件をセルに記載するよう運用で対応 |
| 改行を含むセル | セル内改行（`\n`）はそのまま取得される。`button_name` 列は意図的に改行区切りを使用するため正常動作。他の列は整形が必要な場合がある | テストケース生成時に Claude Code 側で整形する |
