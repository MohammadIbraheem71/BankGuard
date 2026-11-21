# BankGuard — Agent Instructions

## Project summary
BankGuard is a university Information Security term project: a prototype security gateway for an AI banking chatbot. It is a Python 3.11+ / FastAPI / SQLite / Streamlit / LangChain skeleton that compares three modes — `baseline` (LLM plus tools, no security checks), `detector_only` (inspect the user message) and `full` (detector on user and documents, policy on every tool call, transfer confirmation, response guard and event logging). All people, accounts, transactions and documents are synthetic. Every user-facing path goes through `gateway.handle_message`, and every executed tool call is written to `audit_log` as eval ground truth.

## Source of truth
CONTRACT.md is the source of truth, never change a signature without editing CONTRACT.md and telling the team

## Ownership
| Owner | Files |
| --- | --- |
| Ibraheem | app/*.py (except security/), data/, docs/architecture.md, README, tests/test_smoke.py |
| Muzammil | app/security/*, tests/security/* |
| Anum | eval/*, ui/*, docs/security_analysis.md |

never edit files you don't own

## Rules
- run pytest before every commit
- never commit secrets, .env or .db files
- never claim something works without running it and showing the output
- only Anum may read eval/cases/heldout.jsonl before code freeze; all other people and agents must not open it or tune anything against it
- use temperature 0 for the LLM
