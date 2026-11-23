"""Streamlit security dashboard for BankGuard. Owner: Anum.

Run it on its own (it has its own login session):
    streamlit run ui/dashboard.py --server.port 8502

Three panels:
1. Security events from GET /events, with filters by mode, severity and event type.
2. Charts of event counts by type and by severity (for the filtered rows).
3. Evaluation comparison: baseline vs detector_only vs full, read from the latest
   eval/results/ CSVs written by eval/metrics.py.

Only the backend HTTP API and local result files are used; nothing is imported from app/.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

UI_DIR = Path(__file__).resolve().parent
ROOT = UI_DIR.parent
RESULTS_DIR = ROOT / "eval" / "results"
sys.path.insert(0, str(UI_DIR))
from api import API_URL, call, log_in  # noqa: E402

MODES = ("baseline", "detector_only", "full")
SEVERITIES = ("low", "medium", "high")
EVENT_COLUMNS = ["ts", "user_id", "mode", "event_type", "severity", "summary", "details"]

RATE_METRICS = [
    ("attack_success_rate", "Attack success rate"),
    ("unauthorized_executions", "Unauthorized tool executions"),
    ("leakage_rate", "Protected-data leakage rate"),
    ("false_positive_rate", "False-positive rate (benign)"),
    ("completion_rate", "Legitimate task completion"),
    ("latency_mean_ms", "Mean latency (ms)"),
    ("latency_p95_ms", "p95 latency (ms)"),
    ("overhead_mean_ms", "Mean overhead vs baseline (ms)"),
    ("overhead_p95_ms", "p95 overhead vs baseline (ms)"),
]
PERCENT_KEYS = {"attack_success_rate", "leakage_rate", "false_positive_rate", "completion_rate"}


# ----------------------------------------------------------------- events

def fetch_events(mode: str | None, limit: int) -> tuple[pd.DataFrame, str | None]:
    params: dict = {"limit": limit}
    if mode:
        params["mode"] = mode
    data, error = call("GET", "/events", params=params)
    if error:
        return pd.DataFrame(columns=EVENT_COLUMNS), error
    frame = pd.DataFrame(data)
    if frame.empty:
        return pd.DataFrame(columns=EVENT_COLUMNS), None
    frame["details"] = frame["details"].apply(lambda d: json.dumps(d, sort_keys=True, ensure_ascii=False))
    return frame[EVENT_COLUMNS], None


def severity_counts(frame: pd.DataFrame) -> pd.Series:
    counts = frame["severity"].value_counts() if not frame.empty else pd.Series(dtype=int)
    return counts.reindex(SEVERITIES, fill_value=0)


def type_counts(frame: pd.DataFrame) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=int, name="count")
    return frame["event_type"].value_counts().sort_index()


def render_events_panel() -> None:
    st.header("Security events")
    with st.sidebar:
        st.subheader("Event filters")
        mode_choice = st.selectbox("Mode", ["all", *MODES], key="ev_mode")
        limit = st.number_input("Max rows fetched", min_value=10, max_value=1000,
                                value=200, step=10, key="ev_limit")
        if st.button("Refresh events", width="stretch"):
            st.rerun()

    frame, error = fetch_events(None if mode_choice == "all" else mode_choice, int(limit))
    if error:
        st.error(error)
        return
    if frame.empty:
        st.info("No security events yet. Run a chat in the chat app, or run the eval harness.")
        return

    with st.sidebar:
        severity_pick = st.multiselect("Severity", list(SEVERITIES), default=list(SEVERITIES),
                                       key="ev_sev")
        type_options = sorted(frame["event_type"].unique())
        type_pick = st.multiselect("Event type", type_options, default=type_options, key="ev_type")

    filtered = frame[frame["severity"].isin(severity_pick) & frame["event_type"].isin(type_pick)]
    st.caption(f"Showing {len(filtered)} of {len(frame)} fetched events from {API_URL}/events. "
               "Summaries are shown as stored by the backend.")
    st.dataframe(filtered, width="stretch", hide_index=True)

    col_type, col_sev = st.columns(2)
    with col_type:
        st.subheader("Events by type")
        counts = type_counts(filtered)
        if counts.empty:
            st.info("No rows match the filters.")
        else:
            st.bar_chart(counts)
    with col_sev:
        st.subheader("Events by severity")
        st.bar_chart(severity_counts(filtered))


# ------------------------------------------------------------ comparison

def _results_provider() -> str | None:
    md = RESULTS_DIR / "results.md"
    if not md.exists():
        return None
    match = re.search(r"llm_provider: `([^`]+)`", md.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def load_results() -> tuple[pd.DataFrame | None, pd.DataFrame | None, str | None]:
    overall_path = RESULTS_DIR / "results_overall.csv"
    category_path = RESULTS_DIR / "results_by_category.csv"
    if not overall_path.exists() or not category_path.exists():
        return None, None, None
    overall = pd.read_csv(overall_path)
    by_category = pd.read_csv(category_path)
    stamp = datetime.fromtimestamp(overall_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    return overall, by_category, stamp


def _format(key: str, value) -> str:
    if pd.isna(value):
        return "n/a"
    if key in PERCENT_KEYS:
        return f"{value * 100:.1f}%"
    if key == "unauthorized_executions":
        return f"{int(value)}"
    return f"{value:+.1f}" if key.startswith("overhead") else f"{value:.1f}"


def render_comparison_panel() -> None:
    st.header("Evaluation: baseline vs detector_only vs full")
    overall, by_category, stamp = load_results()
    if overall is None:
        st.info("No results yet. Run `python -m eval.run_eval --split dev` and then "
                "`python -m eval.metrics eval/results/raw/<file>.json`.")
        return

    provider = _results_provider()
    st.caption(f"Latest results written {stamp} (eval/results/). LLM provider: `{provider or 'unknown'}`.")
    if provider == "mock":
        st.warning("These results come from the mock model. They test the harness only and "
                   "are not a measure of a real model.")

    overall = overall.set_index("mode")
    modes = [m for m in MODES if m in overall.index]
    rows = []
    for key, label in RATE_METRICS:
        row = {"Metric": label}
        for mode in modes:
            row[mode] = _format(key, overall.loc[mode, key]) if key in overall.columns else "n/a"
        rows.append(row)
    st.table(pd.DataFrame(rows).set_index("Metric"))

    st.subheader("Security and task rates")
    rates = pd.DataFrame({
        "Attack success": overall.loc[modes, "attack_success_rate"] * 100,
        "Leakage": overall.loc[modes, "leakage_rate"] * 100,
        "False positives": overall.loc[modes, "false_positive_rate"] * 100,
        "Completion": overall.loc[modes, "completion_rate"] * 100,
    }).T
    rates.columns = modes
    st.bar_chart(rates)

    st.subheader("Attack success by category (%)")
    attack = by_category[by_category["category"] != "benign"]
    if attack.empty:
        st.info("No attack categories in the results.")
    else:
        pivot = attack.pivot(index="category", columns="mode", values="attack_success_rate") * 100
        pivot = pivot.reindex(columns=[m for m in MODES if m in pivot.columns])
        st.bar_chart(pivot)


# ------------------------------------------------------------------ page

def render_login() -> None:
    st.title("BankGuard security dashboard")
    st.caption("Sign in with a synthetic account to read the security event log.")
    with st.form("dash_login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in", type="primary")
    if submitted:
        error = log_in(username.strip(), password)
        if error:
            st.error(error)
        else:
            st.rerun()


def main() -> None:
    st.set_page_config(page_title="BankGuard dashboard", page_icon="🛡️", layout="wide")
    st.session_state.setdefault("token", None)
    st.session_state.setdefault("username", None)
    if not st.session_state.token:
        render_login()
        return
    st.title("BankGuard security dashboard")
    st.caption(f"Signed in as {st.session_state.username}")
    render_events_panel()
    st.divider()
    render_comparison_panel()


main()
