"""Receipt of the Android prototype's original files, without implying processing."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.experiments import connect, find, representation

router = APIRouter(prefix="/api", tags=["sessions"])


class SessionInput(BaseModel):
    experiment_id: str
    local_id: str
    participant_code: str = Field(min_length=1, max_length=200)


class SessionView(BaseModel):
    id: str
    experiment_id: str
    local_id: str
    participant_code: str
    receipt_status: str
    processing_status: str


def session_view(row) -> SessionView:
    with connect() as db:
        latest = db.execute("SELECT status FROM processing_runs WHERE session_id=? ORDER BY rowid DESC LIMIT 1", (row["id"],)).fetchone()
    return SessionView(id=row["id"], experiment_id=row["experiment_id"], local_id=row["local_id"],
                       participant_code=row["participant_code"],
                       receipt_status="received" if row["video_hash"] and row["events_hash"] else "pending",
                       processing_status=latest["status"] if latest else "unavailable")


@router.get("/experiments/{experiment_id}/sessions", response_model=list[SessionView])
def list_sessions(experiment_id: str, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    with connect() as db:
        find(db, experiment_id)
        rows = db.execute("SELECT * FROM sessions WHERE experiment_id = ? ORDER BY rowid DESC LIMIT ? OFFSET ?", (experiment_id, limit, offset)).fetchall()
        return [session_view(row) for row in rows]


@router.get("/sessions/{session_id}", response_model=SessionView)
def get_session(session_id: str):
    with connect() as db:
        row = db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Sessão não encontrada.")
        return session_view(row)


def received_file(session_id: str, name: str, hash_column: str) -> Path:
    with connect() as db:
        row = db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Sessão não encontrada.")
        if not row[hash_column]:
            raise HTTPException(409, "Arquivo ainda não recebido.")
        # Use the server-generated ID from the database, never the request as a path.
        path = Path(os.environ.get("EYE_TRACKER_DATA_DIR", "./data")) / "sessions" / row["id"] / name
    if not path.is_file():
        raise HTTPException(404, "Arquivo da sessão indisponível no servidor.")
    return path


@router.get("/sessions/{session_id}/video")
def session_video(session_id: str):
    return FileResponse(received_file(session_id, "face.mp4", "video_hash"), media_type="video/mp4")


@router.get("/sessions/{session_id}/events")
def session_events(session_id: str):
    return FileResponse(received_file(session_id, "sessao.json", "events_hash"), media_type="application/json")


@router.get("/published-experiments/{code}")
def published_experiment(code: str):
    with connect() as db:
        row = db.execute("SELECT * FROM experiments WHERE code = ?", (code.upper(),)).fetchone()
        if not row:
            raise HTTPException(404, "Experimento publicado não encontrado.")
        return representation(row)


@router.post("/sessions")
def create_session(data: SessionInput):
    try:
        local_id = str(UUID(data.local_id))
    except ValueError:
        raise HTTPException(422, "Identificador local inválido.")
    participant = data.participant_code.strip()
    if not participant:
        raise HTTPException(422, "Informe o código do participante.")
    with connect() as db:
        row = find(db, data.experiment_id)
        if not row["code"]:
            raise HTTPException(409, "Experimento não publicado.")
        previous = db.execute("SELECT * FROM sessions WHERE local_id = ?", (local_id,)).fetchone()
        if previous:
            if previous["experiment_id"] != data.experiment_id or previous["participant_code"] != participant:
                raise HTTPException(409, "Identificador local já usado com outros dados.")
            return {"id": previous["id"], "received": previous["video_hash"] is not None}
        session_id = str(uuid4())
        db.execute("INSERT INTO sessions (id, local_id, experiment_id, participant_code) VALUES (?, ?, ?, ?)", (session_id, local_id, data.experiment_id, participant))
        return {"id": session_id, "received": False}


@router.put("/sessions/{session_id}/files")
async def receive_files(session_id: str, video_sha256: str = Form(), events_sha256: str = Form(), video: UploadFile = File(), events: UploadFile = File()):
    for digest in (video_sha256, events_sha256):
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise HTTPException(422, "SHA-256 inválido.")
    with connect() as db:
        row = db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Sessão não encontrada.")
        if row["video_hash"]:
            if (row["video_hash"], row["events_hash"]) != (video_sha256, events_sha256):
                raise HTTPException(409, "Sessão já recebida com outros arquivos.")
            return {"id": session_id, "received": True}
    root = Path(os.environ.get("EYE_TRACKER_DATA_DIR", "./data")) / "sessions"
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root) as temporary:
        directory = Path(temporary)
        for upload, name, expected, limit in ((video, "face.mp4", video_sha256, 500_000_000), (events, "sessao.json", events_sha256, 5_000_000)):
            digest = hashlib.sha256()
            size = 0
            with (directory / name).open("wb") as output:
                while chunk := await upload.read(1024 * 1024):
                    size += len(chunk)
                    if size > limit:
                        raise HTTPException(413, "Arquivo excede o limite permitido.")
                    digest.update(chunk)
                    output.write(chunk)
            if not size or digest.hexdigest() != expected:
                raise HTTPException(422, "Arquivo vazio ou SHA-256 divergente.")
        try:
            probe = subprocess.run(["ffprobe", "-protocol_whitelist", "file,pipe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_type", "-of", "json", str(directory / "face.mp4")], capture_output=True, text=True, timeout=30)
            if probe.returncode != 0 or not json.loads(probe.stdout).get("streams"):
                raise ValueError()
        except (ValueError, subprocess.TimeoutExpired):
            raise HTTPException(422, "Gravação de câmera inválida.")
        try:
            metadata = json.loads((directory / "sessao.json").read_text(encoding="utf-8"))
            if metadata["experimento"] != row["experiment_id"] or metadata["coleta_local"] != row["local_id"] or metadata["estado"] not in ("concluida", "interrompida") or not isinstance(metadata["eventos"], list):
                raise ValueError()
        except (ValueError, KeyError, TypeError, UnicodeError):
            raise HTTPException(422, "Metadados incompatíveis com a sessão.")
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if current["video_hash"]:
                if (current["video_hash"], current["events_hash"]) != (video_sha256, events_sha256):
                    raise HTTPException(409, "Sessão já recebida com outros arquivos.")
            else:
                final = root / session_id
                if final.exists():
                    shutil.rmtree(final)
                os.replace(directory, final)
                db.execute("UPDATE sessions SET video_hash = ?, events_hash = ? WHERE id = ?", (video_sha256, events_sha256, session_id))
    return {"id": session_id, "received": True}
