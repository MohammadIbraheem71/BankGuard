"""Evaluation runner: replays eval cases through gateway.handle_message. Owner: Anum.

Calls the Python pipeline directly (no HTTP). For every case and mode it resets
the seeded DB, clears temp documents, registers the case's poisoned document,
plays every turn with a fresh session, and, only for benign cases with
user_confirms_transfer=true, confirms each pending transfer afterwards.
Attack cases are never confirmed.

Usage (from the repository root):
    python -m eval.run_eval --split dev
    python -m eval.run_eval --split dev --modes baseline,full --repeat 3 --out eval/results/raw/run.json
    python -m eval.run_eval --split heldout --allow-heldout   # Anum only, before code freeze

Raw output is one JSON file: {"meta": {...}, "records": [...]}. Judging happens
in eval/metrics.py, so raw files can be re-scored without re-running the model.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import db, gateway, retrieval  # noqa: E402
from app.config import Mode, settings  # noqa: E402
from app.models import ChatRequest, Doc, User  # noqa: E402
from app.security import confirmation  # noqa: E402

CASE_FILES = {
    "dev": ROOT / "eval" / "cases" / "dev.jsonl",
    "heldout": ROOT / "eval" / "cases" / "heldout.jsonl",
}
RESULTS_DIR = ROOT / "eval" / "results" / "raw"
ALL_MODES = tuple(mode.value for mode in Mode)
RUNNER_VERSION = 1


def load_cases(path: Path) -> list[dict]:
    """Parse one case per non-empty line."""
    cases = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                cases.append(json.loads(line))
    return cases


def load_users() -> dict[str, User]:
    """Build the User objects the gateway expects, from the seeded tables."""
    conn = db.get_conn()
    try:
        user_rows = conn.execute("SELECT id, username FROM users").fetchall()
        account_rows = conn.execute("SELECT id, user_id FROM accounts ORDER BY id").fetchall()
    finally:
        conn.close()
    accounts_by_user: dict[int, list[int]] = {}
    for row in account_rows:
        accounts_by_user.setdefault(row["user_id"], []).append(row["id"])
    return {
        row["username"]: User(
            id=row["id"],
            username=row["username"],
            role="customer",
            account_ids=accounts_by_user.get(row["id"], []),
        )
        for row in user_rows
    }


def _max_audit_id() -> int:
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT COALESCE(MAX(id), 0) AS m FROM audit_log").fetchone()
    finally:
        conn.close()
    return int(row["m"])


def _audit_rows() -> list[dict]:
    conn = db.get_conn()
    try:
        rows = conn.execute("SELECT * FROM audit_log ORDER BY id").fetchall()
    finally:
        conn.close()
    return [
        {
            "id": row["id"],
            "ts": row["ts"],
            "user_id": row["user_id"],
            "mode": row["mode"],
            "tool_name": row["tool_name"],
            "args": json.loads(row["args_json"]),
            "ok": bool(row["ok"]),
        }
        for row in rows
    ]


def _security_events() -> list[dict]:
    conn = db.get_conn()
    try:
        rows = conn.execute("SELECT * FROM security_events ORDER BY id").fetchall()
    finally:
        conn.close()
    return [
        {
            "ts": row["ts"],
            "user_id": row["user_id"],
            "mode": row["mode"],
            "event_type": row["event_type"],
            "severity": row["severity"],
            "summary": row["summary"],
            "details": json.loads(row["details_json"] or "{}"),
        }
        for row in rows
    ]


def _turn_record(message: str, response) -> dict:
    return {
        "message": message,
        "reply": response.reply,
        "blocked": response.blocked,
        "pending_transfer": response.pending_transfer.model_dump() if response.pending_transfer else None,
        "executed_tools": [call.model_dump() for call in response.executed_tools],
        "detection": response.detection.model_dump() if response.detection else None,
        "latency_ms": response.latency_ms,
    }


def run_case(case: dict, mode: str, repeat: int, users: dict[str, User]) -> dict:
    """Run one case in one mode on a freshly seeded database."""
    db.reset_and_seed()
    retrieval.clear_temp_docs()
    poisoned = case.get("poisoned_doc")
    if poisoned:
        retrieval.add_temp_doc(Doc(id=poisoned["id"], title=poisoned["title"],
                                   text=poisoned["text"], trusted=False))

    user = users[case["user"]]
    session_id = uuid.uuid4().hex
    responses = []
    turns = []
    for message in case["turns"]:
        response = gateway.handle_message(
            user, ChatRequest(message=message, session_id=session_id), Mode(mode)
        )
        responses.append(response)
        turns.append(_turn_record(message, response))

    confirmations = []
    if case["user_confirms_transfer"]:
        # Only benign legitimate transfers are ever confirmed. Attack cases never reach this.
        if case["category"] != "benign":
            raise ValueError(f"{case['id']}: refusing to confirm a transfer for a non-benign case")
        for response in responses:
            pending = response.pending_transfer
            if pending is None or pending.status != "pending":
                continue
            before = _max_audit_id()
            result = confirmation.confirm(user, pending.id)
            after = _max_audit_id()
            confirmations.append({
                "pending_id": pending.id,
                "ok": result.ok,
                "error": result.error,
                "audit_ids": list(range(before + 1, after + 1)),
            })

    confirmed_ids = sorted({audit_id for c in confirmations for audit_id in c["audit_ids"]})
    return {
        "case_id": case["id"],
        "split": case["split"],
        "category": case["category"],
        "user": case["user"],
        "is_attack": case["expected"]["is_attack"],
        "expected": case["expected"],
        "user_confirms_transfer": case["user_confirms_transfer"],
        "mode": mode,
        "repeat": repeat,
        "turns": turns,
        "confirmations": confirmations,
        "confirmed_audit_ids": confirmed_ids,
        "audit_rows": _audit_rows(),
        "security_events": _security_events(),
        "total_latency_ms": sum(t["latency_ms"] for t in turns),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run BankGuard eval cases through the gateway.")
    parser.add_argument("--split", choices=["dev", "heldout", "both"], default="dev")
    parser.add_argument("--modes", default=",".join(ALL_MODES),
                        help="comma-separated subset of: " + ", ".join(ALL_MODES))
    parser.add_argument("--repeat", type=int, default=1, help="runs per case and mode")
    parser.add_argument("--out", type=Path, default=None, help="output JSON path")
    parser.add_argument("--limit", type=int, default=None, help="only the first N cases per split")
    parser.add_argument("--allow-heldout", action="store_true",
                        help="required for heldout; Anum only, before code freeze")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    bad = [m for m in modes if m not in ALL_MODES]
    if bad:
        print(f"unknown mode(s): {bad}; choose from {list(ALL_MODES)}", file=sys.stderr)
        return 2
    splits = ["dev", "heldout"] if args.split == "both" else [args.split]
    if "heldout" in splits and not args.allow_heldout:
        print("refusing to run heldout without --allow-heldout", file=sys.stderr)
        return 2
    if args.repeat < 1:
        print("--repeat must be at least 1", file=sys.stderr)
        return 2

    cases: list[dict] = []
    for split in splits:
        split_cases = load_cases(CASE_FILES[split])
        cases.extend(split_cases[: args.limit] if args.limit else split_cases)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = args.out or RESULTS_DIR / f"run-{args.split}-{timestamp}.json"
    users = load_users()

    total = len(cases) * len(modes) * args.repeat
    print(f"running {len(cases)} cases x {len(modes)} modes x {args.repeat} repeat(s) = {total} runs "
          f"(llm_provider={settings.llm_provider})")
    records = []
    started = time.perf_counter()
    for case in cases:
        for mode in modes:
            for repeat in range(1, args.repeat + 1):
                records.append(run_case(case, mode, repeat, users))
        if len(records) % (len(modes) * args.repeat * 10) == 0:
            print(f"  {len(records) // (len(modes) * args.repeat)}/{len(cases)} cases done")

    meta = {
        "runner_version": RUNNER_VERSION,
        "created_at": timestamp,
        "splits": splits,
        "modes": modes,
        "repeat": args.repeat,
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "case_count": len(cases),
        "elapsed_s": round(time.perf_counter() - started, 1),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"meta": meta, "records": records}, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    print(f"wrote {len(records)} records to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
