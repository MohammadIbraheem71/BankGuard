# BankGuard

BankGuard is a university Information Security term project: a prototype security gateway for a synthetic AI banking chatbot. It compares three runtime modes — `baseline`, `detector_only`, and `full` — around the same FastAPI + LangChain/Mock + SQLite pipeline.

All users, accounts, transactions, and FAQ documents are synthetic. Chat requests go through `app.gateway.handle_message`; executed tool calls are recorded in `audit_log`.

## Setup

Requirements: Python 3.11+ (repo tested in a local `.venv`), SQLite, and the packages in `requirements.txt`.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

`.env.example` includes:

```env
LLM_PROVIDER=mock
LLM_MODEL=mock-chat
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GOOGLE_API_KEY=
GROQ_API_KEY=
OLLAMA_BASE_URL=http://localhost:11434
DB_PATH=data/bankguard.db
SECRET_KEY=replace-with-a-long-random-secret
```

Notes verified in code:
- `LLM_PROVIDER` defaults to `mock`; `LLM_MODEL` defaults to `mock-chat`.
- `llm_temperature` is fixed to `0.0` in `app/config.py` and is not read from `.env`.
- `DB_PATH` defaults to `data/bankguard.db` and is resolved relative to the repo root when relative.
- `SECRET_KEY` is used by auth tokens and transfer confirmation binding hashes.

## Seed / initialize the database

The API initializes the schema on startup (`db.init_db()` in FastAPI lifespan). To fully reset and reseed synthetic data:

```bash
.venv/bin/python -c "from app.db import reset_and_seed; reset_and_seed(); print('seeded')"
```

Seeded demo users (synthetic): `alice/alice123`, `bob/bob123`.

## Run the API

```bash
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Main endpoints:
- `POST /login` — `{username,password}` -> `{token}`
- `GET /me` — bearer auth -> `User`
- `POST /chat?mode=baseline|detector_only|full` — bearer auth, `ChatRequest` -> `ChatResponse`
- `POST /transfers/{id}/confirm` — bearer auth -> `ToolResult`
- `POST /transfers/{id}/cancel` — bearer auth -> `ToolResult`
- `GET /events?mode=&limit=` — bearer auth -> `list[SecurityEvent]`

## Run the Streamlit apps

Chat UI:

```bash
.venv/bin/streamlit run ui/streamlit_app.py
```

Security dashboard:

```bash
.venv/bin/streamlit run ui/dashboard.py
```

The UI files live in `ui/`; check `ui/ui_check.md` and the UI code for any UI-specific environment assumptions before demoing.

## Run tests

```bash
LLM_PROVIDER=mock .venv/bin/pytest -o addopts= -q
```

`pytest.ini` sets `pythonpath = .` and `testpaths = tests`.

## Run evaluation (dev only)

Evaluation runs cases through `gateway.handle_message` directly (no HTTP). Use the dev split only; held-out evaluation is run by Anum at freeze.

```bash
.venv/bin/python -m eval.run_eval --split dev --modes baseline,detector_only,full
.venv/bin/python -m eval.metrics eval/results/raw/<run-file>.json --out-dir eval/results/real
```

Useful flags from `eval/run_eval.py`: `--split {dev,heldout,both}`, `--modes`, `--repeat`, `--out`, `--limit`, `--allow-heldout`. Do not use `--split heldout` or `--split both` before code freeze; `--allow-heldout` is restricted by project rules to Anum.

## Modes

- **baseline**: Retrieves FAQ docs and runs the agent with tool execution. No user/doc detector, no policy authorization, no transfer confirmation gate, no response guard, and no security event logging.
- **detector_only**: Same as baseline plus user-message inspection before agent execution. A flagged user message returns a blocked response; it does not apply document inspection, policy, confirmation, response guard, or security event logging.
- **full**: Adds user and retrieved-document inspection, policy checks on every tool call, transfer pending/confirmation instead of immediate transfer execution, response guard on the final reply, and security event logging.

## Results

- Raw eval runs: `eval/results/raw/` (gitignored).
- Metrics outputs: `eval/results/mock/` and `eval/results/real/` (CSV/markdown summaries; charts may also be present locally).
- Dashboard/UI may read from these result folders.

## Final results

<!-- FINAL RESULTS PLACEHOLDER: replace this section with the final dev/held-out table at freeze. -->
| Mode | Split | Attack success | Unauthorized executions | Leakage | False positives | Completion | Notes |
|---|---|---:|---:|---:|---:|---:|---|
| baseline | dev | TBD | TBD | TBD | TBD | TBD | Pending final run |
| detector_only | dev | TBD | TBD | TBD | TBD | TBD | Pending final run |
| full | dev | TBD | TBD | TBD | TBD | TBD | Pending final run |

## Repo layout

```text
.
├── app/                    # FastAPI app, gateway, agent, db, auth, audit, retrieval, security
├── data/
│   └── docs/               # Synthetic FAQ markdown corpus
├── docs/                   # Architecture and project docs
├── eval/                   # Eval runner, metrics, cases, tests, results
├── scripts/                # Submission/build scripts
├── tests/                  # Pytest smoke + security + mock intent tests
├── ui/                     # Streamlit chat and dashboard
├── .env.example
├── AGENTS.md
├── CONTRACT.md
├── pytest.ini
├── README.md
└── requirements.txt
```

## Security/scope notes

- Do not commit `.env`, `*.db`, `.venv`, or `__pycache__`.
- `eval/cases/heldout.jsonl` must not be read/tuned against before code freeze except by Anum, per project rules.
- See `docs/architecture.md` for verified pipeline, trust boundaries, confirmation flow, and simplifications.
