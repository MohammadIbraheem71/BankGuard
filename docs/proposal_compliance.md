# Proposal compliance note

Owner: Ibraheem. No proposal document or marking rubric is tracked in this
repository, so exact external wording cannot be verified here. This note maps
the repository to the milestone language recorded in `CONTRACT.md`, git history
and the final documentation.

| Milestone / requirement | Repository evidence | Verdict |
|---|---|---|
| Three comparable modes: baseline, detector_only, full | `CONTRACT.md:5-8`, `app/config.py:Mode`, `app/gateway.py` | Verified in code and tests |
| Synthetic banking data only | `app/seed.py`, `data/docs/`, `README.md` | Verified |
| M1 detector and tool policy | `app/security/detector.py`, `app/security/policy.py`, `tests/security/` | Verified; M3 counts reproduced offline |
| M2 confirmation, response guard, events | `app/security/confirmation.py`, `response_guard.py`, `events.py`, `tests/security/` | Verified; live mock confirmation and event flow exercised |
| M3 defensive controls and repeatable measurements | `docs/security_notes.md`, `tests/security/test_m3_controls.py` | Counts reproduced; timings are machine-specific |
| Eval with dev and held-out splits, criteria locked | `eval/cases/`, `eval/metrics.py`, `docs/eval_criteria_changes.md` | Verified; held-out validation is explicitly not blind |
| FastAPI HTTP surface and Streamlit demo/dashboard | `app/main.py`, `ui/streamlit_app.py`, `ui/dashboard.py`, `ui/ui_check.md` | Verified headless API/UI health and scripted mock flows |
| Temperature 0 | `app/config.py:32` | Verified in code |
| Reproducible final results | `eval/results/final_raw/manifest.json`, `eval/check_results.py` | Verified by offline re-score |

Residual unverified item: the exact external proposal/rubric wording was not
available in the audit scope.
