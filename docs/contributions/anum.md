DRAFT: to be reviewed by Anum

Anum built the evaluation and UI layer shown in git history. She added `eval/cases/dev.jsonl`, `eval/validate_cases.py`, `eval/run_eval.py`, `eval/metrics.py`, `eval/tests/test_metrics.py` and `eval/tests/test_validate_cases.py`. Commit `48ecabd` committed the held-out case set. She added the Streamlit chat UI (`ui/api.py`, `ui/streamlit_app.py`), the security dashboard (`ui/dashboard.py`) and `ui/ui_check.md`. She also wrote `docs/eval_criteria_changes.md`, `docs/security_analysis.md`, `eval/make_real_charts.py`, and the mock/real/held-out result tables and charts.

The main challenge was defining and locking judging criteria while keeping mock, real and held-out result sets separate, then exposing those sets in the dashboard. Commit `a23427a` recorded criteria v2, including the FAQ benign rule, case-insensitive substring checks and the mock label. The case validator checks schema, category minimums and canary/ownership consistency; the metrics module computes attack success, unauthorized executions, leakage, false positives, completion, latency and overhead.

Outside her main `eval/` and `ui/` areas, she changed `docs/eval_criteria_changes.md` and `docs/security_analysis.md` (her assigned docs) and changed `.gitignore` in the held-out freeze commit. The history does not show her changing `app/` or `app/security/`.
