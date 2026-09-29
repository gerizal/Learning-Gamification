"""FastAPI app — pages + routers per CONTRACT.md.

The MVP is a multiple-choice quiz (live PIN game, homework, one-screen classroom) plus read-only reports.
The individual speaking practice (/practice), the admin page and their APIs were removed (owner, 2026-09-28).
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import db

log = logging.getLogger("playclass")

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static"


# --------------------------------------------------------------------------- app

@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.get_pool()
    yield
    db.close_pool()


app = FastAPI(title="PlayClass", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def _validation_handler(_request, exc: RequestValidationError):
    """Contract: errors are {"detail": "<string>"}; also keep the structured list under "errors"."""
    parts = []
    for e in exc.errors():
        loc = ".".join(str(x) for x in e.get("loc", ()) if x not in ("body", "query", "path", "form"))
        msg = str(e.get("msg", "invalid")).removeprefix("Value error, ")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return JSONResponse(status_code=422, content={"detail": "; ".join(parts) or "Invalid request",
                                                  "errors": jsonable_encoder(exc.errors())})


app.mount("/static", StaticFiles(directory=str(STATIC_DIR), check_dir=False), name="static")


def _page(name: str) -> FileResponse:
    path = STATIC_DIR / name
    if not path.is_file():
        raise HTTPException(404, f"static/{name} not found")
    return FileResponse(path)


@app.get("/", include_in_schema=False)
def index_page():
    return _page("home.html")  # Teacher / Student entry


@app.get("/host", include_in_schema=False)
def host_page():
    return _page("host.html")


@app.get("/play", include_in_schema=False)
def play_page():
    return _page("play.html")


@app.get("/classroom", include_in_schema=False)
def classroom_page():
    return _page("classroom.html")


@app.get("/reports", include_in_schema=False)
def reports_page():
    return _page("reports.html")


@app.get("/api/health")
def health():
    return {"ok": True, "db": db.ping()}


# --------------------------------------------------------------------------- routers
from . import classroom  # noqa: E402  (one-screen classroom quiz, /api/class)
from . import live  # noqa: E402  (live PIN game + homework, /api/live)
from . import quiz  # noqa: E402  (teacher-owned quizzes, /api/live/quizzes)
from . import reports  # noqa: E402  (read-only reporting router, X-Reports-Key)

app.include_router(classroom.router)
app.include_router(live.router)
app.include_router(quiz.router)
app.include_router(reports.status_router)
app.include_router(reports.router)
