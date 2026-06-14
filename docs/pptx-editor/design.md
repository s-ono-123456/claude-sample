# pptx-editor 設計書

## 概要

PowerPointファイルをコマンドラインで操作するCLIツール。
テンプレートpptxのデザインを継承しながら、テキスト・図形・SVGアイコン・矢印を配置できる。
Claude Code のスキル（`pptx-editor`）からCLIを呼び出すことで、スライドを視覚確認しながら修正できる。

## ディレクトリ構成

```
pptx-editor/
├── main.py                 # CLIエントリポイント（argparse サブコマンド）
├── commands/
│   ├── __init__.py
│   ├── inspect.py          # スライド構造表示
│   ├── capture.py          # スライドをPNG画像として出力
│   ├── add_text.py         # テキストボックス追加
│   ├── edit_text.py        # 既存シェイプのテキスト修正
│   ├── add_image.py        # PNG/SVG画像配置
│   ├── add_shape.py        # 図形配置
│   ├── add_connector.py    # 線・矢印配置
│   ├── add_table.py        # テーブル新規作成
│   ├── edit_table.py       # テーブルのセル内容・スタイル編集
│   ├── table_add_row.py    # テーブルへの行追加
│   ├── table_add_col.py    # テーブルへの列追加
│   ├── table_merge.py      # セル結合
│   └── table_split.py      # セル結合解除
└── lib/
    ├── __init__.py
    ├── pptx_utils.py       # 共通ユーティリティ（cm/EMU変換・ファイルI/O）
    └── svg_embed.py        # Microsoft 365向けSVG XML埋め込み
```

## 実行方法

```powershell
uv run python pptx-editor/main.py <command> [options]
```

作業ディレクトリは `C:\claude`。座標・サイズの単位はすべて **cm**。

## コマンド仕様

### inspect

スライドのシェイプ構造を表示する。

```
inspect <file> [--slide N]
```

| オプション | 説明 |
|-----------|------|
| `file` | pptxファイルパス |
| `--slide N` | 表示するスライド番号（省略時は全スライド） |

出力例：
```
=== スライド 2 / レイアウト: 章＋1行タイトル ===
  [0] PLACEHOLDER  name='タイトル 1'  pos=(0.6,0.7)cm  size=26.4x1.9cm
       text: 'データセット'
  [3] TEXT_BOX     name='コンテンツ プレースホルダー 2'  pos=(0.6,3.1)cm  ...
```

### capture

指定スライドをPNG画像として出力する。

```
capture <file> --slide N --output <path> [--dpi N]
```

| オプション | 説明 |
|-----------|------|
| `--slide N` | スライド番号（1始まり） |
| `--output <path>` | 出力PNGファイルパス |
| `--dpi N` | 解像度（デフォルト: 150） |

**内部処理**: soffice でpptx→PDFに変換し、PyMuPDFで指定ページをPNGにレンダリング。
soffice の `--convert-to png` がページ指定に非対応のためPDF経由を採用。

### add-text

テキストボックスを新規追加する。

```
add-text <file> --slide N --text "..." --left X --top Y --width W --height H
         [--font-size N] [--font-name "..."] [--bold] [--color "#RRGGBB"]
         [--align left|center|right] [--output <path>]
```

### edit-text

既存シェイプのテキストを書き換える。

```
edit-text <file> --slide N --shape "名前or番号" --text "..." [--output <path>]
```

`--shape` はシェイプ名の部分一致または0始まりインデックスで指定。
既存の書式（フォント・色）を保持したまま文字列のみ差し替える。

### add-image

PNG または SVG 画像をスライドに配置する。

```
add-image <file> --slide N --image <path> --left X --top Y --width W --height H [--output <path>]
```

SVGの場合、`svg_embed.py` によりMicrosoft 365対応のXML直接埋め込みを行う（後述）。

### add-shape

図形をスライドに配置する。

```
add-shape <file> --slide N --type <shape_type> --left X --top Y --width W --height H
          [--fill "#RRGGBB"] [--line-color "#RRGGBB"] [--line-width N]
          [--no-fill] [--no-line] [--text "..."] [--output <path>]
```

| 図形タイプ | 説明 |
|-----------|------|
| `rect` | 矩形 |
| `rounded-rect` | 角丸矩形 |
| `ellipse` | 楕円 |
| `diamond` | ひし形 |
| `triangle` | 三角形 |
| `parallelogram` | 平行四辺形 |
| `hexagon` | 六角形 |
| `cloud` | 雲形 |
| `cylinder` | 円柱 |
| `note` | メモ |

### add-connector

線・矢印をスライドに配置する。

```
add-connector <file> --slide N --start-x X --start-y Y --end-x X --end-y Y
              [--arrow none|start|end|both] [--connector-type straight|elbow|curved]
              [--color "#RRGGBB"] [--line-width N] [--output <path>]
```

### add-table

テーブルを新規作成して配置する。

```
add-table <file> --slide N --rows R --cols C
          --left X --top Y --width W --height H
          [--data "A,B,C;1,2,3"]
          [--col-widths "3,5,4"]
          [--row-heights "1,1.5"]
          [--header]
          [--header-fill "#RRGGBB"]
          [--output <path>]
```

| オプション | 説明 |
|-----------|------|
| `--data` | セルデータ。行を `;` 、セルを `,` で区切る |
| `--col-widths` | 各列の幅（cm）をカンマ区切りで指定。省略時は均等 |
| `--row-heights` | 各行の高さ（cm）をカンマ区切りで指定。省略時は均等 |
| `--header` | 先頭行をヘッダー行として強調 |
| `--header-fill` | ヘッダー行の背景色 |

### edit-table

テーブルのセル内容・スタイルを編集する。

```
edit-table <file> --slide N --shape "名前or番号"
           --row R --col C
           [--text "..."] [--fill "#RRGGBB"]
           [--font-size N] [--bold] [--color "#RRGGBB"]
           [--output <path>]
```

`--row`, `--col` は 0始まりのインデックス。

### table-add-row

既存テーブルに行を追加する。

```
table-add-row <file> --slide N --shape "名前or番号"
              [--at R]
              [--height H]
              [--output <path>]
```

`--at` 省略時は末尾に追加。行高省略時は既存行の平均値を使用。

### table-add-col

既存テーブルに列を追加する。

```
table-add-col <file> --slide N --shape "名前or番号"
              [--at C]
              [--width W]
              [--output <path>]
```

`--at` 省略時は末尾に追加。列幅省略時は既存列の平均値を使用。

### table-merge

テーブルのセルを結合する。

```
table-merge <file> --slide N --shape "名前or番号"
            --from-row R --from-col C
            --to-row R --to-col C
            [--output <path>]
```

`cell(from_row, from_col).merge(cell(to_row, to_col))` を使用。

### table-split

テーブルのセル結合を解除する。

```
table-split <file> --slide N --shape "名前or番号"
            --row R --col C
            [--output <path>]
```

結合元セル（`is_merge_origin == True`）のみ指定可能。`cell.split()` を使用。

**内部XML操作（行・列追加）**: python-pptx に公式APIがないため、`table._tbl.add_tr()` / `table._tbl.tblGrid.add_gridCol()` を直接操作する。

## SVG埋め込み方式（lib/svg_embed.py）

Microsoft 365 でベクター品質のSVGを表示するため、XML直接埋め込みを採用。

1. LibreOffice で SVG → PNG に変換（フォールバック用）
2. フォールバックPNGを `add_picture` で通常の画像として配置
3. `<a:blip>` の `<a:extLst>` に `svgBlip` 拡張要素を追加してSVGをBase64埋め込み

```xml
<a:extLst>
  <a:ext uri="{96DAC541-7B7A-43D3-8B79-37D633B846F1}">
    <asvg:svgBlip r:embed="rId5" />
  </a:ext>
</a:extLst>
```

Microsoft 365ではSVGがベクター表示、旧環境ではPNGにフォールバックする。

## 依存パッケージ

| パッケージ | 用途 |
|-----------|------|
| `python-pptx` | pptxファイルの読み書き |
| `pymupdf` | PDF→PNG変換（captureコマンド） |
| `lxml` | SVG XML埋め込み（python-pptxの依存として自動インストール） |

外部ソフトウェア：
- **LibreOffice** (`C:\Program Files\LibreOffice\program\soffice.exe`): pptx→PDF変換・SVG→PNG変換

## スキルとの連携

Claude Code スキル `pptx-editor`（`~/.claude/skills/pptx-editor/skill.md`）が本CLIをラップする。

スキルのフロー：
1. `capture` でスライドをPNG化 → Readツールで視覚確認
2. `inspect` でシェイプ座標を確認
3. 修正コマンドを実行
4. 再 `capture` で結果確認
5. 問題なければ完了報告
