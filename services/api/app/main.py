"""Minimal HTTP API for the Eye Tracker service."""

import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.experiments import router as experiments_router
from app.sessions import router as sessions_router

SERVICE_NAME = "eye-tracker-api"
VERSION = "0.1.0"


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class Capabilities(BaseModel):
    session_upload: bool
    gaze_processing: bool


class InfoResponse(BaseModel):
    name: str
    version: str
    description: str
    capabilities: Capabilities


app = FastAPI(
    title="Eye Tracker API",
    version=VERSION,
    docs_url="/docs",
    openapi_url="/openapi.json",
)


@app.middleware("http")
async def limit_upload(request: Request, call_next):
    if request.method == "PUT" and (request.url.path.endswith("/stimulus") or request.url.path.startswith("/api/sessions/") and request.url.path.endswith("/files")):
        directory = Path(os.environ.get("EYE_TRACKER_DATA_DIR", "./data")) / "tmp"
        directory.mkdir(parents=True, exist_ok=True)
        tempfile.tempdir = str(directory)
        length = request.headers.get("content-length")
        if length is None:
            return JSONResponse(status_code=411, content={"detail": "Informe o tamanho do envio."})
        try:
            if int(length) < 0 or int(length) > (506 if request.url.path.endswith("/files") else 101) * 1024 * 1024:
                return JSONResponse(status_code=413, content={"detail": "O envio excede o limite permitido."})
        except ValueError:
            return JSONResponse(status_code=400, content={"detail": "Tamanho inválido."})
    return await call_next(request)


app.include_router(experiments_router)
app.include_router(sessions_router)


@app.get("/api/health", response_model=HealthResponse, tags=["service"])
def health() -> HealthResponse:
    """Report that this API process is available."""
    return HealthResponse(status="ok", service=SERVICE_NAME, version=VERSION)


@app.get("/api/info", response_model=InfoResponse, tags=["service"])
def info() -> InfoResponse:
    """Describe the service without implying unimplemented capabilities."""
    return InfoResponse(
        name="Eye Tracker",
        version=VERSION,
        description="Base de coleta e processamento de olhar.",
        capabilities=Capabilities(session_upload=True, gaze_processing=False),
    )
