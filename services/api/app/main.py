"""Minimal HTTP API for the Eye Tracker service."""

from fastapi import FastAPI
from pydantic import BaseModel

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
        capabilities=Capabilities(session_upload=False, gaze_processing=False),
    )
