# Evaluation timeline

This document records only facts available from git history and commit messages.

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
| 2026-11-26 | `374c094c0105c00bac826d74d348b2256f5bb02e` | Final dev and held-out runs for this submission were executed from this `ibraheem/final` commit. |
| 2026-11-26 | `e88c974e3b5dee4757b77e5eeff23cab405a9677` | That phase-1 tree was merged into `main` and tagged `code-freeze`. |

The held-out split was therefore evaluated twice: once on code at `9f05fbd`, before the M3 security commits listed above, and once on the frozen code at `code-freeze`. The second evaluation is not fully blind.
