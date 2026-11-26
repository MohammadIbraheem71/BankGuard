#!/usr/bin/env python3
"""Generate the README final-results table from the metrics CSV files.

Owner: Ibraheem. This script never types evaluation numbers by hand; it reads
`eval/results/real/results_overall.csv` and
`eval/results/heldout/results_overall.csv` and replaces the marked README block.
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402

BEGIN = "<!-- BEGIN FINAL RESULTS -->"
END = "<!-- END FINAL RESULTS -->"
MODES = ("baseline", "detector_only", "full")
SOURCES = (
    ("dev", ROOT / "eval/results/real/results_overall.csv", ROOT / "eval/results/real/results.md"),
    ("heldout", ROOT / "eval/results/heldout/results_overall.csv", ROOT / "eval/results/heldout/results.md"),
)


def _read_model(markdown_path: Path) -> str:
    match = re.search(r"model:\s*`([^`]+)`", markdown_path.read_text(encoding="utf-8"))
    if match is None:
        raise SystemExit(f"cannot find model name in {markdown_path}")
    return match.group(1)


def _count(row: dict[str, str], key: str) -> int:
    return int(float(row[key]))


def _rate(k: int, n: int) -> str:
    if n == 0:
        return f"n/a ({k}/{n})"
    return f"{k / n * 100:.1f}% ({k}/{n})"


def _ms(row: dict[str, str], key: str) -> str:
    value = row.get(key, "")
    return "n/a" if not value else f"{float(value):.1f}"


def _load_split(split: str, csv_path: Path) -> dict[str, dict[str, str]]:
    if not csv_path.exists():
        raise SystemExit(f"missing metrics file: {csv_path}")
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = {row["mode"]: row for row in csv.DictReader(handle)}
    missing = [mode for mode in MODES if mode not in rows]
    if missing:
        raise SystemExit(f"{csv_path}: missing modes {missing}")
    return rows


def build_table() -> str:
    models = {_read_model(markdown) for _, _, markdown in SOURCES}
    if len(models) != 1:
        raise SystemExit(f"result folders disagree on model: {sorted(models)}")
    model = next(iter(models))

    lines = [
        BEGIN,
        f"Model: `{model}`; temperature: `{settings.llm_temperature}`. "
        "Rate denominators: attack success and unauthorized executions use attack runs, "
        "leakage uses leak-eligible runs, false positives and completion use benign runs.",
        "",
        "| Mode | Split | Attack success | Unauthorized executions | Leakage | "
        "False positives | Completion | Mean latency (ms) | p95 latency (ms) |",
        "|---|---|---|---|---|---|---|---:|---:|",
    ]

    for split, csv_path, _ in SOURCES:
        rows = _load_split(split, csv_path)
        for mode in MODES:
            row = rows[mode]
            attacks = _count(row, "attack_runs")
            leak_eligible = _count(row, "leak_eligible_runs")
            benign = _count(row, "benign_runs")
            unauthorized = _count(row, "unauthorized_executions")
            lines.append(
                f"| {mode} | {split} | "
                f"{_rate(_count(row, 'attack_successes'), attacks)} | "
                f"{unauthorized} ({unauthorized}/{attacks}) | "
                f"{_rate(_count(row, 'leaks'), leak_eligible)} | "
                f"{_rate(_count(row, 'false_positives'), benign)} | "
                f"{_rate(_count(row, 'completed'), benign)} | "
                f"{_ms(row, 'latency_mean_ms')} | {_ms(row, 'latency_p95_ms')} |"
            )

    lines.append(END)
    return "\n".join(lines)


def main() -> int:
    table = build_table()
    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    if BEGIN not in text or END not in text:
        raise SystemExit(f"{readme}: missing {BEGIN} / {END} markers")
    start = text.index(BEGIN)
    end = text.index(END) + len(END)
    readme.write_text(text[:start] + table + text[end:], encoding="utf-8")
    print(table)
    return 0


if __name__ == "__main__":
    sys.exit(main())
