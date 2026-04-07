# genshijin 原始人 🗿

> なぜ多くのトークンを使う？少なくて済むのに。

Claude Code / Codex 向けの超圧縮コミュニケーションスキル。[caveman](https://github.com/JuliusBrussee/caveman) の日本語版をベースに、日本語特有の冗長表現に最適化。

トークン使用量を **約75%削減** しつつ、技術的正確性は100%維持。

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
/plugin install genshijin@interfacex/genshijin
```

または、マーケットプレイスを追加してからインストール:

```
/plugin marketplace add interfacex/genshijin
/plugin install genshijin
```

### 方法2: npx skills（サードパーティ）

```bash
npx skills add interfacex/genshijin
```

### 方法3: 手動インストール

**プロジェクト単位**（このリポジトリだけに適用）:

```bash
# リポジトリのルートで実行
mkdir -p .claude/skills/genshijin
curl -o .claude/skills/genshijin/SKILL.md \
  https://raw.githubusercontent.com/interfacex/genshijin/main/skills/genshijin/SKILL.md
```

**グローバル**（すべてのプロジェクトに適用）:

```bash
mkdir -p ~/.claude/skills/genshijin
curl -o ~/.claude/skills/genshijin/SKILL.md \
  https://raw.githubusercontent.com/interfacex/genshijin/main/skills/genshijin/SKILL.md
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
| タスク | 通常 | caveman | 原始人 | caveman削減 | 原始人削減 | 原始人 vs caveman |
|--------|------|---------|--------|------------|-----------|------------------|
| なぜReactコンポーネントが毎回再レンダリングされるのか説 | 1116 | 341 | 316 | 69% | 72% | 7% |
| 認証ミドルウェアのトークン有効期限チェックにバグがある。修正 | 2457 | 325 | 300 | 87% | 88% | 8% |
| Node.jsでPostgreSQLのコネクションプーリング | 1957 | 493 | 545 | 75% | 72% | -11% |
| git rebaseとmergeの違いを説明して | 822 | 293 | 375 | 64% | 54% | -28% |
| コールバック地獄をasync/awaitにリファクタリングし | 1449 | 477 | 534 | 67% | 63% | -12% |
| マイクロサービスとモノリスの比較を説明して | 999 | 436 | 407 | 56% | 59% | 7% |
| ExpressルートのPRをセキュリティ観点でレビューして | 1212 | 279 | 523 | 77% | 57% | -87% |
| Dockerのマルチステージビルドを設定して | 1473 | 342 | 346 | 77% | 77% | -1% |
| PostgreSQLのレースコンディションをデバッグして | 1919 | 610 | 634 | 68% | 67% | -4% |
| ReactのError Boundaryを実装して | 2748 | 597 | 424 | 78% | 85% | 29% |
| **平均** | **1615** | **419** | **440** | **74%** | **73%** | **-5%** |
<!-- BENCHMARK_END -->

> ベンチマークは英語版 [caveman](https://github.com/JuliusBrussee/caveman) の結果を参考値として掲載。
> 自分で計測するには:

```bash
cd benchmarks
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
python run.py --trials 3 --update-readme
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
