"""Verify that committed result tables reproduce from the committed raw runs.

Owner: Anum. This is offline: it re-judges saved raw JSON with eval/metrics.py
and never calls an LLM. With --strict it also checks that the behavior-relevant
code has not changed since the manifest's recorded eval commit.
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

# Files whose contents can change eval behavior. Result artifacts and docs may
# be updated after an eval commit without invalidating the recorded tables.
CODE_PATHS = (
    "app",
    "eval/*.py",
    "eval/cases",
    "scripts",
    "requirements.txt",
    "CONTRACT.md",
)


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


def git(*args: str) -> subprocess.CompletedProcess[str]:
    """Run a read-only git command against the repository root."""
    return subprocess.run(
        ["git", "-C", str(ROOT), *args],
        capture_output=True,
        text=True,
    )


def changed_paths(*args: str) -> list[str]:
    """Return non-empty changed-path lines from a git diff command."""
    result = git("diff", "--name-only", *args, "--", *CODE_PATHS)
    if result.returncode != 0:
        return [f"<git diff failed: {result.stderr.strip() or 'unknown error'}>"]
    return [line for line in result.stdout.splitlines() if line.strip()]


def verify_code_provenance(manifest: dict) -> list[str]:
    """Fail when code or raw metadata no longer matches the recorded eval commit."""
    errors: list[str] = []
    code = manifest.get("code", {})
    commit = code.get("commit")
    tree = code.get("tree")
    if not commit or not tree:
        return ["manifest code section must contain commit and tree"]

    exists = git("cat-file", "-e", f"{commit}^{{commit}}")
    if exists.returncode != 0:
        errors.append(f"manifest code.commit does not exist: {commit}")

    for run in manifest.get("runs", []):
        raw_path = FINAL_RAW / run["file"]
        if not raw_path.exists():
            continue
        meta = json.loads(raw_path.read_text(encoding="utf-8")).get("meta", {})
        for key, expected in (("git_commit", commit), ("git_tree", tree)):
            actual = meta.get(key)
            if not actual:
                errors.append(f"{run['file']}: raw meta missing {key}")
            elif actual != expected:
                errors.append(
                    f"{run['file']}: raw meta {key} mismatch "
                    f"({actual} != manifest {expected})"
                )

    since_commit = changed_paths(commit, "HEAD")
    if since_commit:
        errors.append(
            "behavior-relevant files changed since manifest commit: "
            + ", ".join(since_commit)
        )
    uncommitted = changed_paths("HEAD")
    if uncommitted:
        errors.append(
            "uncommitted behavior-relevant changes: " + ", ".join(uncommitted)
        )
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
        help="also fail on scratch JSON, stale code provenance, or uncommitted code changes",
    )
    args = parser.parse_args()

    errors: list[str] = verify_manifest()
    if args.strict:
        if MANIFEST.exists():
            manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
            errors.extend(verify_code_provenance(manifest))
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
