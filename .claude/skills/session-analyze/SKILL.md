---
name: session-analyze
description: |
  Quantitative log analysis of the current Claude Code session using the log-explorer
  CLI tool. Reads actual JSONL log files (including subagent logs) to surface token
  efficiency, failed/redundant tool calls, subagent performance, and actionable
  improvement suggestions.

  Invoke this skill whenever the user wants data-driven analysis of what happened in
  this session. Trigger phrases include: "セッション分析", "セッション解析",
  "このセッションを分析して", "session analyze", "ログを分析", "ツール呼び出しを分析",
  "サブエージェントの動作を確認", "トークン使用量を分析", "セッションのログを見て".
  Also trigger when the user asks about tool call patterns, subagent behavior,
  or token usage from a quantitative angle — even without using the exact phrases above.
  This skill complements session-retro (which reflects on conversation quality);
  use this one when the user wants hard numbers from the log files.
---

# Session Analyze

セッションの JSONL ログを `log-explorer` で読み込み、定量的な問題点・改善点をレポートする。

## Step 1: セッション ID の取得

```bash
echo $CLAUDE_CODE_SESSION_ID
```

取得できなかった場合（空文字）は「`CLAUDE_CODE_SESSION_ID` が設定されていません。Claude Code セッション内で実行してください。」と伝えて終了する。

以降の `<SESSION_ID>` をこの値で置き換えて実行する。

## Step 2: ログデータの収集

作業ディレクトリ `C:\claude` で以下を実行する。`--no-color` を付けてパース用のプレーンテキストで取得する。

```bash
cd /c/claude
uv run python log-explorer/main.py <SESSION_ID> summary --no-color
uv run python log-explorer/main.py <SESSION_ID> tokens --no-color
uv run python log-explorer/main.py <SESSION_ID> tools --no-color
uv run python log-explorer/main.py <SESSION_ID> agents --no-color
```

サブエージェントが存在した場合（agents 出力にエージェントが1件以上ある場合）、各エージェントを個別取得する：

```bash
uv run python log-explorer/main.py <SESSION_ID> agents --agent 0 --no-color
uv run python log-explorer/main.py <SESSION_ID> agents --agent 1 --no-color
# ... インデックス分繰り返す
```

## Step 3: 分析観点

収集したデータを以下の観点で分析する。数値を具体的に引用して根拠を示すこと。

### トークン効率

- **キャッシュヒット率**: `cache_read / (input + cache_read)` が 50% 未満なら効率が低い
- **サブエージェントのトークン合計**: メインより多い場合はその必要性を評価する
- **無駄なラウンドトリップ**: 同じような短い input+output が連続しているターンはないか

### ツール呼び出しパターン

`tools` の出力から以下を探す：
- **エラー結果**: Result 列に「404」「Error」「Exit code 1」「not found」が含まれているツール呼び出し
- **空結果**: Result が空またはごく短い（10文字以下）ツール呼び出し
- **同一ツールの連続呼び出し**: 同じツールが2回以上連続していて、後の呼び出しが前の修正になっている場合（試行錯誤）
- **大量のツール呼び出し**: 10回超のツール呼び出しがあるセッションは、事前調査や計画が不十分だった可能性がある

### サブエージェント活用

`agents` の各エージェントについて：
- **実行時間が長すぎる** (> 120秒): タスク過多または非効率な探索
- **ツール呼び出し失敗率**: そのエージェントのツール呼び出しのうちエラーになった割合
- **並列化の機会**: `agents` の開始時刻が近い（10秒以内）なら並列起動されている（良い）。大きく離れている場合は順次起動（改善余地）
- **説明文の具体性**: description が曖昧（"調査する" のみ）なエージェントは指示が不明確だった可能性

## Step 4: レポート出力

以下のテンプレートで Markdown レポートを作成する。根拠となる数値を必ず引用すること。問題がなかった項目は「問題なし」と記載してスキップせず、なぜ問題がないと判断したかを一言書く。

レポートをユーザーに表示するとともに、`C:\claude\retro\session-analyze-YYYY-MM-DD.md` に保存する（Write ツール使用）。ファイルが既存の場合は `-2`, `-3` を付加する。

---

```
# セッションログ分析レポート

**日時**: [今日の日付]
**セッション ID**: [先頭8文字]...
**分析対象**: [summary から取得したターン数・ツール呼び出し数・サブエージェント数]

---

## 1. トークン効率

| 指標 | 値 | 評価 |
|------|-----|------|
| 総入力トークン（メイン） | N | - |
| 総出力トークン（メイン） | N | - |
| キャッシュ読取トークン | N | - |
| キャッシュヒット率 | N% | ◎/○/△/× |
| サブエージェント合計 I/O | N | - |

**所見**: [数値に基づいた1〜3文の評価]

---

## 2. ツール呼び出しパターン

**失敗・エラーがあった呼び出し**
- [ツール名] [時刻]: [エラー内容の要約]  ← 具体的に
- 問題なし → その旨を記載

**冗長・試行錯誤と思われる呼び出し**
- [状況の説明] ← 具体的に
- 問題なし → その旨を記載

**所見**: [全体的なパターンの評価]

---

## 3. サブエージェント活用

サブエージェントがない場合は「このセッションにサブエージェントなし」と記載。

| エージェント | 実行時間 | ツール呼び出し数 | 評価 |
|------------|---------|--------------|------|
| [type] idx=N | Ns | N回 | ◎/○/△/× |

**並列化**: [並列起動されたか、改善余地があるか]

**各エージェントの所見**: [問題があったエージェントについて具体的に]

---

## 4. 改善提案

重要度 高/中/低 を付けて箇条書きで記載。
- [高] [具体的な改善アクション]
- [中] [具体的な改善アクション]

改善点がない場合は「特になし」と記載。

---

## 5. 総評

[2文以内。このセッションの全体的な評価と、次回への最重要アクションを述べる]
```

---

## 注意事項

- log-explorer の `--no-color` オプションを使うことでリッチテキスト制御文字を除去し、数値をパースしやすくする
- `tools` の出力が長い場合は `--limit 50` などで制限してから全体傾向を掴む
- ログファイルが存在しない（セッションが新しすぎる・別マシン）場合はその旨を伝えて終了する
- このスキルは `session-retro`（会話品質の振り返り）と相補的。両方実行するとより全体像が見える
