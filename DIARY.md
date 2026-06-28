# DIARY

## 2026-06-28 — OpenAI互換プロトコル対応

### 背景

既存コードはAnthropicのネイティブAPI形式のみに対応していた。OpenRouter利用時も`/api/v1/messages`エンドポイントとAnthropic形式を使っており、真のOpenAI互換プロトコルには非対応だった。

### 変更内容（`nanocode.py`）

#### API設定

- `OPENROUTER_API_KEY` → OpenRouterの`/chat/completions`エンドポイント（OpenAI互換）
- `OPENAI_API_KEY` → OpenAI直接接続（`https://api.openai.com/v1/chat/completions`）
- `ANTHROPIC_API_KEY` → 従来通りAnthropicネイティブ形式（`/v1/messages`）
- `PROVIDER` 変数を追加し、起動時表示を統一

#### ツールスキーマ生成（`make_schema()`）

- 共通の `_param_schemas()` ヘルパーでパラメータ構造を生成
- OpenAI互換: `{"type": "function", "function": {"name", "description", "parameters"}}`
- Anthropicネイティブ: `{"name", "description", "input_schema"}`

#### APIリクエスト（`call_api()`）

| 項目 | Anthropicネイティブ | OpenAI互換 |
|------|---------------------|------------|
| エンドポイント | `/v1/messages` | `/v1/chat/completions` |
| システムプロンプト | トップレベル `system` | `{"role": "system"}` をmessages先頭に挿入 |
| 認証ヘッダー | `x-api-key` | `Authorization: Bearer` |

#### レスポンスパース・エージェントループ（`main()`）

- OpenAI互換: `choices[0].message` → `content`（テキスト）+ `tool_calls`（配列）
- ツール結果の返し方: `role: "tool"` + `tool_call_id`（OpenAI仕様）
- Anthropicネイティブ: 従来通り `role: "user"` + `type: "tool_result"`

#### その他リファクタリング

- `_result_preview()` ヘルパーを抽出（Anthropic/OpenAI両パスで共通化）
- `tool_args` が空dictの場合でも安全な `next(iter(...), "")` に修正
