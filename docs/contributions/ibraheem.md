DRAFT: to be reviewed by Ibraheem

Ibraheem built the walking skeleton recorded in `04cfe5e`: `CONTRACT.md`, `app/models.py`, `app/db.py`, `app/seed.py`, `app/gateway.py`, `app/auth.py`, `app/main.py`, `app/retrieval.py`, `app/chatbot.py`, `app/bank_api.py`, `app/audit.py`, the ten synthetic FAQ documents, `tests/test_smoke.py`, and `tests/test_mock_intents.py`. Later commits added LangChain tool-calling, the deterministic vulnerable mock, audit stamping, HTTP chat tests, I3 bug reports, `README.md`, `docs/architecture.md`, `scripts/make_submission.sh`, and the final session-history implementation in `app/gateway.py`.

The main challenge was keeping one contract-compatible pipeline for baseline, detector_only and full while leaving security plug-in points for Muzammil and an audit trail for evaluation. The smoke tests cover login, all three modes over gateway and HTTP, baseline injection, cross-account denial, canary placement, and the new session-history guarantees.

Outside his owned area, the skeleton commit created placeholder files under `app/security/`, `eval/` and `ui/`. Ibraheem later changed `eval/results/` in `1c404c3` and `cfc4ebf`, and the final result commit changed `eval/results/` again. These changes are stated plainly; the history does not show him changing `ui/` after the skeleton.
