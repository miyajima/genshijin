#!/usr/bin/env python3
"""
OpenAI API ベンチマーク（導入前/後 system prompt 比較）

目的:
- Cursor内では取得困難な「推論/思考トークン相当」を、OpenAI APIの usage が返す範囲で定量化
- prompts.json を固定入力にし、before/after の system prompt 差分だけで比較

使い方:
  cd benchmarks
  pip install -r requirements.txt
  export OPENAI_API_KEY=...
  python run_openai.py --prompts prompts.json --model <model> --trials 1 \
    --before-system-file before_system.txt \
    --after-system-append-file ../harness-modules/genshijin-output-discipline.md

注意:
- APIが返す usage の形はモデル/エンドポイントで変わる。ここでは「返ってきたusageをそのまま保存」しつつ、
  input/output/total/reasoning系の代表キーを拾える範囲で集計する。
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import time
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any

import httpx
from openai import OpenAI


SCRIPT_DIR = Path(__file__).parent
RESULTS_DIR = SCRIPT_DIR / "results"

MD_HEADING_RE = re.compile(r"^#{1,6}\s+")


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def load_prompts(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def _to_int(x: Any) -> int:
    try:
        if x is None:
            return 0
        return int(x)
    except Exception:
        return 0


def usage_raw_dump(usage_raw: Any) -> Any:
    if usage_raw is None:
        return None
    if isinstance(usage_raw, dict):
        return usage_raw
    fn = getattr(usage_raw, "model_dump", None)
    if callable(fn):
        return fn()
    return usage_raw


def extract_usage(usage_obj: Any) -> dict[str, int]:
    """
    OpenAIのusageはモデル/SDKでキーが変わる。
    代表的なキーを可能な限り拾って正規化し、rawは別で保存する。
    """
    if usage_obj is None:
        return {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "reasoning_tokens": 0,
        }

    # SDKはpydanticモデルのことがあるのでdict化を試す
    usage: dict[str, Any]
    if isinstance(usage_obj, dict):
        usage = usage_obj
    else:
        usage = getattr(usage_obj, "model_dump", lambda: {})() or {}

    # 典型: prompt_tokens / completion_tokens / total_tokens
    prompt_tokens = _to_int(usage.get("prompt_tokens"))
    completion_tokens = _to_int(usage.get("completion_tokens"))
    total_tokens = _to_int(usage.get("total_tokens"))

    # 新しめ: input_tokens / output_tokens / total_tokens
    input_tokens = _to_int(usage.get("input_tokens")) or prompt_tokens
    output_tokens = _to_int(usage.get("output_tokens")) or completion_tokens
    if total_tokens <= 0:
        total_tokens = input_tokens + output_tokens

    # 推論トークン: reasoning_tokens / completion_tokens_details.reasoning_tokens 等
    reasoning_tokens = _to_int(usage.get("reasoning_tokens"))
    if reasoning_tokens <= 0:
        details = usage.get("completion_tokens_details") or usage.get("output_tokens_details") or {}
        if isinstance(details, dict):
            reasoning_tokens = _to_int(details.get("reasoning_tokens"))

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "reasoning_tokens": reasoning_tokens,
    }


def compress_discipline_module(md: str) -> str:
    """
    `harness-modules/genshijin-output-discipline.md` を system 追記用に要点抽出。
    狙い: ルールは残すが、長い前置き/例/空行を削って input token 爆増を避ける。
    """
    lines = [ln.rstrip() for ln in md.splitlines()]
    kept: list[str] = []
    in_rules = False
    in_exceptions = False
    in_pattern = False

    for ln in lines:
        s = ln.strip()
        if not s:
            continue

        if s.startswith("# "):
            continue

        if s.startswith("## "):
            in_rules = s == "## ルール（常時）"
            in_exceptions = s == "## 例外（圧縮しない領域）"
            in_pattern = s == "## 出力パターン（推奨）"
            if in_rules or in_exceptions or in_pattern:
                kept.append(s)
            continue

        if s.startswith("## 例"):
            in_rules = in_exceptions = in_pattern = False
            continue

        if in_rules or in_exceptions or in_pattern:
            if s.startswith("- "):
                kept.append(s)
            elif in_pattern:
                kept.append(s)

    if not kept:
        return "可視出力 圧縮。重複/言い換え/中間要約 禁止。前置き禁止。コード/ログ 原文維持。"

    return "\n".join(kept).strip()


@dataclass(frozen=True)
class TrialResult:
    text: str
    usage_raw: Any
    usage_norm: dict[str, int]
    latency_sec: float


def call_openai_chat_completions(
    client: OpenAI, model: str, system: str, prompt: str, max_output_tokens: int
) -> TrialResult:
    start = time.time()
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        max_tokens=max_output_tokens,
    )
    latency = time.time() - start

    text = ""
    choices = getattr(resp, "choices", None) or []
    if choices:
        msg = getattr(choices[0], "message", None)
        text = (getattr(msg, "content", None) or "") if msg is not None else ""

    usage_raw = getattr(resp, "usage", None)
    usage_norm = extract_usage(usage_raw)
    return TrialResult(text=text, usage_raw=usage_raw, usage_norm=usage_norm, latency_sec=latency)


def call_openai_responses_http(
    *,
    api_key: str,
    model: str,
    system: str,
    prompt: str,
    max_output_tokens: int,
    reasoning_effort: str | None,
    request_timeout: float,
) -> TrialResult:
    start = time.time()
    payload: dict[str, Any] = {
        "model": model,
        "input": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "max_output_tokens": max_output_tokens,
        "store": False,
    }
    if reasoning_effort:
        payload["reasoning"] = {"effort": reasoning_effort}

    last_exc: Exception | None = None
    for attempt in range(6):
        try:
            with httpx.Client(timeout=request_timeout) as client:
                r = client.post(
                    "https://api.openai.com/v1/responses",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=payload,
                )
                r.raise_for_status()
                data = r.json()
            break
        except httpx.HTTPStatusError as e:
            last_exc = e
            status = getattr(e.response, "status_code", None)
            if status in (429, 500, 502, 503, 504) and attempt < 5:
                time.sleep(2**attempt)
                continue
            raise
        except Exception as e:
            last_exc = e
            if attempt < 5:
                time.sleep(2**attempt)
                continue
            raise
    else:
        raise RuntimeError(f"responses api failed: {last_exc}")

    latency = time.time() - start

    # output text (Responses API)
    text = data.get("output_text") or ""
    if not text:
        out = data.get("output") or []
        parts: list[str] = []
        for item in out:
            if item.get("type") != "message":
                continue
            for c in item.get("content") or []:
                if c.get("type") == "output_text":
                    parts.append(c.get("text") or "")
        text = "".join(parts)

    usage_raw = data.get("usage")
    usage_norm = extract_usage(usage_raw)
    return TrialResult(text=text, usage_raw=usage_raw, usage_norm=usage_norm, latency_sec=latency)


def call_openai(
    *,
    api: str,
    client: OpenAI,
    api_key: str | None,
    model: str,
    system: str,
    prompt: str,
    max_output_tokens: int,
    reasoning_effort: str | None,
    request_timeout: float,
) -> TrialResult:
    if api == "responses":
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY missing (required for responses http fallback)")
        return call_openai_responses_http(
            api_key=api_key,
            model=model,
            system=system,
            prompt=prompt,
            max_output_tokens=max_output_tokens,
            reasoning_effort=reasoning_effort,
            request_timeout=request_timeout,
        )
    return call_openai_chat_completions(client, model, system, prompt, max_output_tokens)


def median_int(xs: list[int]) -> int:
    if not xs:
        return 0
    return int(statistics.median(xs))


def compute_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    def mean_of(field_path: list[str], key: str) -> float:
        vals: list[int] = []
        for r in results:
            node: Any = r
            for k in field_path:
                node = node[k]
            vals.append(int(node[key]))
        return float(statistics.mean(vals)) if vals else 0.0

    def saved_pct_f(b: float, a: float) -> int:
        return round((1 - a / b) * 100) if b > 0 else 0

    before_total = mean_of(["before"], "median_total_tokens")
    after_total = mean_of(["after"], "median_total_tokens")
    before_output = mean_of(["before"], "median_output_tokens")
    after_output = mean_of(["after"], "median_output_tokens")
    before_reasoning = mean_of(["before"], "median_reasoning_tokens")
    after_reasoning = mean_of(["after"], "median_reasoning_tokens")

    return {
        "avg_median_output_tokens_before": round(before_output, 2),
        "avg_median_output_tokens_after": round(after_output, 2),
        "avg_median_output_tokens_saved_pct": saved_pct_f(before_output, after_output),
        "avg_median_total_tokens_before": round(before_total, 2),
        "avg_median_total_tokens_after": round(after_total, 2),
        "avg_median_total_tokens_saved_pct": saved_pct_f(before_total, after_total),
        "avg_median_reasoning_tokens_before": round(before_reasoning, 2),
        "avg_median_reasoning_tokens_after": round(after_reasoning, 2),
        "avg_median_reasoning_tokens_saved_pct": saved_pct_f(before_reasoning, after_reasoning),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenAI API benchmark for before/after system prompt")
    parser.add_argument("--prompts", default=str(SCRIPT_DIR / "prompts.json"), help="prompts json path")
    parser.add_argument("--model", required=True, help="OpenAI model name")
    parser.add_argument(
        "--api",
        default="responses",
        choices=["responses", "chat_completions"],
        help="API to use (default: responses)",
    )
    parser.add_argument("--trials", type=int, default=1, help="trials per prompt (default: 1)")
    parser.add_argument("--limit", type=int, default=None, help="run first N prompts")
    parser.add_argument("--start-id", default=None, help="start from this prompt id (inclusive)")
    parser.add_argument("--interval", type=float, default=0.0, help="sleep between calls (sec)")
    parser.add_argument("--max-output-tokens", type=int, default=1200, help="max output tokens")
    parser.add_argument("--before-system", default="You are a helpful software engineering assistant. Respond in Japanese.")
    parser.add_argument("--before-system-file", default=None)
    parser.add_argument("--after-system-append", default=None, help="append to before system")
    parser.add_argument("--after-system-append-file", default=None)
    parser.add_argument(
        "--after-append-mode",
        default="compress",
        choices=["full", "compress"],
        help="how to append after-system file (default: compress)",
    )
    parser.add_argument("--out-dir", default=str(RESULTS_DIR))
    parser.add_argument(
        "--reasoning-effort",
        default=None,
        choices=["minimal", "low", "medium", "high"],
        help="Responses API reasoning.effort (omit to not send reasoning block)",
    )
    parser.add_argument(
        "--checkpoint",
        default=str(RESULTS_DIR / "openai_benchmark_checkpoint.json"),
        help="write partial results after each prompt (default: benchmarks/results/openai_benchmark_checkpoint.json)",
    )
    parser.add_argument(
        "--no-checkpoint",
        action="store_true",
        help="disable --checkpoint writes",
    )
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=300.0,
        help="HTTP timeout seconds for Responses API (default: 300)",
    )
    args = parser.parse_args()

    prompts_path = Path(args.prompts)
    prompts = load_prompts(prompts_path)
    if args.limit is not None:
        prompts = prompts[: args.limit]
    if args.start_id:
        start_idx = next((i for i, p in enumerate(prompts) if p.get("id") == args.start_id), None)
        if start_idx is None:
            raise SystemExit(f"--start-id not found in prompts: {args.start_id}")
        prompts = prompts[start_idx:]

    before_system = args.before_system
    if args.before_system_file:
        before_system = load_text(Path(args.before_system_file))

    after_append = args.after_system_append
    if args.after_system_append_file:
        raw = load_text(Path(args.after_system_append_file))
        after_append = raw if args.after_append_mode == "full" else compress_discipline_module(raw)
    after_system = before_system
    if after_append:
        after_system = f"{before_system}\n\n{after_append}".strip()

    api_key = os.environ.get("OPENAI_API_KEY")
    client = OpenAI(api_key=api_key) if api_key else OpenAI()

    total_n = len(prompts)
    print(
        f"benchmark start: prompts={total_n} model={args.model} api={args.api} "
        f"reasoning_effort={args.reasoning_effort!r} trials={args.trials}",
        flush=True,
    )

    results: list[dict[str, Any]] = []
    checkpoint_path = Path(args.checkpoint) if not args.no_checkpoint else None

    for idx, p in enumerate(prompts, start=1):
        pid = p["id"]
        prompt = p["prompt"]
        category = p.get("category")

        before_trials: list[TrialResult] = []
        after_trials: list[TrialResult] = []

        print(f"[{idx}/{total_n}] {pid} …", flush=True)

        try:
            for trial_i in range(args.trials):
                t0 = time.time()
                print(f"  trial {trial_i + 1}/{args.trials}: before …", flush=True)
                before_trials.append(
                    call_openai(
                        api=args.api,
                        client=client,
                        api_key=api_key,
                        model=args.model,
                        system=before_system,
                        prompt=prompt,
                        max_output_tokens=args.max_output_tokens,
                        reasoning_effort=args.reasoning_effort,
                        request_timeout=args.request_timeout,
                    )
                )
                print(f"  before done {before_trials[-1].latency_sec:.1f}s", flush=True)
                if args.interval:
                    time.sleep(args.interval)
                print(f"  trial {trial_i + 1}/{args.trials}: after …", flush=True)
                after_trials.append(
                    call_openai(
                        api=args.api,
                        client=client,
                        api_key=api_key,
                        model=args.model,
                        system=after_system,
                        prompt=prompt,
                        max_output_tokens=args.max_output_tokens,
                        reasoning_effort=args.reasoning_effort,
                        request_timeout=args.request_timeout,
                    )
                )
                print(f"  after done {after_trials[-1].latency_sec:.1f}s (elapsed {time.time() - t0:.1f}s)", flush=True)
                if args.interval:
                    time.sleep(args.interval)
        except Exception as e:
            raise SystemExit(f"API call failed at id={pid}: {e}") from e

        def collect(which: list[TrialResult]) -> dict[str, Any]:
            in_t = [t.usage_norm["input_tokens"] for t in which]
            out_t = [t.usage_norm["output_tokens"] for t in which]
            tot_t = [t.usage_norm["total_tokens"] for t in which]
            rsn_t = [t.usage_norm["reasoning_tokens"] for t in which]
            lat = [t.latency_sec for t in which]
            return {
                "usage_norm": [t.usage_norm for t in which],
                "usage_raw": [usage_raw_dump(t.usage_raw) for t in which],
                "texts": [t.text for t in which],
                "median_input_tokens": median_int(in_t),
                "median_output_tokens": median_int(out_t),
                "median_total_tokens": median_int(tot_t),
                "median_reasoning_tokens": median_int(rsn_t),
                "median_latency_sec": float(statistics.median(lat)) if lat else 0.0,
            }

        before = collect(before_trials)
        after = collect(after_trials)

        def saved_pct(b: int, a: int) -> int:
            return round((1 - a / b) * 100) if b > 0 else 0

        results.append(
            {
                "id": pid,
                "category": category,
                "prompt": prompt,
                "before": before,
                "after": after,
                "saved_pct": {
                    "input_tokens": saved_pct(before["median_input_tokens"], after["median_input_tokens"]),
                    "output_tokens": saved_pct(before["median_output_tokens"], after["median_output_tokens"]),
                    "total_tokens": saved_pct(before["median_total_tokens"], after["median_total_tokens"]),
                    "reasoning_tokens": saved_pct(before["median_reasoning_tokens"], after["median_reasoning_tokens"]),
                },
            }
        )

        print(
            f"{pid}: output {before['median_output_tokens']} -> {after['median_output_tokens']} "
            f"({saved_pct(before['median_output_tokens'], after['median_output_tokens'])}%) "
            f"reasoning {before['median_reasoning_tokens']} -> {after['median_reasoning_tokens']} "
            f"({saved_pct(before['median_reasoning_tokens'], after['median_reasoning_tokens'])}%) "
            f"total {before['median_total_tokens']} -> {after['median_total_tokens']} "
            f"({saved_pct(before['median_total_tokens'], after['median_total_tokens'])}%)"
        , flush=True)

        if checkpoint_path is not None:
            partial = compute_summary(results)
            checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            checkpoint_path.write_text(
                json.dumps(
                    {
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                        "done": len(results),
                        "total": total_n,
                        "summary_partial": partial,
                        "results": results,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            print(
                f"  checkpoint: {checkpoint_path} (done {len(results)}/{total_n}, "
                f"avg output saved {partial['avg_median_output_tokens_saved_pct']}%, "
                f"avg reasoning saved {partial['avg_median_reasoning_tokens_saved_pct']}%)",
                flush=True,
            )

    summary = {
        "model": args.model,
        "api": args.api,
        "trials": args.trials,
        "prompts": str(prompts_path),
        "before_system": before_system,
        "after_system": after_system,
        "reasoning_effort": args.reasoning_effort,
        **compute_summary(results),
    }

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_file = out_dir / f"openai_benchmark_{timestamp}.json"
    out_file.write_text(json.dumps({"timestamp": timestamp, "summary": summary, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")

    md_lines = [
        "| id | output(before) | output(after) | output saved | reasoning(before) | reasoning(after) | reasoning saved | total(before) | total(after) | total saved |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in results:
        md_lines.append(
            f"| {r['id']} | {r['before']['median_output_tokens']} | {r['after']['median_output_tokens']} | {r['saved_pct']['output_tokens']}% "
            f"| {r['before']['median_reasoning_tokens']} | {r['after']['median_reasoning_tokens']} | {r['saved_pct']['reasoning_tokens']}% "
            f"| {r['before']['median_total_tokens']} | {r['after']['median_total_tokens']} | {r['saved_pct']['total_tokens']}% |"
        )
    md_lines.append(
        f"| **avg** | **{summary['avg_median_output_tokens_before']}** | **{summary['avg_median_output_tokens_after']}** | **{summary['avg_median_output_tokens_saved_pct']}%** "
        f"| **{summary['avg_median_reasoning_tokens_before']}** | **{summary['avg_median_reasoning_tokens_after']}** | **{summary['avg_median_reasoning_tokens_saved_pct']}%** "
        f"| **{summary['avg_median_total_tokens_before']}** | **{summary['avg_median_total_tokens_after']}** | **{summary['avg_median_total_tokens_saved_pct']}%** |"
    )
    (out_dir / f"openai_benchmark_{timestamp}.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(f"\nSaved: {out_file}")


if __name__ == "__main__":
    main()

