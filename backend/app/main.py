from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .hub import Hub
from .rules import format_error

ROOT = Path(os.environ.get("QUIETWATER_ROOT", Path(__file__).resolve().parents[2]))
DIST = ROOT / "frontend" / "dist"


class ControlBody(BaseModel):
    action: Literal["play", "pause", "restart", "speed"]
    speed: float | None = None


class ScenarioBody(BaseModel):
    name: str
    seed: int | None = None


class ModeBody(BaseModel):
    mode: Literal["security", "recovery"]
    load_scenario: bool = True


class ActionBody(BaseModel):
    action: Literal["approve", "reject", "watch", "send"]
    operator: str = "Watch officer"
    note: str | None = None


class TwistBody(BaseModel):
    yaml: str | None = None
    rules: dict[str, Any] | None = None
    ops: list[dict[str, Any]] | None = None
    scenario: str | None = None
    seed: int | None = None
    note: str = ""
    title: str = "Twist"
    source: Literal["ui", "preset"] = "ui"


def create_app(root: Path = ROOT, run_loop: bool = True) -> FastAPI:
    hub = Hub(root)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(hub.run()) if run_loop else None
        if not run_loop:
            hub.loop = asyncio.get_running_loop()
        yield
        if task:
            task.cancel()

    app = FastAPI(title="Quietwater", version="1.0.0", lifespan=lifespan)
    app.state.hub = hub
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                       allow_methods=["*"], allow_headers=["*"])

    def bad(exc: Exception) -> HTTPException:
        return HTTPException(status_code=422, detail=format_error(exc))

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        rules = hub.store.rules
        return {"ok": True, "rules_version": hub.store.version, "rules_error": hub.store.error,
                "config_hash": rules.config_hash(), "jurisdiction": rules.jurisdiction,
                "advisor": {"enabled": rules.advisor.enabled, "backend": rules.advisor.backend}}

    @app.get("/api/config")
    def config() -> dict[str, Any]:
        return hub.config_payload()

    @app.get("/api/state")
    def state() -> dict[str, Any]:
        return hub.hello()

    @app.get("/api/rules")
    def rules() -> dict[str, Any]:
        return {"version": hub.store.version, "error": hub.store.error, "data": hub.store.data,
                "text": hub.store.text}

    @app.get("/api/stream")
    async def stream(request: Request) -> StreamingResponse:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=20)
        hub.subscribers.add(queue)

        async def events():
            try:
                yield f"event: hello\ndata: {_json(hub.hello())}\n\n"
                while not await request.is_disconnected():
                    try:
                        yield await asyncio.wait_for(queue.get(), timeout=15)
                    except TimeoutError:
                        yield ": keepalive\n\n"
            finally:
                hub.subscribers.discard(queue)

        return StreamingResponse(events(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.post("/api/sim/control")
    def control(body: ControlBody) -> dict[str, Any]:
        try:
            hub.control(body.action, body.speed)
        except ValueError as exc:
            raise bad(exc) from exc
        return {"running": hub.running, "speed": hub.speed}

    @app.post("/api/sim/scenario")
    def scenario(body: ScenarioBody) -> dict[str, Any]:
        try:
            hub.load_scenario(body.name, body.seed)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        return {"scenario": body.name, "seed": hub.session.seed, "mode": hub.mode}

    @app.post("/api/mode")
    def mode(body: ModeBody) -> dict[str, Any]:
        hub.set_mode(body.mode, body.load_scenario)
        return {"mode": hub.mode, "scenario": hub.session.scenario_name}

    @app.post("/api/handoff/{item_id}")
    def handoff(item_id: str, body: ActionBody) -> dict[str, Any]:
        try:
            item = hub.act(item_id, body.action, body.operator, body.note)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return item.to_dict(hub.session.t)

    @app.get("/api/receipts")
    def receipts(limit: int = 500, contact_id: str | None = None) -> list[dict[str, Any]]:
        rows = [r for r in hub.receipts if contact_id is None or r["contact_id"] == contact_id]
        return rows[-limit:]

    @app.get("/api/audit/export")
    def export(format: Literal["json", "csv"] = "json") -> Response:
        body, media = hub.export(format)
        name = f"quietwater-audit.{format}"
        return Response(body, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @app.get("/api/twist/presets")
    def presets() -> list[dict[str, Any]]:
        return hub.world.presets

    @app.get("/api/twist/history")
    def history() -> list[dict[str, Any]]:
        return hub.history.public()

    @app.post("/api/twist/preview")
    async def twist_preview(body: TwistBody) -> dict[str, Any]:
        try:
            data, _ = hub.candidate(body.model_dump())
            result = await run_in_threadpool(hub.preview, data, body.scenario, body.seed)
        except Exception as exc:
            raise bad(exc) from exc
        return {**result, "candidate": data}

    @app.post("/api/twist/apply")
    async def twist_apply(body: TwistBody) -> dict[str, Any]:
        try:
            data, text = hub.candidate(body.model_dump())
            result = await run_in_threadpool(hub.preview, data, body.scenario, body.seed)
        except Exception as exc:
            raise bad(exc) from exc
        entry = hub.apply(data, text, body.note, body.title, body.source, result["impact"])
        return {k: v for k, v in entry.items() if k != "before_text"}

    @app.post("/api/twist/revert/{entry_id}")
    async def twist_revert(entry_id: str) -> dict[str, Any]:
        try:
            entry = await run_in_threadpool(hub.revert, entry_id, "operator")
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except Exception as exc:
            raise bad(exc) from exc
        return {k: v for k, v in entry.items() if k != "before_text"}

    if DIST.exists() and root == ROOT:
        app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> Response:
            file = DIST / path
            if path and file.is_file() and DIST in file.resolve().parents:
                return FileResponse(file)
            return FileResponse(DIST / "index.html")

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    return app


def _json(payload: Any) -> str:
    return json.dumps(payload, separators=(",", ":"))


app = create_app()
