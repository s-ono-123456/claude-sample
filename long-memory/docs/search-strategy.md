# 長期記憶 データライフサイクル戦略

## 1. ライフサイクル全体像

```
【登録】SessionEnd / PreCompact フック
  会話トランスクリプト
    → LLM で事実・決定・観察を抽出
    → Embedding 生成・エンティティ抽出
    → Neo4j に Memory / Entity / エッジを書き込み
          ↓（時間とともに減衰）
【蓄積】Neo4j グラフ
  Memory ノード（knowledge / decision / tentative）
  Entity ノード（CO_OCCURS_WITH で相互リンク）
          ↓（検索クエリで浮上）
【取得・注入】SessionStart / PostCompact フック（補助・受動的）
【能動検索】エージェント自身がスキルを呼ぶ（メイン・能動的）
  クエリ Embedding 生成
    → ハイブリッド検索（ベクトル + 全文 + グラフ拡張）
    → スコアリング（類似度 + グラフ近接度 + 時間減衰 + 重要度）
    → 上位 N 件を注入 / 表示
          ↓
【整理スキル】定期実行または手動
  類似・競合する Memory を検出 → LLM で判断 → 統合 or inactive
```

---

## 2. データ登録（保存フロー）

### 2.1 登録トリガー

| フックイベント | タイミング | 理由 |
|---|---|---|
| `SessionEnd` | 会話終了時 | セッション全体の会話を保存 |
| `PreCompact` | コンテキスト圧縮直前 | 圧縮で消えてしまう文脈を先に Memory として保存 |

どちらも `hooks/memory_save.py` が実行される。

### 2.2 抽出されるデータ（type 別）

`lib/extractor.py` が LLM を使って会話トランスクリプトから以下の3分類を抽出する。

| type | 意味 | 半減期 | 分類基準 |
|---|---|---|---|
| `knowledge` | 事実・観察・発見 | 90 日 | 客観的事実・作業中の発見・観察結果。「X は Y である」「この API はドキュメントと挙動が違う」 |
| `decision` | 最終確定した意思決定 | なし（status で管理） | 採用・却下が確定したもの。上位の問いに従属していない |
| `tentative` | 未確定の検討事項・仮説 | 30 日 | A か B か未決の中間判断・検討中の仮説。上位の問いが未解決なら tentative |

**`tentative` の扱い:** 議論が決着して `decision` に昇格させる、という処理は行わない。決定が確定したら **新しく `decision` として保存** する。残った `tentative` は半減期30日で自然に埋もれる。昇格のための突き合わせ処理は不要。

**`decision` と `tentative` の判断基準：** 「この議論はまだ上位の問いに従属しているか？」  
A・B どちらを選ぶか未解決なら `tentative`。最終的に選んだ時点で新しい `decision` を作成する。

### 2.3 登録処理ステップ

```
1. transcript_path からトランスクリプトを読み込む
2. extractor.py → LLM 抽出 → [{type, content}] リスト
3. ollama_client.py → 各 content の Embedding（1024 次元）を生成
4. entity_extractor.py → content からエンティティ（固有名詞・技術名・概念）を抽出・正規化
5. fugashi（MeCab）→ content を形態素解析し content_tokens（スペース区切り）を生成
6. neo4j_client.py → Neo4j に書き込み
   - Session ノードを MERGE（session_id で統合）
   - Project ノードを MERGE（cwd で統合）、Session に IN_PROJECT エッジを作成
   - Memory ノードを INSERT（重複は定期整理スキルで別途管理）、Session に BELONGS_TO エッジを作成
   - Entity ノードを MERGE（name 正規化済みで統合）
   - MENTIONS エッジを作成
   - 同一 Memory 内の Entity 間に CO_OCCURS_WITH エッジを作成（count 加算）
```

### 2.4 重複・類似の管理（定期整理スキル）

保存時の厳密一致による重複排除は行わない。LLM が生成する content は表現が変わるため、hash 一致はほぼ発生しない。

代わりに **定期整理スキル**（§6.4）が以下の3段階で管理する：

1. **候補抽出**: Embedding cosine ≥ 0.7 の Memory ペアを候補とする
2. **絞り込み**: 共通 Entity が多いペアを優先（Embedding だけでは「競合」と「補完」が区別できないため）
3. **LLM 判断**: 候補ペアを渡して「類似 / 競合 / 無関係」を判定
   - 類似（同内容）→ 内容を統合して1つの Memory に統合
   - 競合（矛盾する結論）→ 最新を `active` に残し、古いものを `inactive` に更新
   - 無関係 → スキップ

> **検証メモ**: qwen3-embedding:0.6b で計測した結果、方針転換した文章（0.76）と同テーマ・同結論（0.77）の cosine 類似度がほぼ同じだった。Embedding のみでの「競合」判定は精度が不十分なため、Entity の重なりと LLM 判断の組み合わせが必要。

### 2.5 UC4 問題2・3の設計判断

| 問題 | 判断 | 理由 |
|---|---|---|
| コード変更で文脈が古くなっても気づけない | 対処不要 | 時間減衰は指数減衰（完全には消えない）。リファクタリング後も関連クエリを投げれば類似度でヒットし続ける。誤った文脈が注入された場合は能動検索スキルでユーザーが確認・棄却できる |
| 発見タイミングと保存タイミングのずれ | 対処不要 | トランスクリプトに Read・Edit 等のツール使用記録が含まれるため、extractor.py が「どのファイルを触っていたか」を含む文脈を再構成できる |

---

## 3. データ取得と注入（検索フロー）

### 3.1 取得トリガー

| フックイベント | タイミング | 役割 |
|---|---|---|
| `SessionStart` | セッション開始時 | 初回メッセージを使って関連記憶を注入（受動・補助） |
| `PostCompact` | コンテキスト圧縮直後 | 圧縮後コンテキストで記憶を補完（受動・補助） |

どちらも `hooks/memory_inject.py` が実行される。フックは補助的な下地であり、精度の高い記憶参照はエージェント自身による能動検索（§4）が担う。

### 3.2 クエリ生成の3層設計

記憶検索のクエリ生成は用途に応じて3層に分かれる。

| 層 | 担い手 | クエリの生成方法 | 精度 |
|---|---|---|---|
| SessionStart フック | memory_inject.py | **初回メッセージをそのままクエリとして使用** | 低（文脈理解なし） |
| PostCompact フック | memory_inject.py | 圧縮後の直近メッセージを結合 | 低〜中 |
| エージェント自身の検索 | Claude Code | タスク内容を理解した上でクエリを自分で考えて memory_search.py を呼ぶ | 高 |

フックは「セッション開始時の下準備」として位置付ける。実際の作業に関連する記憶参照は、エージェントがタスクの文脈を理解した上で能動的に行う（§4）。

### 3.3 ハイブリッド検索処理の概要

詳細な Cypher クエリは §7 を参照。

```
Step 1a: ベクトル検索（意味的類似）
  クエリ Embedding → memory_embedding_index → 上位 20 件（ベクトルスコア付き）

Step 1b: 全文検索（文字列一致）
  クエリ → fugashi 形態素解析 → memory_token_index → 上位 top_k_fulltext 件（全文スコア付き、デフォルト 10）
  ※ 固有名詞・ファイルパス・コマンド名など、ベクトル検索が苦手な語に補完的に使用

Step 1 マージ: 両結果を統合・重複排除（最大 30 件程度）

Step 2: グラフ拡張
  取得 Memory の MENTIONS エッジ → Entity を収集
  Entity の CO_OCCURS_WITH エッジ → 関連 Entity を収集（深さ 2 まで）
  関連 Entity の MENTIONS 逆引き → 追加 Memory を収集（上限 30 件）

Step 3: スコアリング統合
  最終スコア = α × ベクトル類似度
             + β × グラフ近接度（最短パス長の逆数）
             + γ × 時間スコア（type 別指数減衰）
             + δ × 重要度スコア（Memory.score）
  α=0.5, β=0.2, γ=0.2, δ=0.1（初期値、config.json でチューニング可）
```

検索時フィルタ: `WHERE m.status = 'active'` で `inactive` を除外する。

### 3.4 注入フォーマット

`hooks/memory_inject.py` が stdout に出力し、Claude Code がシステムプロンプトに自動注入する。

```
## 関連する過去の記憶

- [2026-05-10] Neo4j のベクトルインデックスは cosine 類似度を使用した
- [2026-05-12] qwen3-embedding:0.6b の Embedding 次元数は 1024
```

---

## 4. 能動検索スキル設計

### 4.1 フックとスキルの役割分担

| 方式 | 担い手 | クエリ品質 | 出力先 | 主な用途 |
|---|---|---|---|---|
| 自動注入（フック） | memory_inject.py | 低（機械的） | システムプロンプト（非表示） | セッション開始時の下地 |
| 能動検索（スキル） | エージェント自身 | 高（文脈理解あり） | 会話（表示） | 作業前の記憶確認・明示的な問い |

**記憶参照のメインは能動検索。** CLAUDE.md のルールに従い、エージェントはタスクを実行する前に必ずスキルを呼んで関連記憶を確認する。クエリはエージェントが「このタスクに関連する記憶を引き出すには何を聞くべきか」を自分で考えて生成する。

### 4.2 スキルの処理フロー

```
1. タスクの内容を理解し、関連しそうなキーワード・ファイルパス・技術名を抽出
2. hooks/memory_search.py を呼び出す
   入力: {"query": "<エージェントが考えたクエリ>", "cwd": "<プロジェクトルート>"}
3. ハイブリッド検索（§7 と同じ処理）を実行
4. 結果を会話に表示してユーザーと内容を確認
5. 記憶の内容が古い・不正確と思われる場合はその旨を伝える
6. 記憶を踏まえてタスクを実行する
```

### 4.3 CLAUDE.md への追記内容

`long-memory` スキルが実装されたら、`CLAUDE.md` の Working Rules セクションに以下を追記する：

```markdown
5. **タスク実行前に記憶を参照する** — 作業を開始する前に必ず `long-memory` スキルを呼び出して関連する過去の記憶を確認すること（`C:/claude/long-memory/` が存在する場合）
```

### 4.4 スキル定義（SKILL.md 形式）

`~/.claude/skills/long-memory.md` または `.claude/skills/long-memory.md`:

```markdown
---
name: long-memory
description: |
  長期記憶から関連する過去の記憶を検索して会話に表示する。
  以下の場面でこのスキルを使用する：
  ・「〜について覚えていることは？」「なぜ〜を選んだか」「このファイルで注意点は？」など
    ユーザーが明示的に記憶を問うたとき
  ・特定のファイル・関数・技術・設計について議論するとき
  ※ タスク実行前の記憶参照は CLAUDE.md のルールによりエージェントが自律的に行う
---

ユーザーが指定した内容、または現在議論している内容に関連する記憶を検索します。

手順：
1. 対象のキーワード・ファイルパス・技術名・概念を抽出する
   - ユーザーが明示した場合はそれをそのまま使う
   - 会話の文脈から読み取る場合は「このタスクで重要な概念は何か」を考える
2. 以下のコマンドを実行する：
   echo '{"query": "<クエリ>", "cwd": "<cwd>"}' | uv run python C:/claude/long-memory/hooks/memory_search.py
3. 検索結果を会話に表示する
4. 関連する記憶がある場合は内容をユーザーに説明し、タスクに活かす
5. 記憶が古い・不正確と思われる場合はその旨を伝える
```

---

## 5. データ更新タイミング

### 5.1 decision の競合解消・inactive 化（記憶整理スキルと共通）

§2.4 の定期整理スキルと同じフローで処理する（重複管理と競合管理を一つのスキルで担う）。

**トリガー:** 手動スキル呼び出しのみ。decision が蓄積してからまとめて整理する方が効率的。

**処理フロー:**
1. 全 `status='active'` の decision ノードを取得
2. Embedding cosine ≥ 0.7 かつ共通 Entity が多いペアを候補とする
3. LLM に候補ペアを渡して「類似 / 競合 / 無関係」を判定
4. 競合 → 最新を `active` に残し、古いものを `inactive` に更新
5. 変更内容をユーザーに報告（誤判定の確認用）

### 5.2 Entity プロパティの更新

Memory 保存のたびに以下を更新する：

| 更新対象 | タイミング | 内容 |
|---|---|---|
| `Entity.mention_count` | Memory 保存時 | `+1`（言及するたびに累積加算） |
| `Entity.last_seen` | Memory 保存時 | 現在の datetime に更新 |
| `CO_OCCURS_WITH.count` | Memory 保存時 | 同一 Memory 内の共起ペアに `+1` |
| `CO_OCCURS_WITH.strength` | Memory 保存時 | `count / max_count` で正規化して更新 |

### 5.3 Memory の無効化

ユーザーが「この記憶は不要・誤り」と明示した場合、`Memory.status = 'inactive'` に更新する。

`score = 0.0` での無効化は行わない（スコア計算式では `δ × 0.0 = 0` になるだけで他のスコアで浮上し続けてしまうため）。

検索フィルタ: `WHERE m.status = 'active'` で `inactive` を除外する。

---

## 6. 記憶の減衰

### 6.1 type 別の減衰方式

| type | 減衰方式 | 半減期 | 管理方法 |
|---|---|---|---|
| `decision` | なし | — | `status: "active" / "inactive"` で競合・無効化管理 |
| `knowledge` | 指数減衰 | 90 日 | `exp(-0.693 × 経過日数 / 90)` |
| `tentative` | 指数減衰 | 30 日 | `exp(-0.693 × 経過日数 / 30)` |

`decision` を時間減衰させない理由：意思決定は後のセッションでも有効なはずだが、時間減衰が適用されると永続すべき決定が薄れてしまうため。

### 6.2 減衰の適用タイミングと性能影響

**重要：DB に保存されている値は変更しない。** 検索時のスコア計算で動的に適用する。

```cypher
-- スコア計算時（Cypher 内で動的に実行）
ageDays = duration.inDays(m.created_at, datetime()).days
timeScore =
  CASE m.type
    WHEN 'decision'  THEN 1.0
    WHEN 'knowledge' THEN exp(-0.693 * ageDays / 90.0)
    ELSE                  exp(-0.693 * ageDays / 30.0)
  END
```

**性能影響:** `exp()` は Cypher 内の軽量浮動小数点演算。ボトルネックは I/O（ノード読み込み）であり計算コスト自体は無視できる。現設計の LIMIT 30 程度なら問題なし。ノード数が万単位になる場合は §6.3 に記載の将来的な物理削除ポリシーを適用する。

これにより古い記憶が完全に消えることなく、クエリとの関連性が高ければ浮上し続ける。

### 6.3 物理削除のポリシー

フックによる**自動の物理削除はなし**。定期整理スキル（§6.4）を手動実行したときのみ「類似」判定の Memory を物理削除する（「競合」判定は `inactive` 化のみ）。`scripts/analyze_memory.py` で統計を確認しながら整理する。

将来的な検討事項：
- `tentative` で `created_at` が 90 日以上経過したものの一括削除
- `inactive` 化された `decision` の一括削除

### 6.4 記憶の整理スキル

§2.4 の重複・類似管理と §5.1 の競合解消を一つのスキルとして設計する。

**整理スキルが扱うケース:**

| ケース | 判定 | 処理 |
|---|---|---|
| 同内容の knowledge が複数 | 類似（LLM判定） | 最も情報が豊富なものに統合して他を削除 |
| 矛盾する decision が複数 | 競合（LLM判定） | 最新を `active` に残し古いものを `inactive` に |
| 無関係に見えて共通テーマがある | 無関係（LLM判定） | スキップ |

**候補抽出フロー（Step1: --project + --plan-output）:**
```
1. Embedding cosine ≥ 0.7 の Memory ペアを全て列挙
2. 各ペアの共通 Entity 数を計算（CO_OCCURS_WITH で接続されている Entity を含む）
3. 共通 Entity が多いペアを優先して LLM 判定キューに投入
4. LLM が「類似 / 競合 / 無関係」を判定 → 判定結果を --plan-output で指定した JSON に保存
5. JSON 内容を stdout に表示して終了（この時点では Neo4j への書き込みなし）
```

**適用（Step2: --apply）:**
```
・ユーザーが JSON を確認後 --apply <file> で実行
・JSON の判定結果をそのまま適用（LLM 再呼び出しなし）
・変更件数を stdout にレポート出力 ＋ JSON ファイルを削除
```

**発火タイミング:** 手動スキル呼び出し（フックによる自動実行なし）。decision の蓄積量が増えてからまとめて整理する方が効率的なため、毎 PreCompact で自動実行はしない。

#### スクリプト仕様

| 項目 | 内容 |
|---|---|
| パス | `scripts/memory_cleanup.py` |
| 実行方式 | 手動スキル呼び出しのみ |
| LLM | Claude Haiku（Step1 のみ呼び出し。Step2 は JSON 適用のみで LLM 不使用） |
| Step1 引数 | `--project <path>`（必須）、`--plan-output <file>`（必須）、`--cosine-threshold`（デフォルト 0.7） |
| Step2 引数 | `--apply <file>`（保存済み計画 JSON） |
| 出力 | Step1: 判定結果を stdout 表示 ＋ JSON 保存。Step2: 変更件数を stdout にレポート ＋ JSON ファイルを削除 |

**2ステップ方式を採用した理由:** `--dry-run` で確認した LLM の判定結果と本実行時の結果が一致しない可能性がある（LLM の非決定性）。LLM 呼び出しを Step1 の 1 回に限定し、Step2 では JSON をそのまま適用することで確認時と完全に同一の操作を保証する。

---

## 7. ハイブリッド検索の技術詳細

### 7.1 検索フロー

```
Step 1a: ベクトル検索（意味的類似）
  クエリ Embedding → memory_embedding_index → 上位 20 件の Memory（ベクトルスコア付き）

Step 1b: 全文検索（文字列一致）
  クエリを fugashi で形態素解析 → memory_token_index → 上位 top_k_fulltext 件の Memory（全文スコア付き、デフォルト 10）
  ※ 固有名詞・ファイルパス・コマンド名など、ベクトル検索が苦手な語に補完的に使用

Step 1 マージ: 両結果を統合・重複排除（最大 30 件程度）

Step 2: グラフ拡張
  取得 Memory の MENTIONS エッジ → Entity を収集
  Entity の CO_OCCURS_WITH エッジ → 関連 Entity を収集（深さ 2 まで）
  関連 Entity の MENTIONS 逆引き → 追加 Memory を収集（上限 30 件）

Step 3: スコアリング統合
  最終スコア = α × ベクトル類似度
             + β × グラフ近接度（最短パス長の逆数）
             + γ × 時間スコア（type 別指数減衰）
             + δ × 重要度スコア（Memory.score）
  α=0.5, β=0.2, γ=0.2, δ=0.1 （初期値、チューニング対象）
```

### 7.2 Cypher クエリ例（グラフ拡張検索）

```cypher
-- Step 1: ベクトル検索で近傍 Memory を取得
-- $graphDepth = config.json の memory.graph_depth（デフォルト 2）
CALL db.index.vector.queryNodes('memory_embedding_index', 20, $queryEmbedding)
YIELD node AS seedMemory, score AS vecScore
WHERE seedMemory.status = 'active'
MATCH (seedMemory)-[:BELONGS_TO]->(:Session)-[:IN_PROJECT]->(:Project {path: $project})

-- Step 2: グラフ拡張（OPTIONAL MATCH で関連 Memory を収集）
OPTIONAL MATCH (seedMemory)-[:MENTIONS]->(e:Entity)
  -[:CO_OCCURS_WITH*1..$graphDepth]-(re:Entity)
  <-[:MENTIONS]-(relatedMemory:Memory)
  -[:BELONGS_TO]->(:Session)-[:IN_PROJECT]->(:Project {path: $project})
WHERE relatedMemory <> seedMemory AND relatedMemory.status = 'active'

-- Step 3: seed / related をスコア情報付きでリスト化
-- （collect 後に seedMemory がスコープ外になるため、集約前にマップへ格納する）
WITH
  collect(DISTINCT {m: seedMemory, base: vecScore, graph: 1.0}) AS seedEntries,
  [x IN collect(DISTINCT relatedMemory) WHERE x IS NOT NULL
   | {m: x, base: 0.5, graph: 0.5}] AS relatedEntries
UNWIND (seedEntries + relatedEntries) AS entry

-- Step 4: 重複排除（同一 Memory が seed と related の両方に出現するケースに対応）
WITH entry.m AS m, max(entry.base) AS baseScore, max(entry.graph) AS graphScore

-- Step 5: 時間減衰スコアを計算して最終スコアを返す
WITH m, baseScore, graphScore,
  CASE m.type
    WHEN 'decision'  THEN 1.0
    WHEN 'knowledge' THEN exp(-0.693 * duration.inDays(m.created_at, datetime()).days / 90.0)
    ELSE                  exp(-0.693 * duration.inDays(m.created_at, datetime()).days / 30.0)
  END AS timeScore
RETURN
  m.content AS content,
  m.created_at AS createdAt,
  (0.5 * baseScore + 0.2 * graphScore + 0.2 * timeScore + 0.1 * m.score) AS finalScore
ORDER BY finalScore DESC
LIMIT $topK
```

### 7.3 Cypher クエリ例（全文検索）

クエリを fugashi で形態素解析してトークン化し、`memory_token_index` に投入する。ベクトル検索と並行して実行し、結果をマージする。

```cypher
-- クエリトークンを受け取り全文検索（OR がデフォルト）
CALL db.index.fulltext.queryNodes('memory_token_index', $queryTokens)
YIELD node AS m, score
WHERE m.status = 'active'
MATCH (m)-[:BELONGS_TO]->(:Session)-[:IN_PROJECT]->(:Project {path: $project})
RETURN m, score
ORDER BY score DESC
LIMIT $topKFulltext  -- config.json の memory.top_k_fulltext
```

```cypher
-- AND 検索（両キーワードを含む Memory に絞る）
CALL db.index.fulltext.queryNodes('memory_token_index', 'Neo4j AND ベクトルインデックス')
YIELD node AS m, score
...
```

`$queryTokens` は検索時にも fugashi で形態素解析して生成する（保存時と同じ処理）。

### 7.4 スコアリング式

```
finalScore = α × ベクトル類似度
           + β × グラフ近接度（最短パス長の逆数）
           + γ × 時間スコア（type 別指数減衰）
           + δ × 重要度（Memory.score）

α=0.5, β=0.2, γ=0.2, δ=0.1（初期値）
```

重みは `config.json` の `memory.score_weights` でチューニングする。

### 7.5 時間減衰パラメータ

type ごとに異なる半減期を適用する（§6.1 と対応）。

| type | 半減期 | 管理方法 |
|---|---|---|
| `decision` | なし | `status: "active" / "inactive"` で競合・無効化管理 |
| `knowledge` | 90 日 | 指数減衰 `exp(-0.693 × 経過日数 / 90)` |
| `tentative` | 30 日 | 指数減衰 `exp(-0.693 × 経過日数 / 30)` |
