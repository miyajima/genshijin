#!/usr/bin/env python3
"""
genshijin ベンチマーク
通常応答 vs caveman vs genshijin モード応答のトークン使用量を比較する。

使い方:
  pip install -r requirements.txt
  export ANTHROPIC_API_KEY=sk-ant-...
  python run.py [--trials 3] [--model claude-sonnet-4-20250514] [--update-readme]
"""

import argparse
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from anthropic import Anthropic, RateLimitError

SCRIPT_DIR = Path(__file__).parent
PROMPTS_FILE_JA = SCRIPT_DIR / "prompts.json"
PROMPTS_FILE_EN = SCRIPT_DIR / "prompts_en.json"
SKILL_FILE = SCRIPT_DIR.parent / "skills" / "genshijin" / "SKILL.md"
CAVEMAN_SKILL_FILE = SCRIPT_DIR / "caveman_skill.md"
RESULTS_DIR = SCRIPT_DIR / "results"
README_FILE = SCRIPT_DIR.parent / "README.md"
DOCS_DIR = SCRIPT_DIR.parent / "docs"

NORMAL_SYSTEM_JA = "あなたは親切で丁寧なソフトウェアエンジニアリングアシスタントです。日本語で回答してください。"
NORMAL_SYSTEM_EN = "You are a helpful and thorough software engineering assistant. Respond in English."
CAVEMAN_SUFFIX_JA = "\n\n日本語で回答してください。"


def load_skill(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    # frontmatter を除去
    if text.startswith("---"):
        end = text.index("---", 3)
        text = text[end + 3 :].strip()
    return text


API_CALL_INTERVAL = 3  # リクエスト間の待機秒数（デフォルト）
MAX_RETRIES = 5


def api_call_with_retry(client, **kwargs):
    """Rate limit対応のリトライ付きAPI呼び出し。"""
    for attempt in range(MAX_RETRIES):
        try:
            return client.messages.create(**kwargs)
        except RateLimitError:
            wait = 2 ** attempt * 10  # 10, 20, 40, 80, 160秒
            print(f"\n    Rate limit hit, waiting {wait}s...", end=" ", flush=True)
            time.sleep(wait)
    return client.messages.create(**kwargs)


def run_benchmark(
    client: Anthropic,
    model: str,
    prompts: list[dict],
    trials: int,
    lang: str = "ja",
    metric: str = "output",
    thinking_budget: int | None = None,
    normal_system_append: str | None = None,
    api_call_interval: int = API_CALL_INTERVAL,
) -> list[dict]:
    genshijin_text = load_skill(SKILL_FILE)
    caveman_text = load_skill(CAVEMAN_SKILL_FILE)
    if lang == "ja":
        normal_system = NORMAL_SYSTEM_JA
        caveman_text += CAVEMAN_SUFFIX_JA
    else:
        normal_system = NORMAL_SYSTEM_EN
    if normal_system_append:
        normal_system = f"{normal_system}\n\n{normal_system_append}".strip()
    results = []

    for prompt_data in prompts:
        prompt_id = prompt_data["id"]
        category = prompt_data["category"]
        prompt = prompt_data["prompt"]

        normal_tokens = []
        caveman_tokens = []
        genshijin_tokens = []
        normal_usage = []
        caveman_usage = []
        genshijin_usage = []
        normal_texts = []
        caveman_texts = []
        genshijin_texts = []

        for trial in range(trials):
            print(
                f"  [{trial + 1}/{trials}] {prompt_id}...",
                end=" ",
                flush=True,
            )

            def extract_usage(resp) -> dict:
                usage = resp.usage
                # anthropic SDK: usage.input_tokens / usage.output_tokens
                input_tokens = getattr(usage, "input_tokens", 0) or 0
                output_tokens = getattr(usage, "output_tokens", 0) or 0
                total_tokens = input_tokens + output_tokens
                return {
                    "input_tokens": int(input_tokens),
                    "output_tokens": int(output_tokens),
                    "total_tokens": int(total_tokens),
                }

            def pick_metric(usage_dict: dict) -> int:
                if metric == "total":
                    return usage_dict["total_tokens"]
                return usage_dict["output_tokens"]

            extra_kwargs = {}
            if thinking_budget is not None:
                # NOTE: When supported by the model/runtime, thinking tokens are included in usage.
                extra_kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}

            # 通常応答
            resp_normal = api_call_with_retry(
                client,
                model=model,
                max_tokens=4096,
                system=normal_system,
                messages=[{"role": "user", "content": prompt}],
                **extra_kwargs,
            )
            n_usage = extract_usage(resp_normal)
            n_tokens = pick_metric(n_usage)
            normal_tokens.append(n_tokens)
            normal_usage.append(n_usage)
            normal_texts.append(resp_normal.content[0].text)

            time.sleep(api_call_interval)

            # caveman応答
            resp_caveman = api_call_with_retry(
                client,
                model=model,
                max_tokens=4096,
                system=caveman_text,
                messages=[{"role": "user", "content": prompt}],
                **extra_kwargs,
            )
            cv_usage = extract_usage(resp_caveman)
            cv_tokens = pick_metric(cv_usage)
            caveman_tokens.append(cv_tokens)
            caveman_usage.append(cv_usage)
            caveman_texts.append(resp_caveman.content[0].text)

            time.sleep(api_call_interval)

            # genshijin応答
            resp_genshijin = api_call_with_retry(
                client,
                model=model,
                max_tokens=4096,
                system=genshijin_text,
                messages=[{"role": "user", "content": prompt}],
                **extra_kwargs,
            )
            g_usage = extract_usage(resp_genshijin)
            g_tokens = pick_metric(g_usage)
            genshijin_tokens.append(g_tokens)
            genshijin_usage.append(g_usage)
            genshijin_texts.append(resp_genshijin.content[0].text)

            print(f"通常={n_tokens} caveman={cv_tokens} genshijin={g_tokens}")

        median_normal = int(statistics.median(normal_tokens))
        median_caveman = int(statistics.median(caveman_tokens))
        median_genshijin = int(statistics.median(genshijin_tokens))
        saved_caveman_pct = round((1 - median_caveman / median_normal) * 100)
        saved_genshijin_pct = round((1 - median_genshijin / median_normal) * 100)
        # genshijin vs caveman の改善率
        vs_caveman_pct = round((1 - median_genshijin / median_caveman) * 100) if median_caveman > 0 else 0

        results.append(
            {
                "id": prompt_id,
                "category": category,
                "prompt": prompt,
                "normal_tokens": normal_tokens,
                "caveman_tokens": caveman_tokens,
                "genshijin_tokens": genshijin_tokens,
                "normal_usage": normal_usage,
                "caveman_usage": caveman_usage,
                "genshijin_usage": genshijin_usage,
                "normal_texts": normal_texts,
                "caveman_texts": caveman_texts,
                "genshijin_texts": genshijin_texts,
                "median_normal": median_normal,
                "median_caveman": median_caveman,
                "median_genshijin": median_genshijin,
                "saved_caveman_pct": saved_caveman_pct,
                "saved_genshijin_pct": saved_genshijin_pct,
                "vs_caveman_pct": vs_caveman_pct,
            }
        )

    return results


def print_table(results: list[dict], lang: str = "ja") -> str:
    if lang == "en":
        header = [
            "| Task | Normal | caveman | genshijin | caveman saved | genshijin saved | genshijin vs caveman |",
            "|------|--------|---------|-----------|--------------|----------------|---------------------|",
        ]
        avg_label = "**Average**"
    else:
        header = [
            "| タスク | 通常 | caveman | genshijin | caveman削減 | genshijin削減 | genshijin vs caveman |",
            "|--------|------|---------|-----------|------------|-------------|---------------------|",
        ]
        avg_label = "**平均**"

    lines = list(header)
    total_normal = 0
    total_caveman = 0
    total_genshijin = 0

    for r in results:
        lines.append(
            f"| {r['prompt'][:30]} | {r['median_normal']} | {r['median_caveman']} "
            f"| {r['median_genshijin']} | {r['saved_caveman_pct']}% "
            f"| {r['saved_genshijin_pct']}% | {r['vs_caveman_pct']}% |"
        )
        total_normal += r["median_normal"]
        total_caveman += r["median_caveman"]
        total_genshijin += r["median_genshijin"]

    avg_normal = total_normal // len(results)
    avg_caveman = total_caveman // len(results)
    avg_genshijin = total_genshijin // len(results)
    avg_saved_cv = round((1 - total_caveman / total_normal) * 100)
    avg_saved_gs = round((1 - total_genshijin / total_normal) * 100)
    avg_vs = round((1 - total_genshijin / total_caveman) * 100) if total_caveman > 0 else 0
    lines.append(
        f"| {avg_label} | **{avg_normal}** | **{avg_caveman}** "
        f"| **{avg_genshijin}** | **{avg_saved_cv}%** "
        f"| **{avg_saved_gs}%** | **{avg_vs}%** |"
    )

    table = "\n".join(lines)
    print("\n" + table)
    return table


def update_readme(table: str, lang: str = "ja") -> None:
    readme = README_FILE.read_text(encoding="utf-8")
    if lang == "en":
        start_marker = "<!-- BENCHMARK_EN_START -->"
        end_marker = "<!-- BENCHMARK_EN_END -->"
    else:
        start_marker = "<!-- BENCHMARK_START -->"
        end_marker = "<!-- BENCHMARK_END -->"

    if start_marker not in readme:
        print(f"README.md にベンチマークマーカー ({start_marker}) が見つかりません。スキップ。")
        return

    before = readme[: readme.index(start_marker) + len(start_marker)]
    after = readme[readme.index(end_marker) :]
    new_readme = f"{before}\n{table}\n{after}"
    README_FILE.write_text(new_readme, encoding="utf-8")
    print("README.md を更新しました。")


def main():
    parser = argparse.ArgumentParser(description="genshijin ベンチマーク")
    parser.add_argument("--trials", type=int, default=3, help="試行回数 (デフォルト: 3)")
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-20250514",
        help="使用モデル (デフォルト: claude-sonnet-4-20250514)",
    )
    parser.add_argument(
        "--update-readme",
        action="store_true",
        help="README.md のベンチマークテーブルを更新",
    )
    parser.add_argument(
        "--update-docs",
        action="store_true",
        help="docs/benchmark.json を更新（GitHub Pages用）",
    )
    parser.add_argument(
        "--metric",
        default="output",
        choices=["output", "total"],
        help="集計トークン: output=出力のみ / total=入力+出力 (デフォルト: output)",
    )
    parser.add_argument(
        "--thinking-budget",
        type=int,
        default=None,
        help="可能なら thinking を有効化（budget tokens）。usage ベースで計測対象に含まれる。",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="先頭N件だけ実行（コスト削減用）。未指定なら全件。",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=API_CALL_INTERVAL,
        help="API呼び出し間隔（秒）。Rate limit 回避用 (デフォルト: 3)",
    )
    parser.add_argument(
        "--normal-system-append",
        default=None,
        help="通常応答の system に追記する文字列（共通ハーネス組み込み再現用）。",
    )
    parser.add_argument(
        "--normal-system-append-file",
        default=None,
        help="通常応答の system に追記するファイルパス（共通ハーネス組み込み再現用）。",
    )
    parser.add_argument(
        "--lang",
        default="ja",
        choices=["ja", "en"],
        help="ベンチマーク言語 (デフォルト: ja)",
    )
    args = parser.parse_args()

    client = Anthropic()
    prompts_file = PROMPTS_FILE_EN if args.lang == "en" else PROMPTS_FILE_JA
    prompts = json.loads(prompts_file.read_text(encoding="utf-8"))

    print(f"モデル: {args.model}")
    print(f"言語: {args.lang}")
    print(f"試行回数: {args.trials}")
    print(f"プロンプト数: {len(prompts)}")
    print(f"集計: {args.metric}")
    if args.thinking_budget is not None:
        print(f"thinking: enabled budget={args.thinking_budget}")
    print()

    if args.limit is not None:
        prompts = prompts[: args.limit]

    normal_system_append = args.normal_system_append
    if args.normal_system_append_file:
        normal_system_append = Path(args.normal_system_append_file).read_text(encoding="utf-8")

    results = run_benchmark(
        client,
        args.model,
        prompts,
        args.trials,
        lang=args.lang,
        metric=args.metric,
        thinking_budget=args.thinking_budget,
        normal_system_append=normal_system_append,
        api_call_interval=args.interval,
    )
    table = print_table(results, lang=args.lang)

    # 結果を保存
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    result_file = RESULTS_DIR / f"benchmark_{args.lang}_{timestamp}.json"
    result_file.write_text(
        json.dumps(
            {
                "model": args.model,
                "lang": args.lang,
                "trials": args.trials,
                "timestamp": timestamp,
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n結果を保存: {result_file}")

    if args.update_readme:
        update_readme(table, lang=args.lang)

    if args.update_docs:
        import shutil
        DOCS_DIR.mkdir(parents=True, exist_ok=True)
        docs_file = DOCS_DIR / f"benchmark{'_en' if args.lang == 'en' else ''}.json"
        shutil.copy2(result_file, docs_file)
        print(f"{docs_file.name} を更新しました。")


if __name__ == "__main__":
    main()
