PY ?= $(shell command -v python3.11 || command -v python3.12 || command -v python3.13 || command -v python3)
VENV := backend/.venv
BIN := $(VENV)/bin
API_PORT ?= 8000
UI_PORT ?= 5173

.PHONY: dev install build test lint start docker clean

dev: install
	@echo "Quietwater: UI http://127.0.0.1:$(UI_PORT)  API http://127.0.0.1:$(API_PORT)"
	@trap 'kill 0' INT TERM EXIT; \
	(cd backend && .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port $(API_PORT) --reload --reload-dir app) & \
	(cd frontend && QUIETWATER_API=http://127.0.0.1:$(API_PORT) npm run dev -- --port $(UI_PORT) --strictPort) & \
	wait

install: $(VENV)/.installed frontend/node_modules/.installed

$(VENV)/.installed: backend/requirements.txt backend/requirements-dev.txt
	@$(PY) -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else "Python 3.11+ is required (set PY=/path/to/python3.11)")'
	$(PY) -m venv $(VENV)
	$(BIN)/pip install -q --upgrade pip
	$(BIN)/pip install -q -r backend/requirements-dev.txt
	@touch $@

frontend/node_modules/.installed: frontend/package.json
	cd frontend && npm install --no-audit --no-fund
	@touch $@

build: install
	cd frontend && npm run build
	$(BIN)/python -m compileall -q backend/app

test: install
	cd backend && .venv/bin/pytest -q
	cd backend && .venv/bin/ruff check .
	cd frontend && npm run typecheck

lint: install
	cd backend && .venv/bin/ruff check . && .venv/bin/ruff format --check .

start: build
	@echo "Quietwater (production build): http://127.0.0.1:$(API_PORT)"
	cd backend && .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port $(API_PORT)

docker:
	docker compose up --build

clean:
	rm -rf $(VENV) frontend/node_modules frontend/dist backend/.pytest_cache backend/.ruff_cache
