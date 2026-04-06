#!/usr/bin/env python3
"""
genshijin ベンチマーク
通常応答 vs 原始人モード応答のトークン使用量を比較する。

使い方:
  pip install -r requirements.txt
  export ANTHROPIC_API_KEY=sk-ant-...
  python run.py [--trials 3] [--model claude-sonnet-4-20250514] [--update-readme]
"""

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

from anthropic import Anthropic

SCRIPT_DIR = Path(__file__).parent
PROMPTS_FILE = SCRIPT_DIR / "prompts.json"
SKILL_FILE = SCRIPT_DIR.parent / "skills" / "genshijin" / "SKILL.md"
RESULTS_DIR = SCRIPT_DIR / "results"
README_FILE = SCRIPT_DIR.parent / "README.md"

NORMAL_SYSTEM = "あなたは親切で丁寧なソフトウェアエンジニアリングアシスタントです。日本語で回答してください。"


def load_skill() -> str:
    text = SKILL_FILE.read_text(encoding="utf-8")
    # frontmatter を除去
    if text.startswith("---"):
        end = text.index("---", 3)
        text = text[end + 3 :].strip()
    return text


def run_benchmark(
    client: Anthropic,
    model: str,
    prompts: list[dict],
    trials: int,
) -> list[dict]:
    skill_text = load_skill()
    results = []

    for prompt_data in prompts:
        prompt_id = prompt_data["id"]
        category = prompt_data["category"]
        prompt = prompt_data["prompt"]

        normal_tokens = []
        caveman_tokens = []

        for trial in range(trials):
            print(
                f"  [{trial + 1}/{trials}] {prompt_id}...",
                end=" ",
                flush=True,
            )

            # 通常応答
            resp_normal = client.messages.create(
                model=model,
                max_tokens=4096,
                system=NORMAL_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            n_tokens = resp_normal.usage.output_tokens
            normal_tokens.append(n_tokens)

            # 原始人応答
            resp_caveman = client.messages.create(
                model=model,
                max_tokens=4096,
                system=skill_text,
                messages=[{"role": "user", "content": prompt}],
            )
            c_tokens = resp_caveman.usage.output_tokens
            caveman_tokens.append(c_tokens)

            print(f"通常={n_tokens} 原始人={c_tokens}")

        median_normal = int(statistics.median(normal_tokens))
        median_caveman = int(statistics.median(caveman_tokens))
        saved_pct = round((1 - median_caveman / median_normal) * 100)

        results.append(
            {
                "id": prompt_id,
                "category": category,
                "prompt": prompt,
                "normal_tokens": normal_tokens,
                "caveman_tokens": caveman_tokens,
                "median_normal": median_normal,
                "median_caveman": median_caveman,
                "saved_pct": saved_pct,
            }
        )

    return results


def print_table(results: list[dict]) -> str:
    lines = [
        "| タスク | 通常 | 原始人 | 削減率 |",
        "|--------|------|--------|--------|",
    ]
    total_normal = 0
    total_caveman = 0

    for r in results:
        lines.append(
            f"| {r['prompt'][:30]} | {r['median_normal']} | {r['median_caveman']} | {r['saved_pct']}% |"
        )
        total_normal += r["median_normal"]
        total_caveman += r["median_caveman"]

    avg_saved = round((1 - total_caveman / total_normal) * 100)
    avg_normal = total_normal // len(results)
    avg_caveman = total_caveman // len(results)
    lines.append(f"| **平均** | **{avg_normal}** | **{avg_caveman}** | **{avg_saved}%** |")

    table = "\n".join(lines)
    print("\n" + table)
    return table


def update_readme(table: str) -> None:
    readme = README_FILE.read_text(encoding="utf-8")
    start_marker = "<!-- BENCHMARK_START -->"
    end_marker = "<!-- BENCHMARK_END -->"

    if start_marker not in readme:
        print("README.md にベンチマークマーカーが見つかりません。スキップ。")
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
    args = parser.parse_args()

    client = Anthropic()
    prompts = json.loads(PROMPTS_FILE.read_text(encoding="utf-8"))

    print(f"モデル: {args.model}")
    print(f"試行回数: {args.trials}")
    print(f"プロンプト数: {len(prompts)}")
    print()

    results = run_benchmark(client, args.model, prompts, args.trials)
    table = print_table(results)

    # 結果を保存
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    result_file = RESULTS_DIR / f"benchmark_{timestamp}.json"
    result_file.write_text(
        json.dumps(
            {
                "model": args.model,
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
        update_readme(table)


if __name__ == "__main__":
    main()
