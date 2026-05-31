# Long-Memory Embedding モデル選定

## 採用モデル：`qwen3-embedding:0.6b`（推奨）

| 項目 | 内容 |
|---|---|
| モデル名 | Qwen/Qwen3-Embedding-0.6B |
| Ollama タグ | `qwen3-embedding:0.6b` |
| ベクトル次元数 | 1024（32〜4096 で可変） |
| 対応言語 | 100 言語以上（日本語含む） |
| 最大トークン長 | 32768 |
| 特徴 | 密ベクトル、次元数可変（Matryoshka対応） |

**選定理由：**
- Ollama 公式サポート済みで `ollama pull qwen3-embedding:0.6b` で即時利用可能
- MTEB 多言語スコア（0.6B 版）が bge-m3（63.0）を上回る
- 最大 32768 トークン対応（bge-m3 の4倍）
- 次元数を可変にできるため、ストレージと精度のトレードオフを後から調整可能

**GPU リソースに余裕がある場合：**
- `qwen3-embedding:8b` — MTEB 多言語スコア 70.58（2026年5月時点で多言語 No.1）

---

## モデル比較

| モデル | MTEB 多言語 | MTEB 英語 | 次元数 | 最大トークン | Ollama | 備考 |
|---|---|---|---|---|---|---|
| **qwen3-embedding:0.6b** | **64.33** | 70.70 | 1024 | 32768 | ✅ | **現採用** |
| qwen3-embedding:4b | 69.45 | 74.60 | 4096 | 32768 | ✅ | GPU 推奨 |
| qwen3-embedding:8b | 70.58（多言語1位） | 75.22 | 4096 | 32768 | ✅ | GPU 必須 |
| bge-m3 | 63.0 | — | 1024 | 8192 | ✅ | 旧採用モデル |
| cl-nagoya/ruri-v3-310m | JMTEB 最高峰 | — | 768 | 8192 | ❌ | 日本語特化、Ollama 非対応 |
| multilingual-e5-large | — | — | 1024 | 512 | ✅ | 短文向け |

> **注:** qwen3-embedding:0.6b と bge-m3 の多言語スコア差は約1.3ポイント（64.33 vs 63.0）と僅差。
> 主な優位点はトークン長（32768 vs 8192）と次元数の可変対応。

---

## Ollama API 呼び出し仕様

```
エンドポイント: http://localhost:11434/api/embed
メソッド:       POST
Content-Type:  application/json

リクエスト:
{
  "model": "qwen3-embedding:0.6b",
  "input": ["テキスト1", "テキスト2"]   // バッチ対応
}

レスポンス:
{
  "model": "qwen3-embedding:0.6b",
  "embeddings": [[0.012, -0.034, ...], [...]]  // 1024次元
}
```

---

## モデル変更履歴

| 日付 | 変更内容 |
|---|---|
| 2026-05-31 | bge-m3 → qwen3-embedding:0.6b に変更（MTEB スコア・長文対応で優位） |
