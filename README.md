# genshijin 原始人 🗿

> なぜ多くトークン使う？少なくて済む🗿

AI コーディングエージェント向けの超圧縮コミュニケーションスキル（Claude Code / Codex / Cursor / Hermes Agent / Antigravity / GitHub Copilot Chat 等）。[caveman](https://github.com/JuliusBrussee/caveman) の日本語版をベースに、日本語特有の冗長表現に最適化。

トークン使用量を **約75%削減** しつつ、技術的正確性は100%維持。

## 共通ハーネスへ取り込み（推奨）

このリポジトリは **中立**（特定ツールの設定ファイルや個人環境の絶対パスに依存しない）に保ち、導入先（あなたの共通ハーネス）へ「モジュール」を取り込む設計。

- **必須（出力規律）**: `harness-modules/genshijin-output-discipline.md`
- **任意（圧縮ルール本体）**: `skills/genshijin/SKILL.md` の「ルール」章（強度レベル含む）

取り込み後は、**途中経過/更新/下書き/最終報告**を含む「ユーザー可視の全出力」に圧縮を適用。

例外: **コミット/PR本文**、**ユーザー向けドキュメント成果物（README/設計ドキュメント等）**。

コード/ログ/エラー文は原文維持。

## 日本語への最適化ポイント

英語版 caveman は冠詞(a/an/the)やフィラーの削除が中心だが、日本語版は以下に対応:

| 英語版の削減対象 | 日本語版の削減対象 |
|-----------------|-------------------|
| 冠詞 (a/an/the) | 敬語・丁寧語 (です/ます/ございます) |
| フィラー (just/really/basically) | クッション言葉 (えーと/まあ/基本的に/一応) |
| 前置き (Sure! I'd be happy to...) | 前置き表現 (ご質問ありがとうございます...) |
| ぼかし (might/perhaps/likely) | ぼかし (〜かもしれません/おそらく/〜と思われます) |
| 冗長表現 | 冗長な助詞連続・敬語の二重化 |

## インストール

### 方法1: Claude Code プラグイン（推奨）

Claude Code 内で以下を実行:

```
/plugin install genshijin@InterfaceX-co-jp/genshijin
claude plugin marketplace add InterfaceX-co-jp/genshijin
```

### 方法2: npx skills（サードパーティ）

```bash
npx skills add InterfaceX-co-jp/genshijin
```

### 方法3: 手動インストール

**プロジェクト単位**（このリポジトリだけに適用）:

```bash
# リポジトリのルートで実行
mkdir -p .claude/skills/genshijin
curl -o .claude/skills/genshijin/SKILL.md \
  https://raw.githubusercontent.com/InterfaceX-co-jp/genshijin/main/skills/genshijin/SKILL.md
```

**グローバル**（すべてのプロジェクトに適用）:

```bash
mkdir -p ~/.claude/skills/genshijin
curl -o ~/.claude/skills/genshijin/SKILL.md \
  https://raw.githubusercontent.com/InterfaceX-co-jp/genshijin/main/skills/genshijin/SKILL.md
```

### 方法4: 一時的に使う

```bash
claude --plugin-dir ./path/to/genshijin
```

## 使い方

```
/genshijin          # 通常モード（デフォルト）で起動
/genshijin 丁寧     # ビジネス向け簡潔体
/genshijin 極限     # 最大圧縮
```

会話中に `原始人やめて` または `通常モード` で解除。

## 完了前チェック（運用）
- 途中経過を含むユーザー可視出力で、**重複/言い換え/中間要約**をしていない
- 例外領域（コミット/PR本文、ユーザー向けドキュメント成果物）では、読みやすさ優先（ただし冗長は避ける）

## 3段階の強度

### 丁寧モード
クッション言葉・ぼかし表現を削除。敬語は維持。ビジネスメール向き。

**Before:**
> ご質問ありがとうございます。お調べしたところ、こちらの問題につきましては、認証ミドルウェアにおけるトークンの有効期限チェックの部分に原因がある可能性が考えられます。

**After:**
> コンポーネントが再レンダリングされるのは、レンダリングごとに新しいオブジェクト参照が生成されるためです。`useMemo`で解決できます。

### 通常モード（デフォルト）
敬語を落とし体言止め。助詞も最小限。原始人の基本形。

**Before:**
> こちらの問題は、レンダリングが行われるたびに新しいオブジェクトの参照が生成されてしまうことが原因となっております。

**After:**
> レンダリング毎に新オブジェクト参照が生成。インラインオブジェクトprop = 新しい参照 = 再レンダリング。`useMemo`で包む。

### 極限モード
略語・矢印記法・一語回答。電報のような圧縮。

**Before:**
> データベースのコネクションプーリングというのは、リクエストが来るたびに新しい接続を確立するのではなく、あらかじめ作成しておいた接続を再利用する仕組みのことです。

**After:**
> プール = DB接続再利用。ハンドシェイク省略 → 高負荷時に高速。

## ベンチマーク

<!-- BENCHMARK_START -->
| タスク | 通常 | caveman | genshijin | caveman削減 | genshijin削減 | genshijin vs caveman |
|--------|------|---------|-----------|------------|-------------|---------------------|
| なぜReactコンポーネントが毎回再レンダリングされるのか説 | 1223 | 251 | 180 | 79% | 85% | 28% |
| 認証ミドルウェアのトークン有効期限チェックにバグがある。修正 | 1710 | 231 | 111 | 86% | 94% | 52% |
| Node.jsでPostgreSQLのコネクションプーリング | 2043 | 462 | 335 | 77% | 84% | 27% |
| git rebaseとmergeの違いを説明して | 720 | 291 | 225 | 60% | 69% | 23% |
| コールバック地獄をasync/awaitにリファクタリングし | 1711 | 461 | 275 | 73% | 84% | 40% |
| マイクロサービスとモノリスの比較を説明して | 1043 | 464 | 260 | 56% | 75% | 44% |
| ExpressルートのPRをセキュリティ観点でレビューして | 1329 | 260 | 103 | 80% | 92% | 60% |
| Dockerのマルチステージビルドを設定して | 1454 | 412 | 194 | 72% | 87% | 53% |
| PostgreSQLのレースコンディションをデバッグして | 1771 | 529 | 341 | 70% | 81% | 36% |
| ReactのError Boundaryを実装して | 2965 | 466 | 277 | 84% | 91% | 41% |
| CORSエラーが出る。原因と解決策を教えて | 799 | 362 | 216 | 55% | 73% | 40% |
| Nginxのリバースプロキシ設定を教えて | 1969 | 418 | 366 | 79% | 81% | 12% |
| Redisを使ったキャッシュ戦略を教えて | 2098 | 633 | 321 | 70% | 85% | 49% |
| TypeScriptのジェネリクスを初心者向けに説明して | 1261 | 668 | 366 | 47% | 71% | 45% |
| REST APIとGraphQLの違いを説明して | 885 | 400 | 313 | 55% | 65% | 22% |
| Node.jsアプリのメモリリークを調査する方法を教えて | 1832 | 584 | 319 | 68% | 83% | 45% |
| GitHub Actionsで基本的なCI/CDパイプライン | 2339 | 1079 | 431 | 54% | 82% | 60% |
| N+1クエリ問題とは何か、どう解決するか教えて | 1265 | 523 | 349 | 59% | 72% | 33% |
| WebSocketとServer-Sent Eventsの使 | 1079 | 480 | 262 | 56% | 76% | 45% |
| Reactの状態管理ライブラリの選び方を教えて | 901 | 363 | 242 | 60% | 73% | 33% |
| Kubernetesの基本概念を説明して | 928 | 415 | 228 | 55% | 75% | 45% |
| OAuth2の認証フローを説明して | 1116 | 425 | 300 | 62% | 73% | 29% |
| CSS FlexboxとGridの使い分けを教えて | 1059 | 333 | 295 | 69% | 72% | 11% |
| Pythonのデコレータの仕組みを説明して | 1395 | 449 | 306 | 68% | 78% | 32% |
| データベースインデックスの仕組みと使いどころを教えて | 1631 | 517 | 257 | 68% | 84% | 50% |
| JWTとセッションベース認証の比較を教えて | 1401 | 349 | 274 | 75% | 80% | 21% |
| Promise.allとPromise.raceの違いと使い | 1236 | 436 | 352 | 65% | 72% | 19% |
| TerraformでAWSインフラを管理する基本を教えて | 1345 | 568 | 383 | 58% | 72% | 33% |
| Node.jsのイベントループの仕組みを説明して | 1287 | 845 | 277 | 34% | 78% | 67% |
| APIのレート制限を実装する方法を教えて | 1819 | 805 | 616 | 56% | 66% | 23% |
| **平均** | **1453** | **482** | **292** | **67%** | **80%** | **39%** |
<!-- BENCHMARK_END -->

### 計測対象（思考中トークン含むか？）

- この表の数値: **Anthropic API の `usage.output_tokens` の中央値**
- “思考中トークン” は、**API が usage として返す範囲**のみ計測可能
  - ユーザーに見えない内部思考（非公開）は取得できない
  - もし thinking を有効化して usage に含まれる場合は **output/total に反映**

実行例:

```bash
cd benchmarks
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...

# 出力トークンのみ（従来）
python run.py --trials 3 --update-readme

# thinking 有効化 + 入力+出力（thinking が usage に入る場合は total に含まれる）
python run.py --trials 3 --metric total --thinking-budget 2000 --update-readme
```

### OpenAI（Responses）で reasoning も検証した結果

結論: **reasoning_tokens 削減は小さい（ほぼ変わらない）**。主効果は **output_tokens（可視出力）削減**。

条件:
- モデル: `gpt-5.4`
- API: Responses
- `reasoning_effort`: `medium`
- プロンプト: `benchmarks/prompts.json`（30問）
- after: `harness-modules/genshijin-output-discipline.md`（`compress`で要点抽出してsystem追記）

結果（中央値の平均）:

| 指標 | before | after | 削減 |
|---|---:|---:|---:|
| output_tokens | 1172.3 | 788.0 | 33% |
| reasoning_tokens | 142.0 | 137.6 | 3% |
| total_tokens | 1209.0 | 1176.7 | 3% |

参考: `benchmarks/results/openai_benchmark_merged_gpt54_medium_30_20260415_025206.json`

### Cursor Auto Proxy Benchmark（Usage画面なし代替）

Cursor Auto は API の `usage.tokens` を直接取れないことが多い。代替として **可視出力の量（代理指標）** を導入前後で比較する。

計測できるもの:
- 応答テキスト量（文字数/行数/コードブロック行数/箇条書き数/見出し数）
- 任意で応答時間（秒）と品質OK/NG

計測できないもの:
- **内部思考トークン（非公開）**
- Cursor側が表示しないトークンusage/cost

#### 手順（コピペ保存 → 集計）

1) ベースライン（導入前）と導入後で、同じ順序で `benchmarks/prompts.json` の `prompt` を Cursor に投げる  
2) 各応答を `baseline.txt` / `discipline.txt` にコピペ保存（下のフォーマット）  
3) 集計:

```bash
python benchmarks/cursor_proxy_analyze.py \
  --baseline baseline.txt \
  --discipline discipline.txt \
  --prompts benchmarks/prompts.json
```

#### 保存フォーマット（最小）

```text
=== react-rerender ===
TIME_SEC: 12
QUALITY: OK
<ここにCursorのアシスタント出力をそのまま貼る>

=== auth-middleware ===
TIME_SEC: 20
QUALITY: NG
<...>
```

- `=== <id> ===` は必須（`benchmarks/prompts.json` の `id` と一致）
- `TIME_SEC:` と `QUALITY:` は任意（無い場合は未計測として扱う）

### English Benchmark (参考値)

genshijin は日本語最適化スキルだが、英語プロンプトでも圧縮効果を発揮するか検証。caveman（英語ネイティブ）との比較。

<!-- BENCHMARK_EN_START -->
*英語ベンチマーク未実行。`python run.py --lang en --trials 3 --update-readme` で生成。*
<!-- BENCHMARK_EN_END -->

> ベンチマークは英語版 [caveman](https://github.com/JuliusBrussee/caveman) の結果を参考値として掲載。
> 自分で計測するには:

```bash
cd benchmarks
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
python run.py --trials 3 --update-readme              # 日本語
python run.py --lang en --trials 3 --update-readme     # 英語
```

## 安全機能

セキュリティ警告や破壊的操作の確認時は自動的に通常の丁寧な日本語に切り替わる。誤解が致命的になる場面では正確性を優先。

## プロジェクト構成

```
genshijin/
├── skills/genshijin/SKILL.md   # コアのスキル定義
├── .claude-plugin/
│   ├── plugin.json               # Claude Code プラグインマニフェスト
│   └── marketplace.json          # マーケットプレイス定義
├── benchmarks/
│   ├── run.py                    # ベンチマークスクリプト
│   ├── prompts.json              # テスト用プロンプト（10問）
│   └── requirements.txt          # Python依存パッケージ
├── README.md
├── LICENSE
└── .gitignore
```

## 元プロジェクト

[JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman) — 英語版オリジナル

## ライセンス

MIT
