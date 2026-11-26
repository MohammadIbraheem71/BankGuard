# BankGuard

BankGuard is a university Information Security term project: a prototype security gateway for a synthetic AI banking chatbot. It compares three runtime modes — `baseline`, `detector_only`, and `full` — around the same FastAPI + LangChain/Mock + SQLite pipeline.

All users, accounts, transactions, and FAQ documents are synthetic. Chat requests go through `app.gateway.handle_message`; executed tool calls are recorded in `audit_log`.

## Setup

Requirements: Python 3.11+ (the cleanroom check used Python 3.14.4), SQLite, and the packages in `requirements.txt`. `requirements.lock.txt` records the exact versions installed in that verified cleanroom; CI uses the same Python version.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -c requirements.lock.txt
cp .env.example .env
```

Replace `SECRET_KEY` in `.env` with a long random value. For a non-demo startup,
set `BANKGUARD_REQUIRE_SECRET=1` so the default fallback secret is refused.

Before committing, run `bash scripts/pre_commit_check.sh`; CI runs the same offline mock pytest.

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
BANKGUARD_REQUIRE_SECRET=0
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

## Run evaluation

Evaluation runs cases through `gateway.handle_message` directly (no HTTP). Always set `LLM_PROVIDER` explicitly: a mock run must never be scored into `eval/results/real/`.

Mock harness check (writes only to `eval/results/mock/`):

```bash
LLM_PROVIDER=mock LLM_MODEL=mock-chat .venv/bin/python -m eval.run_eval \
  --split dev --modes baseline,detector_only,full \
  --out eval/results/raw/dev-mock.json
.venv/bin/python -m eval.metrics eval/results/raw/dev-mock.json \
  --out-dir eval/results/mock
```

Real-model dev evaluation (uses provider/model from `.env` for chat, with the provider made explicit here):

```bash
LLM_PROVIDER=openai .venv/bin/python -m eval.run_eval \
  --split dev --modes baseline,detector_only,full \
  --out eval/results/raw/dev-real.json
.venv/bin/python -m eval.metrics eval/results/raw/dev-real.json \
  --out-dir eval/results/real
```

Final post-development held-out-style validation requires the tracked case file and the explicit guard flag; it is only run at/after code freeze:

```bash
LLM_PROVIDER=openai .venv/bin/python -m eval.run_eval \
  --split heldout --allow-heldout --modes baseline,detector_only,full \
  --out eval/results/raw/heldout-real.json
.venv/bin/python -m eval.metrics eval/results/raw/heldout-real.json \
  --out-dir eval/results/heldout
```

Useful flags from `eval/run_eval.py`: `--split {dev,heldout,both}`, `--modes`, `--repeat`, `--out`, `--limit`, `--allow-heldout`. Do not tune anything against the held-out split after reading its results. The second run is post-development validation, not a blind first look: the same cases were run earlier on pre-M3 code, and the code changed between runs.

## Modes

- **baseline**: Retrieves FAQ docs and runs the agent with tool execution. No user/doc detector, no policy authorization, no transfer confirmation gate, no response guard, and no security event logging.
- **detector_only**: Same as baseline plus user-message inspection before agent execution. A flagged user message returns a blocked response; it does not apply document inspection, policy, confirmation, response guard, or security event logging.
- **full**: Adds user and retrieved-document inspection, policy checks on every tool call, transfer pending/confirmation instead of immediate transfer execution, response guard on the final reply, and security event logging.

## Results

- `eval/results/raw/`: raw JSON runs, gitignored because they include case text. Scratch runs only.
- `eval/results/final_raw/`: committed raw JSON files for the two final runs (dev and held-out), kept for provenance. `manifest.json` records their hashes, inferred code commit/tree and model settings.
- `eval/results/mock/`: derived CSV, markdown and charts from mock harness runs; not comparable to real-model results.
- `eval/results/real/`: derived CSV, markdown and charts from the final real-model dev run.
- `eval/results/heldout/`: derived CSV, markdown and charts from the real-model held-out run.
- The dashboard can read from the `mock`, `real` and `heldout` result sets.

## Final results

<!-- BEGIN FINAL RESULTS -->
Model: `gpt-4o-mini`; temperature: `0.0`. Rate denominators: attack success and unauthorized executions use attack runs, leakage uses leak-eligible runs, false positives and completion use benign runs.

| Mode | Split | Attack success | Unauthorized executions | Leakage | False positives | Completion | Mean latency (ms) | p95 latency (ms) |
|---|---|---|---|---|---|---|---:|---:|
| baseline | dev | 15.0% (6/40) | 6 (6/40) | 0.0% (0/18) | 0.0% (0/20) | 100.0% (20/20) | 3096.4 | 9195.3 |
| detector_only | dev | 10.0% (4/40) | 4 (4/40) | 0.0% (0/18) | 0.0% (0/20) | 100.0% (20/20) | 2839.9 | 7957.9 |
| full | dev | 0.0% (0/40) | 0 (0/40) | 0.0% (0/18) | 0.0% (0/20) | 100.0% (20/20) | 2609.2 | 7675.2 |
| baseline | heldout | 10.0% (4/40) | 3 (3/40) | 5.0% (1/20) | 0.0% (0/20) | 100.0% (20/20) | 2743.8 | 7408.6 |
| detector_only | heldout | 7.5% (3/40) | 2 (2/40) | 5.0% (1/20) | 0.0% (0/20) | 100.0% (20/20) | 2555.7 | 6856.9 |
| full | heldout | 0.0% (0/40) | 0 (0/40) | 0.0% (0/20) | 0.0% (0/20) | 100.0% (20/20) | 2612.1 | 7092.8 |
<!-- END FINAL RESULTS -->

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
