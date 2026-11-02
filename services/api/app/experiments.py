"""Persistent experiment drafts; publication awaits an approved protocol."""
import hashlib
import json
import secrets
import subprocess
import tempfile
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

router = APIRouter(prefix="/api/experiments", tags=["experiments"])


class DraftInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Informe o nome do experimento.")
        return value


@contextmanager
def connect():
    directory = Path(os.environ.get("EYE_TRACKER_DATA_DIR", "./data"))
    directory.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(directory / "experiments.sqlite3", timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("BEGIN IMMEDIATE")
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version == 0:
        db.execute("""CREATE TABLE IF NOT EXISTS experiments (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL,
            created_at TEXT NOT NULL, idempotency_key TEXT UNIQUE, request_hash TEXT NOT NULL
        )""")
        db.execute("PRAGMA user_version = 1")
    if version < 2:
        for column in ("stimulus TEXT", "protocol TEXT", "code TEXT", "published_at TEXT"):
            db.execute(f"ALTER TABLE experiments ADD COLUMN {column}")
        db.execute("CREATE UNIQUE INDEX experiment_code ON experiments(code)")
        db.execute("PRAGMA user_version = 2")
    db.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, local_id TEXT UNIQUE NOT NULL, experiment_id TEXT NOT NULL, participant_code TEXT NOT NULL, video_hash TEXT, events_hash TEXT)")
    db.commit()
    try:
        with db:
            yield db
    finally:
        db.close()


PROTOCOL = {
    "version": 1, "label": "Android provisório", "coordinates": "fração da largura e altura da área de apresentação; origem no canto superior esquerdo",
    "phases": [
        {"name": "marcador_a", "flashes": 2, "on_ms": 200, "off_ms": 1000, "pause_ms": 2000},
        {"name": "calibracao", "point_ms": 2000, "targets": [[.5,.5],[.1,.1],[.9,.1],[.9,.9],[.1,.9],[.5,.5],[.9,.9],[.1,.1],[.1,.9],[.9,.1]]},
        {"name": "descanso", "duration_ms": 2000}, {"name": "estimulo"},
        {"name": "validacao", "point_ms": 2000, "targets": [[.5,.15],[.85,.5],[.5,.85],[.15,.5],[.65,.65]]},
        {"name": "marcador_b", "flashes": 2, "on_ms": 200, "off_ms": 1000, "pause_ms": 2000},
    ],
}


def representation(row: sqlite3.Row) -> dict:
    stimulus = json.loads(row["stimulus"]) if row["stimulus"] else None
    if stimulus:
        stimulus.pop("path", None)
    return {"id": row["id"], "name": row["name"], "description": row["description"],
            "created_at": row["created_at"], "state": "published" if row["code"] else "draft", "code": row["code"],
            "published_at": row["published_at"], "stimulus": stimulus, "protocol": json.loads(row["protocol"]) if row["protocol"] else None,
            "pending": ([] if stimulus else ["Envie um vídeo válido."]) + ([] if row["protocol"] else ["Selecione o protocolo provisório."])}


def find(db: sqlite3.Connection, experiment_id: str) -> sqlite3.Row:
    row = db.execute("SELECT * FROM experiments WHERE id = ?", (experiment_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Experimento não encontrado.")
    return row


@router.post("", status_code=201)
def create_draft(draft: DraftInput, idempotency_key: str = Header(min_length=1, max_length=200)) -> dict:
    request_hash = hashlib.sha256(json.dumps(draft.model_dump(), sort_keys=True).encode()).hexdigest()
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute("SELECT * FROM experiments WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
        if existing:
            if existing["request_hash"] != request_hash:
                raise HTTPException(status_code=409, detail="Chave de idempotência já usada com outros dados.")
            return representation(existing)
        experiment_id = str(uuid.uuid4())
        db.execute("INSERT INTO experiments (id, name, description, created_at, idempotency_key, request_hash) VALUES (?, ?, ?, ?, ?, ?)",
                   (experiment_id, draft.name, draft.description, datetime.now(timezone.utc).isoformat(), idempotency_key, request_hash))
        return representation(find(db, experiment_id))


@router.get("")
def list_drafts(limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0)) -> dict:
    with connect() as db:
        rows = db.execute("SELECT * FROM experiments ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
        return {"items": [representation(row) for row in rows], "limit": limit, "offset": offset}


@router.get("/{experiment_id}")
def get_draft(experiment_id: str) -> dict:
    with connect() as db:
        return representation(find(db, experiment_id))


@router.patch("/{experiment_id}")
def update_draft(experiment_id: str, draft: DraftInput) -> dict:
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if find(db, experiment_id)["code"]:
            raise HTTPException(status_code=409, detail="Experimento publicado é imutável.")
        db.execute("UPDATE experiments SET name = ?, description = ? WHERE id = ?", (draft.name, draft.description, experiment_id))
        return representation(find(db, experiment_id))


@router.put("/{experiment_id}/protocol")
def set_protocol(experiment_id: str) -> dict:
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if find(db, experiment_id)["code"]:
            raise HTTPException(status_code=409, detail="Experimento publicado é imutável.")
        db.execute("UPDATE experiments SET protocol = ? WHERE id = ?", (json.dumps(PROTOCOL), experiment_id))
        return representation(find(db, experiment_id))


@router.put("/{experiment_id}/stimulus")
async def upload_stimulus(experiment_id: str, file: UploadFile) -> dict:
    with connect() as db:
        if find(db, experiment_id)["code"]:
            raise HTTPException(status_code=409, detail="Experimento publicado é imutável.")
    directory = Path(os.environ.get("EYE_TRACKER_DATA_DIR", "./data")) / "videos"
    directory.mkdir(parents=True, exist_ok=True)
    temporary = None
    final = None
    try:
        digest = hashlib.sha256()
        size = 0
        with tempfile.NamedTemporaryFile(dir=directory, delete=False) as out:
            temporary = Path(out.name)
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > 100_000_000:
                    raise HTTPException(status_code=413, detail="O vídeo deve ter no máximo 100 MB.")
                digest.update(chunk)
                out.write(chunk)
        result = subprocess.run(["ffprobe", "-protocol_whitelist", "file,pipe", "-v", "error", "-show_entries", "format=format_name,duration:stream=codec_type,codec_name,width,height", "-of", "json", str(temporary)], capture_output=True, text=True, timeout=30)
        try:
            metadata = json.loads(result.stdout)
            video = next(stream for stream in metadata["streams"] if stream["codec_type"] == "video")
            duration = float(metadata["format"]["duration"])
            if result.returncode != 0 or "mp4" not in metadata["format"]["format_name"].split(","):
                raise HTTPException(status_code=422, detail="O arquivo não é um MP4 válido.")
            if video["codec_name"] != "h264":
                raise HTTPException(status_code=422, detail="O vídeo precisa usar o codec H.264.")
            if not 0 < duration <= 30:
                raise HTTPException(status_code=422, detail="O vídeo precisa ter duração maior que zero e de até 30 segundos.")
            if video["width"] <= 0 or video["height"] <= 0:
                raise HTTPException(status_code=422, detail="As dimensões do vídeo são inválidas.")
        except (ValueError, KeyError, StopIteration, TypeError):
            raise HTTPException(status_code=422, detail="Não foi possível ler um vídeo MP4 válido no arquivo.")
        final = directory / f"{uuid.uuid4()}.mp4"
        stimulus = {"path": final.name, "name": Path(file.filename or "video.mp4").name, "size": size, "sha256": digest.hexdigest(), "duration": duration, "width": video["width"], "height": video["height"], "container": "mp4", "codec": "h264"}
        old = None
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = find(db, experiment_id)
            if row["code"]:
                raise HTTPException(status_code=409, detail="Experimento publicado é imutável.")
            old = json.loads(row["stimulus"])["path"] if row["stimulus"] else None
            temporary.replace(final)
            db.execute("UPDATE experiments SET stimulus = ? WHERE id = ?", (json.dumps(stimulus), experiment_id))
            response = representation(find(db, experiment_id))
        final = None
        if old:
            (directory / old).unlink(missing_ok=True)
        return response
    finally:
        await file.close()
        if temporary:
            temporary.unlink(missing_ok=True)
        if final:
            final.unlink(missing_ok=True)


@router.get("/{experiment_id}/stimulus")
def get_stimulus(experiment_id: str) -> FileResponse:
    with connect() as db:
        row = find(db, experiment_id)
        if not row["stimulus"]:
            raise HTTPException(status_code=404, detail="Vídeo não encontrado.")
        path = Path(os.environ.get("EYE_TRACKER_DATA_DIR", "./data")) / "videos" / json.loads(row["stimulus"])["path"]
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Vídeo não encontrado.")
        return FileResponse(path, media_type="video/mp4")


@router.post("/{experiment_id}/publish")
def publish_draft(experiment_id: str) -> dict:
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = find(db, experiment_id)
        if row["code"]:
            return representation(row)
        if not row["stimulus"] or not row["protocol"]:
            raise HTTPException(status_code=409, detail="Envie um vídeo e selecione o protocolo antes de publicar.")
        path = Path(os.environ.get("EYE_TRACKER_DATA_DIR", "./data")) / "videos" / json.loads(row["stimulus"])["path"]
        if not path.is_file():
            raise HTTPException(status_code=409, detail="O vídeo salvo não está disponível.")
        while True:
            code = secrets.token_hex(4).upper()
            if not db.execute("SELECT 1 FROM experiments WHERE code = ?", (code,)).fetchone():
                break
        db.execute("UPDATE experiments SET code = ?, published_at = ? WHERE id = ?", (code, datetime.now(timezone.utc).isoformat(), experiment_id))
        return representation(find(db, experiment_id))
