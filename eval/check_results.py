"""Verify that committed result tables reproduce from the committed raw runs.

Owner: Anum. This is offline: it re-judges saved raw JSON with eval/metrics.py
and never calls an LLM.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FINAL_RAW = ROOT / "eval" / "results" / "final_raw"
MANIFEST = FINAL_RAW / "manifest.json"
RESULTS = ROOT / "eval" / "results"
PAIRS = {
    "final-dev.json": ROOT / "eval" / "results" / "real",
    "final-heldout.json": ROOT / "eval" / "results" / "heldout",
}
TABLES = ("results_overall.csv", "results_by_category.csv", "results.md")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rescore(raw_path: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [sys.executable, "-m", "eval.metrics", str(raw_path), "--out-dir", str(out_dir)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def verify_manifest() -> list[str]:
    """Check the committed provenance manifest against the raw/table bytes."""
    errors: list[str] = []
    if not MANIFEST.exists():
        return [f"missing manifest: {MANIFEST.relative_to(ROOT)}"]
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for run in manifest.get("runs", []):
        raw_path = FINAL_RAW / run["file"]
        if not raw_path.exists():
            errors.append(f"manifest names missing raw file: {run['file']}")
            continue
        if run["sha256"] != sha256(raw_path):
            errors.append(f"manifest hash mismatch: {run['file']}")
        if run["bytes"] != raw_path.stat().st_size:
            errors.append(f"manifest byte-count mismatch: {run['file']}")
        table_path = ROOT / run["result_table"]
        if not table_path.exists():
            errors.append(f"manifest names missing table: {run['result_table']}")
            continue
        if run["result_table_sha256"] != sha256(table_path):
            errors.append(f"manifest table hash mismatch: {run['result_table']}")
    return errors


def strict_extra_json() -> list[str]:
    """JSON files under eval/results that are not the final raw runs or manifest."""
    allowed = {FINAL_RAW / name for name in PAIRS}
    allowed.add(FINAL_RAW / "manifest.json")
    return sorted(
        str(path.relative_to(ROOT))
        for path in RESULTS.rglob("*.json")
        if path not in allowed
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="also fail when scratch JSON exists anywhere under eval/results",
    )
    args = parser.parse_args()

    errors: list[str] = verify_manifest()
    if args.strict:
        extra = strict_extra_json()
        if extra:
            errors.append("unexpected JSON under eval/results: " + ", ".join(extra))

    scratch_root = Path("/tmp/opencode")
    scratch_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="bankguard-check-", dir=scratch_root) as tmp:
        work = Path(tmp)
        for raw_name, expected_dir in PAIRS.items():
            raw_path = FINAL_RAW / raw_name
            if not raw_path.exists():
                errors.append(f"missing raw file: {raw_path.relative_to(ROOT)}")
                continue
            generated_dir = work / raw_path.stem
            rescore(raw_path, generated_dir)
            for table in TABLES:
                generated = generated_dir / table
                committed = expected_dir / table
                if not generated.exists() or not committed.exists():
                    errors.append(f"missing table: {table} for {raw_name}")
                    continue
                if sha256(generated) != sha256(committed):
                    errors.append(f"hash mismatch: {raw_name} -> {table}")
            print(f"{raw_name}: checked {len(TABLES)} tables")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("OK: final raw files reproduce all committed result tables")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
