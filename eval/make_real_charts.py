"""Draw report charts from the real-model result CSVs in eval/results/real/.

Usage (from the repository root):
    python -m eval.make_real_charts                                  # dev, eval/results/real
    python -m eval.make_real_charts eval/results/heldout "held-out split, criteria v2"

Reads only results_overall.csv and results_by_category.csv in the given folder
and writes two PNG files next to them. No numbers are computed here beyond
reading the CSV columns; the values are plotted as recorded.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

DEFAULT_DIR = Path(__file__).resolve().parent / "results" / "real"
MODES = ["baseline", "detector_only", "full"]
ATTACK_CATEGORIES = [
    "direct_injection",
    "doc_injection",
    "role_impersonation",
    "cross_account",
    "multi_turn",
    "exfiltration",
]


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def chart_attack_success_by_category(by_cat: list[dict[str, str]], out: Path, title: str) -> None:
    rates = {(r["mode"], r["category"]): float(r["attack_success_rate"]) * 100 for r in by_cat
             if r["category"] in ATTACK_CATEGORIES}
    width = 0.27
    xs = range(len(ATTACK_CATEGORIES))
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for i, mode in enumerate(MODES):
        ys = [rates[(mode, c)] for c in ATTACK_CATEGORIES]
        bars = ax.bar([x + (i - 1) * width for x in xs], ys, width, label=mode)
        ax.bar_label(bars, labels=[f"{y:.1f}" for y in ys], fontsize=7, padding=2)
    ax.set_xticks(list(xs))
    ax.set_xticklabels(ATTACK_CATEGORIES, rotation=15)
    ax.set_ylabel("Attack success rate (%)")
    ax.set_ylim(0, 100)
    ax.set_title(title)
    ax.legend(title="Mode")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def chart_latency(overall: list[dict[str, str]], out: Path, title: str) -> None:
    by_mode = {r["mode"]: r for r in overall}
    width = 0.35
    xs = range(len(MODES))
    mean = [float(by_mode[m]["latency_mean_ms"]) for m in MODES]
    p95 = [float(by_mode[m]["latency_p95_ms"]) for m in MODES]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.bar([x - width / 2 for x in xs], mean, width, label="mean")
    ax.bar([x + width / 2 for x in xs], p95, width, label="p95")
    ax.set_xticks(list(xs))
    ax.set_xticklabels(MODES)
    ax.set_ylabel("Latency per run (ms)")
    ax.set_title(title)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def main(argv: list[str] | None = None) -> None:
    """Usage: python -m eval.make_real_charts [results_dir] [split_label]."""
    args = argv if argv is not None else sys.argv[1:]
    results_dir = Path(args[0]) if args else DEFAULT_DIR
    label = args[1] if len(args) > 1 else "dev, judged under criteria v1"
    overall = _read(results_dir / "results_overall.csv")
    by_cat = _read(results_dir / "results_by_category.csv")
    out_success = results_dir / "chart_attack_success_by_category.png"
    out_latency = results_dir / "chart_latency.png"
    chart_attack_success_by_category(by_cat, out_success,
                                     f"Attack success by category, real model (gpt-4o-mini), {label}")
    chart_latency(overall, out_latency,
                  f"Whole-run latency, {label} (60 runs per mode)")
    print("wrote", out_success)
    print("wrote", out_latency)


if __name__ == "__main__":
    main()
