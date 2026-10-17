# Quietwater Tech Stack

A simple overview of what Quietwater is built with.

## At a glance

| Part | Technology |
| --- | --- |
| Backend | Python 3.11+, FastAPI, Uvicorn |
| Frontend | React 18, TypeScript, Vite |
| Live updates | Server-Sent Events (SSE) |
| Config | YAML files (hot-reloaded) |
| Storage | Files only (no database) |
| Packaging | Make, Docker |

## Backend

Python serves the API and runs the decision logic.

- **FastAPI** is the web framework.
- **Uvicorn** is the server that runs it.
- **Pydantic** checks that data has the right shape.
- **ruamel.yaml** reads and writes the YAML rules, so the Twist Console can edit them.
- **pytest** and **httpx** run the tests, and **ruff** lints the code.

What the backend does:

1. **Simulator** makes fake sonar contacts (detection is mocked).
2. **Classifier** labels each contact.
3. **Facts** work out distance, zone, closest approach, trend and more.
4. **Rules engine** picks a response on the ladder: watch, ask, slow, hold, hand to a person. It also writes the reason.
5. **Advisor** looks only at unclear cases. It can raise a response or ask for another look, but it never lowers one. It is rule-based by default, with an optional LLM mode that calls Anthropic's API.
6. **Hub** keeps the receipts, the hand-off queue and the audit log.

## Frontend

A single-page app that shows the harbor to the watch officer.

- **React** builds the screens.
- **TypeScript** adds type safety.
- **Vite** is the dev server and build tool.
- **Plain CSS** handles styling. There is no UI framework.
- The sonar radar is custom-built, with no chart library.

Main screens:

- **Sonar radar** shows the contacts.
- **Alert Budget** counts what needs you and what was handled quietly.
- **Hand-off sheet** is where a person approves, rejects or keeps watching.
- **Decision receipts** show why each decision was made.
- **Twist Console** lets you change the rules live.

## How the two talk

- The UI sends actions (approve, pause, change rules) to the API with normal HTTP requests.
- The backend pushes every update to the UI over one SSE stream (`/api/stream`).
- In development, Vite proxies `/api` to the backend.
- In production, FastAPI also serves the built UI, so everything runs as one process.

## Config and data

- `config/rules.yaml` holds the decision thresholds and rungs.
- `config/harbor.yaml`, `scenarios.yaml` and `twist_presets.yaml` describe the harbor, test scenarios and rule presets.
- Rule changes reload without a restart.
- The audit log exports as JSON or CSV.

## Running it

- `make dev` runs the backend and frontend together for development.
- `make test` runs the backend tests, ruff and the TypeScript check.
- `make start` builds the UI and serves everything on port 8000.
- `docker compose up` runs it in one container.
