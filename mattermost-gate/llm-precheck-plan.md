# LLM事前審査 実装方針

## 概要

PermissionRequest フック（`permissionrequest.py`）に、Claude Haiku によるツール使用の事前審査ステップを追加する。
審査結果は Mattermost 通知に追記され、オペレーターの判断材料となる。

## フロー

```
stdin (hook_input)
  → llm_precheck()       # Haiku でポリシーに照らして審査
  → build_message()      # 審査結果を通知メッセージに含める
  → Mattermost 投稿
  → poll_for_decision()  # ユーザーが ✅/❌ でリアクション
  → stdout (decision)
```

## 追加・変更するファイル

### 1. `mattermost-gate/policy.md`（新規）

Haiku に渡す審査ポリシーを記述するファイル。自然言語で書く。

```markdown
# ツール使用審査ポリシー

## 自動的に危険（dangerous）と判断するもの
- git push --force / --force-with-lease
- 本番DB（prod/production を含む接続文字列）への DELETE / DROP
- rm -rf / Remove-Item -Recurse -Force でルートに近いパスを対象とするもの
- システムファイル（C:\Windows, /etc, /usr）への書き込み

## 注意が必要（risky）と判断するもの
- git reset --hard
- 外部URLへのPOST/PUT（WebFetch で method=POST など）
- 設定ファイル（.env, config.json, settings.json）の上書き
- パイプラインを含む長いシェルコマンド

## 問題なし（safe）と判断するもの
- ファイルの読み取り（Read, Glob, Grep）
- git status / git log / git diff などの参照系
- ローカルファイルへの書き込みで、上記の危険パターンに該当しないもの
```

### 2. `permissionrequest.py`（変更）

#### 追加する関数: `llm_precheck(hook_input, policy) -> dict`

- `claude -p <prompt> --model claude-haiku-4-5-20251001 --output-format json` をサブプロセスで呼び出す
- Haiku に渡すプロンプトは以下を含む:
  - policy の内容
  - tool_name, tool_input の内容
  - 出力形式の指示（JSON で `verdict` と `reason` を返す）
- 返り値の例:
  ```json
  {"verdict": "risky", "reason": "git reset --hard はローカルの未コミット変更を全て破棄します"}
  ```
- タイムアウト: 30秒
- エラー時は `{"verdict": "unknown", "reason": "審査失敗"}` を返す（フック自体は止めない）

#### 変更する関数: `build_message(hook_input, precheck_result)`

- 引数に `precheck_result` を追加
- メッセージに審査結果セクションを追加:

```
### 🤖 AI事前審査

| verdict | reason |
|---|---|
| ✅ safe / ⚠️ risky / 🚨 dangerous / ❓ unknown | （Haikuの判断理由） |
```

#### 変更する関数: `main()`

1. `policy.md` を読み込む（存在しない場合はスキップ）
2. `llm_precheck()` を呼び出す
3. `build_message()` に結果を渡す

## Haiku へのプロンプト設計

```
以下のポリシーに基づき、Claude Code のツール使用リクエストを審査してください。

## ポリシー
{policy}

## 審査対象
ツール名: {tool_name}
入力内容:
{tool_input_json}

## 出力形式
以下の JSON のみを返してください（説明文は不要）:
{"verdict": "safe|risky|dangerous", "reason": "判断理由を1〜2文で"}
```

## 注意点

- `--output-format json` は Claude Code CLI のバージョンによっては使えない可能性がある。
  その場合は stdout 全体を JSON としてパースし、失敗したら正規表現で JSON 部分を抽出する。
- Haiku の審査結果はあくまで **参考情報**。最終決定はユーザーのリアクションに委ねる。
- `policy.md` が存在しない場合は `llm_precheck()` をスキップし、通知にも審査セクションを表示しない。

## 実装ステップ

1. `policy.md` のサンプルを作成
2. `llm_precheck()` 関数を実装・単体テスト（モック stdin で動作確認）
3. `build_message()` を拡張
4. `main()` を修正
5. 実際に hook を通して Mattermost 通知を目視確認
