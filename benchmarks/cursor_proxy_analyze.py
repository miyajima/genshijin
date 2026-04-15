#!/usr/bin/env python3
"""
Cursor Auto proxy benchmark analyzer.

Cursorのチャット出力をコピペ保存したテキストから、導入前後の差分を代理指標で集計する。
（トークンusageが取れない環境向け）
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SECTION_RE = re.compile(r"^===\s*(?P<id>[^=]+?)\s*===$")
TIME_RE = re.compile(r"^TIME_SEC:\s*(?P<sec>\d+(?:\.\d+)?)\s*$")
QUALITY_RE = re.compile(r"^QUALITY:\s*(?P<q>OK|NG)\s*$", re.IGNORECASE)

HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+\S+")
BULLET_RE = re.compile(r"^\s*[-*+]\s+\S+")
CODE_FENCE_RE = re.compile(r"^\s*```")


@dataclass(frozen=True)
class SectionMetrics:
    id: str
    text: str
    time_sec: float | None
    quality: str | None  # "OK" | "NG" | None

    chars: int
    lines: int
    headings: int
    bullets: int
    code_fence_lines: int
    code_lines: int


def load_prompts(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_export(text: str) -> dict[str, dict[str, Any]]:
    """
    Returns:
      { id: { "raw": str, "time_sec": float|None, "quality": "OK"|"NG"|None } }
    """
    current_id: str | None = None
    buf: list[str] = []
    time_sec: float | None = None
    quality: str | None = None
    out: dict[str, dict[str, Any]] = {}

    def flush():
        nonlocal current_id, buf, time_sec, quality
        if current_id is None:
            return
        raw = "\n".join(buf).strip("\n")
        out[current_id] = {"raw": raw, "time_sec": time_sec, "quality": quality}
        current_id = None
        buf = []
        time_sec = None
        quality = None

    for line in text.splitlines():
        m = SECTION_RE.match(line.strip())
        if m:
            flush()
            current_id = m.group("id").strip()
            continue

        if current_id is None:
            # header前のゴミは無視
            continue

        t = TIME_RE.match(line.strip())
        if t:
            try:
                time_sec = float(t.group("sec"))
            except ValueError:
                time_sec = None
            continue

        q = QUALITY_RE.match(line.strip())
        if q:
            quality = q.group("q").upper()
            continue

        buf.append(line)

    flush()
    return out


def compute_metrics(section_id: str, raw: str, time_sec: float | None, quality: str | None) -> SectionMetrics:
    lines = raw.splitlines()
    chars = len(raw)
    line_count = len(lines)

    headings = 0
    bullets = 0
    code_fence_lines = 0
    code_lines = 0
    in_code = False

    for ln in lines:
        if CODE_FENCE_RE.match(ln):
            code_fence_lines += 1
            in_code = not in_code
            continue
        if in_code:
            if ln.strip():
                code_lines += 1
            continue

        if HEADING_RE.match(ln):
            headings += 1
        if BULLET_RE.match(ln):
            bullets += 1

    return SectionMetrics(
        id=section_id,
        text=raw,
        time_sec=time_sec,
        quality=quality,
        chars=chars,
        lines=line_count,
        headings=headings,
        bullets=bullets,
        code_fence_lines=code_fence_lines,
        code_lines=code_lines,
    )


def pct_saved(baseline: float, new: float) -> int:
    if baseline <= 0:
        return 0
    return round((1 - (new / baseline)) * 100)


def fmt_int(n: float) -> str:
    return str(int(round(n)))


def main() -> None:
    parser = argparse.ArgumentParser(description="Cursor Auto proxy benchmark analyzer")
    parser.add_argument("--baseline", required=True, help="baseline export txt path")
    parser.add_argument("--discipline", required=True, help="discipline export txt path")
    parser.add_argument("--prompts", required=True, help="benchmarks/prompts.json path")
    parser.add_argument("--out-dir", default="benchmarks/results", help="output dir (default: benchmarks/results)")
    parser.add_argument("--out-prefix", default="cursor_proxy", help="output filename prefix")
    args = parser.parse_args()

    prompts_path = Path(args.prompts)
    baseline_path = Path(args.baseline)
    discipline_path = Path(args.discipline)
    out_dir = Path(args.out_dir)

    prompts = load_prompts(prompts_path)
    prompt_ids = [p["id"] for p in prompts]

    baseline_export = parse_export(baseline_path.read_text(encoding="utf-8"))
    discipline_export = parse_export(discipline_path.read_text(encoding="utf-8"))

    per_task: list[dict[str, Any]] = []

    for pid in prompt_ids:
        b = baseline_export.get(pid)
        d = discipline_export.get(pid)
        if not b or not d:
            per_task.append(
                {
                    "id": pid,
                    "missing": True,
                    "baseline_present": bool(b),
                    "discipline_present": bool(d),
                }
            )
            continue

        bm = compute_metrics(pid, b["raw"], b.get("time_sec"), b.get("quality"))
        dm = compute_metrics(pid, d["raw"], d.get("time_sec"), d.get("quality"))

        per_task.append(
            {
                "id": pid,
                "missing": False,
                "baseline": bm.__dict__,
                "discipline": dm.__dict__,
                "saved_pct": {
                    "chars": pct_saved(bm.chars, dm.chars),
                    "lines": pct_saved(bm.lines, dm.lines),
                    "code_lines": pct_saved(bm.code_lines, dm.code_lines),
                },
            }
        )

    def present_tasks() -> list[dict[str, Any]]:
        return [t for t in per_task if not t.get("missing")]

    def avg(field: str) -> float:
        vals = []
        for t in present_tasks():
            vals.append(float(t["discipline"][field]) if field in t["discipline"] else float(t["discipline"]["chars"]))
        return statistics.mean(vals) if vals else 0.0

    # averages for baseline/discipline
    def mean_pair(field: str) -> tuple[float, float]:
        bvals = []
        dvals = []
        for t in present_tasks():
            bvals.append(float(t["baseline"][field]))
            dvals.append(float(t["discipline"][field]))
        if not bvals:
            return 0.0, 0.0
        return statistics.mean(bvals), statistics.mean(dvals)

    b_chars, d_chars = mean_pair("chars")
    b_lines, d_lines = mean_pair("lines")
    b_code, d_code = mean_pair("code_lines")

    # time/quality summaries (optional)
    b_time_vals = [t["baseline"]["time_sec"] for t in present_tasks() if t["baseline"]["time_sec"] is not None]
    d_time_vals = [t["discipline"]["time_sec"] for t in present_tasks() if t["discipline"]["time_sec"] is not None]
    b_time_mean = statistics.mean(b_time_vals) if b_time_vals else None
    d_time_mean = statistics.mean(d_time_vals) if d_time_vals else None

    b_ok = sum(1 for t in present_tasks() if t["baseline"]["quality"] == "OK")
    d_ok = sum(1 for t in present_tasks() if t["discipline"]["quality"] == "OK")
    b_ng = sum(1 for t in present_tasks() if t["baseline"]["quality"] == "NG")
    d_ng = sum(1 for t in present_tasks() if t["discipline"]["quality"] == "NG")

    summary = {
        "prompts": str(prompts_path),
        "baseline": str(baseline_path),
        "discipline": str(discipline_path),
        "present_tasks": len(present_tasks()),
        "missing_tasks": len([t for t in per_task if t.get("missing")]),
        "avg": {
            "baseline_chars": round(b_chars, 2),
            "discipline_chars": round(d_chars, 2),
            "saved_chars_pct": pct_saved(b_chars, d_chars),
            "baseline_lines": round(b_lines, 2),
            "discipline_lines": round(d_lines, 2),
            "saved_lines_pct": pct_saved(b_lines, d_lines),
            "baseline_code_lines": round(b_code, 2),
            "discipline_code_lines": round(d_code, 2),
            "saved_code_lines_pct": pct_saved(b_code, d_code),
            "baseline_time_sec_mean": round(b_time_mean, 2) if b_time_mean is not None else None,
            "discipline_time_sec_mean": round(d_time_mean, 2) if d_time_mean is not None else None,
            "baseline_quality_ok": b_ok,
            "baseline_quality_ng": b_ng,
            "discipline_quality_ok": d_ok,
            "discipline_quality_ng": d_ng,
        },
    }

    # markdown table (simple)
    md_lines = [
        "| id | baseline chars | discipline chars | saved | baseline lines | discipline lines | saved | baseline code lines | discipline code lines | saved |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for t in per_task:
        pid = t["id"]
        if t.get("missing"):
            md_lines.append(f"| {pid} | - | - | - | - | - | - | - | - | - |")
            continue
        bm = t["baseline"]
        dm = t["discipline"]
        md_lines.append(
            "| {id} | {bc} | {dc} | {spc}% | {bl} | {dl} | {spl}% | {bcl} | {dcl} | {spcl}% |".format(
                id=pid,
                bc=bm["chars"],
                dc=dm["chars"],
                spc=t["saved_pct"]["chars"],
                bl=bm["lines"],
                dl=dm["lines"],
                spl=t["saved_pct"]["lines"],
                bcl=bm["code_lines"],
                dcl=dm["code_lines"],
                spcl=t["saved_pct"]["code_lines"],
            )
        )
    md_lines.append(
        "| **avg** | **{bc}** | **{dc}** | **{spc}%** | **{bl}** | **{dl}** | **{spl}%** | **{bcl}** | **{dcl}** | **{spcl}%** |".format(
            bc=fmt_int(b_chars),
            dc=fmt_int(d_chars),
            spc=summary["avg"]["saved_chars_pct"],
            bl=fmt_int(b_lines),
            dl=fmt_int(d_lines),
            spl=summary["avg"]["saved_lines_pct"],
            bcl=fmt_int(b_code),
            dcl=fmt_int(d_code),
            spcl=summary["avg"]["saved_code_lines_pct"],
        )
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json = out_dir / f"{args.out_prefix}_{timestamp}.json"
    out_md = out_dir / f"{args.out_prefix}_{timestamp}.md"

    out_json.write_text(
        json.dumps({"timestamp": timestamp, "summary": summary, "results": per_task}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    out_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print("Wrote:")
    print(f"- {out_json}")
    print(f"- {out_md}")


if __name__ == "__main__":
    main()

