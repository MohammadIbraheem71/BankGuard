# Evaluation timeline

This document records only facts available from git history, commit messages, and raw run metadata.

| Date | Commit | Fact |
|---|---|---|
| 2026-11-23 | `9f05fbd` | Commit "Audit benign transfer source accounts; record rule C-R2". The later `3430e61` commit message states that the earlier held-out run used `9f05fbd`. |
| 2026-11-23 | `912eaf9` | M1 detector and tool policy implemented. |
| 2026-11-23 | `6669e35` | M2 confirmation, response guard and security events implemented. |
| 2026-11-23 | `c143c67` | Transfer confirmation made atomic with banking and audit writes. |
| 2026-11-25 | `b66adf0` | M3 defensive controls frozen and repeatable detector measurements recorded. |
| 2026-11-25 | `d645f93` | Safe event identifiers restored and customer ownership respected in full mode. |
| 2026-11-25 | `cde2fd9` | M3 control measurements, latency and remaining limitations documented. |
| 2026-11-26 | `3430e61` | Held-out result tables, charts and `docs/security_analysis.md` first appeared on `main`; `git merge-base --is-ancestor 3430e61 main` exits 0. |
| 2026-11-26 | `48ecabd` | Commit "Freeze held-out case set: commit eval/cases/heldout.jsonl"; `git merge-base --is-ancestor 48ecabd main` exits 0. |
| 2026-11-26 | `374c094c0105c00bac826d74d348b2256f5bb02e` | First dev and held-out runs for the original frozen submission, executed from this `ibraheem/final` commit. Superseded by the rebaseline below. |
| 2026-11-26 | `e88c974e3b5dee4757b77e5eeff23cab405a9677` | That phase-1 tree was merged into `main` and tagged `code-freeze`. |
| 2026-11-27 | `8c79b9b2391c7937d1c425090cfec1b08218424d` | `eval/check_results.py --strict` was extended to detect stale code provenance. The current real-model dev and held-out rebaseline was then executed from this commit; raw metadata records `git_commit` and `git_tree` directly. |

The held-out split has therefore been evaluated three times: once on code at `9f05fbd`, before the M3 security commits listed above; once on the frozen code at `code-freeze`; and once post-freeze at `8c79b9b`. The first and second evaluations are not fully blind. The third is a rebaseline of the same locked case set and judging criteria after post-freeze application changes, not a new blind split. It is the run reported by the committed tables.

The current raw files record commit `8c79b9b2391c7937d1c425090cfec1b08218424d` and tree `7548c7f8f29b2a4aa01c964eac199b4da870687c` directly. `eval/results/final_raw/manifest.json` records their hashes, table hashes and model settings. `python eval/check_results.py --strict` now fails if behavior-relevant files (`app/`, `eval/*.py`, `eval/cases/`, `scripts/`, `requirements.txt`, `CONTRACT.md`) change after that recorded commit or are left uncommitted. Result files and documentation may be updated after an eval commit without invalidating the run.
