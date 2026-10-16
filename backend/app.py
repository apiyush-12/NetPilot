"""FastAPI browser-facing NetPilot control service (loopback only)."""

from __future__ import annotations

import asyncio
import hmac
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security.api_key import APIKeyHeader

from backend.cloud import cloud_events, cloud_status
from backend.core import (AUDIT, EVENTS, LOG_DIR, ControlError, Lab, ProcessSupervisor,
                          append_audit, incident_summary, recent_jsonl)

lab = Lab()
supervisor = ProcessSupervisor()
api_key = APIKeyHeader(name="X-NetPilot-Token", auto_error=False)


def require_token(token: str | None = Security(api_key)) -> None:
    required = os.environ.get("NETPILOT_CONTROL_TOKEN", "")
    if not required or not token or not hmac.compare_digest(token, required):
        raise HTTPException(status_code=403, detail="Valid local control token required")


def run_audited(action: str, target: str, fn):
    try:
        result = fn()
        append_audit(action, target, "SUCCESS")
        return {"ok": True, "action": action, "target": target, "detail": result}
    except ControlError as error:
        append_audit(action, target, "ERROR", str(error))
        raise HTTPException(status_code=409, detail=str(error)) from error


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    supervisor.close()


app = FastAPI(title="NetPilot Control API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware,
                   allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_credentials=False,
                   allow_methods=["GET", "POST"],
                   allow_headers=["X-NetPilot-Token", "Content-Type"])


@app.get("/api/health")
def health():
    return {"service": "netpilot-control", "healthy": True, "scope": "local-only"}


@app.get("/api/status")
def network_status():
    return lab.status(supervisor.status())


@app.get("/api/cloud/status")
def get_cloud_status():
    return cloud_status()


@app.get("/api/cloud/events")
def get_cloud_events(limit: int = Query(50, ge=1, le=100),
                     cursor: str | None = Query(None, max_length=2048)):
    try:
        return cloud_events(limit=limit, cursor=cursor)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except (RuntimeError, KeyError, TypeError) as error:
        raise HTTPException(status_code=502, detail=f"AWS event query failed: {error}") from error


@app.get("/api/logs/{name}")
def console_logs(name: Literal["controller", "forwarder"],
                 limit: int = Query(100, ge=1, le=500)):
    from collections import deque
    path = LOG_DIR / f"{name}_console.log"
    if not path.exists():
        return {"lines": []}
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return {"lines": list(deque((line.rstrip("\r\n") for line in handle), maxlen=limit))}


@app.get("/api/events")
def get_events(limit: int = Query(100, ge=1, le=1000),
               event_type: str | None = None, incident_id: str | None = None):
    return {"items": recent_jsonl(EVENTS, limit, event_type, incident_id)}


@app.get("/api/incidents")
def get_incidents(limit: int = Query(50, ge=1, le=200)):
    return {"items": incident_summary(limit)}


@app.get("/api/audit")
def get_audit(limit: int = Query(50, ge=1, le=200)):
    return {"items": recent_jsonl(AUDIT, limit)}


@app.get("/api/events/stream")
async def event_stream(request: Request):
    async def generator():
        offset = EVENTS.stat().st_size if EVENTS.exists() else 0
        last_heartbeat = time.monotonic()
        while not await request.is_disconnected():
            if EVENTS.exists():
                if EVENTS.stat().st_size < offset:
                    offset = 0
                with EVENTS.open("rb") as handle:
                    handle.seek(offset)
                    while True:
                        raw = handle.readline()
                        if not raw or not raw.endswith(b"\n"):
                            break
                        offset = handle.tell()
                        try:
                            obj = json.loads(raw)
                            if isinstance(obj, dict):
                                yield "event: log\ndata: " + json.dumps(obj) + "\n\n"
                        except (UnicodeDecodeError, json.JSONDecodeError):
                            continue
            if time.monotonic() - last_heartbeat > 15:
                yield ": heartbeat\n\n"
                last_heartbeat = time.monotonic()
            await asyncio.sleep(1)
    return StreamingResponse(generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/services/{service}/{action}", dependencies=[Depends(require_token)])
def change_service(service: Literal["client", "server", "router-a", "router-b"],
                   action: Literal["start", "stop", "restart"]):
    return run_audited(action, service, lambda: lab.service_action(service, action))


@app.post("/api/lab/{action}", dependencies=[Depends(require_token)])
def change_lab(action: Literal["start", "stop"]):
    if action == "stop" and supervisor.running("controller"):
        raise HTTPException(409, "Stop the controller before stopping the whole lab")
    return run_audited(action, "lab", lambda: lab.lab_action(action))


@app.post("/api/routes/reset-primary", dependencies=[Depends(require_token)])
def reset_primary():
    if supervisor.running("controller"):
        raise HTTPException(409, "Stop the controller before changing routes manually")
    return run_audited("reset-primary", "routes", lab.reset_primary_routes)


@app.post("/api/processes/{name}/{action}", dependencies=[Depends(require_token)])
def change_process(name: Literal["controller", "forwarder"],
                   action: Literal["start", "stop"]):
    if action == "start":
        return run_audited("start", name, lambda: {"pid": supervisor.start(name)})
    return run_audited("stop", name, lambda: supervisor.stop(name))
