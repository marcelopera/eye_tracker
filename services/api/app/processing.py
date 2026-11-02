"""A single persistent local queue, executed in an isolated CPU subprocess."""
from contextlib import asynccontextmanager
from functools import lru_cache
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import threading
import tempfile
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.experiments import connect

router = APIRouter(prefix="/api", tags=["processing"])
_stop = threading.Event()


def now():
    return datetime.now(timezone.utc).isoformat()


def root():
    return Path(os.environ.get("EYE_TRACKER_DATA_DIR", "./data"))


def runtime():
    local = next((p / "ml/itracker" for p in Path(__file__).resolve().parents if (p / "ml/itracker/pipeline.py").is_file()), Path("/opt/pipeline"))
    directory = Path(os.environ.get("EYE_TRACKER_PIPELINE_DIR", str(local)))
    python = Path(os.environ.get("EYE_TRACKER_PIPELINE_PYTHON", str(directory / ".venv/bin/python")))
    return directory, python


def enabled():
    directory, python = runtime()
    return (directory / "pipeline.py").is_file() and python.is_file()


class RunInput(BaseModel):
    config: dict = Field(description="Configuração v1 descrita em docs/pipeline.md; medidas ausentes devem ser null.")


class PreparationInput(BaseModel):
    settings: dict = Field(default_factory=dict)


@router.post("/sessions/{session_id}/analysis-config")
def collection_config(session_id: str, data: PreparationInput):
    import hashlib
    from app.sessions import received_file
    source = received_file(session_id, "sessao.json", "events_hash")
    with connect() as db:
        expected = db.execute("SELECT events_hash FROM sessions WHERE id=?", (session_id,)).fetchone()[0]
    with source.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
            raise HTTPException(409, "Integridade dos metadados da coleta divergente.")
    if not enabled():
        raise HTTPException(503, "Runtime de processamento não instalado.")
    try:
        encoded = json.dumps(data.settings, allow_nan=False)
    except (ValueError, TypeError):
        raise HTTPException(422, "Medidas inválidas.")
    if len(encoded) > 20000:
        raise HTTPException(413, "Medidas excedem 20 KB.")
    directory, python = runtime()
    try:
        with tempfile.TemporaryDirectory() as temporary:
            settings = Path(temporary) / "settings.json"
            settings.write_text(encoded, encoding="utf-8")
            result = subprocess.run([str(python), str(directory / "itracker.py"), "prepare", "--events", str(source.resolve()),
                "--settings", str(settings)], capture_output=True, text=True, timeout=30,
                env={**os.environ, "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1"})
            if result.returncode:
                raise HTTPException(422, "Não foi possível gerar a configuração: " + result.stderr[-3000:])
            return json.loads(result.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise HTTPException(422, "Não foi possível ler a instrumentação da coleta.")


class RunView(BaseModel):
    id: str
    session_id: str
    status: str
    created_at: str
    started_at: str | None
    finished_at: str | None
    error: str | None
    config: dict
    progress: dict | None = None


def view(row):
    result = dict(row)
    result["config"] = json.loads(result["config"])
    try:
        result["progress"] = json.loads((root() / "runs" / row["id"] / "progress.json").read_text())
    except (OSError, ValueError):
        result["progress"] = None
    return result


def find_run(run_id):
    with connect() as db:
        row = db.execute("SELECT * FROM processing_runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Execução não encontrada.")
        return dict(row)


@router.post("/sessions/{session_id}/runs", response_model=RunView, status_code=202)
def start_run(session_id: str, data: RunInput):
    if not enabled():
        raise HTTPException(503, "Runtime de processamento não instalado.")
    try:
        encoded = json.dumps(data.config, allow_nan=False)
    except ValueError:
        raise HTTPException(422, "Configuração contém números não finitos.")
    if len(encoded) > 2_000_000:
        raise HTTPException(413, "Configuração excede 2 MB.")
    if data.config.get("schema_version") != 1 or not isinstance(data.config.get("capture"), dict):
        raise HTTPException(422, "Informe schema_version 1 e capture com rotação e espelhamento.")
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        session = db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not session:
            raise HTTPException(404, "Sessão não encontrada.")
        if not session["video_hash"] or not session["events_hash"]:
            raise HTTPException(409, "Aguarde o recebimento íntegro dos arquivos.")
        active = db.execute("SELECT * FROM processing_runs WHERE session_id = ? AND status IN ('queued','running')", (session_id,)).fetchone()
        if active:
            raise HTTPException(409, "Já existe uma execução ativa para esta sessão.")
        run_id = str(uuid4())
        db.execute("INSERT INTO processing_runs(id,session_id,status,config,created_at) VALUES (?,?,'queued',?,?)",
                   (run_id, session_id, encoded, now()))
        row = db.execute("SELECT * FROM processing_runs WHERE id = ?", (run_id,)).fetchone()
        return view(row)


@router.get("/sessions/{session_id}/runs", response_model=list[RunView])
def list_runs(session_id: str):
    with connect() as db:
        if not db.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone():
            raise HTTPException(404, "Sessão não encontrada.")
        return [view(r) for r in db.execute("SELECT * FROM processing_runs WHERE session_id = ? ORDER BY rowid DESC LIMIT 100", (session_id,))]


@router.get("/runs/{run_id}", response_model=RunView)
def get_run(run_id: str):
    return view(find_run(run_id))


def artifact(run_id, filename):
    row = find_run(run_id)
    if row["status"] != "completed":
        raise HTTPException(409, "Resultados ainda não disponíveis.")
    path = root() / "runs" / row["id"] / "results" / filename
    if not path.is_file():
        raise HTTPException(404, "Artefato indisponível.")
    return path


@router.get("/runs/{run_id}/summary")
def summary(run_id: str):
    return json.loads(artifact(run_id, "summary.json").read_text())


@router.get("/runs/{run_id}/samples")
def samples(run_id: str, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000)):
    rows = []
    with artifact(run_id, "samples.jsonl").open() as stream:
        for index, line in enumerate(stream):
            if index < offset:
                continue
            if len(rows) >= limit:
                break
            rows.append(json.loads(line))
    return {"items": rows, "offset": offset, "limit": limit}


@lru_cache(maxsize=2)
def overlay_samples(path):
    index = {}
    with Path(path).open() as stream:
        for line in stream:
            row = json.loads(line)
            stamp = row["stimulus_time_ms"]
            if stamp is not None and (stamp not in index or (not index[stamp]["valid"] and row["valid"])):
                row.pop("features", None)
                row.pop("boxes", None)
                index[stamp] = row
    return index


@router.get("/runs/{run_id}/at")
def sample_at(run_id: str, time_ms: float = Query(ge=0, allow_inf_nan=False)):
    report = json.loads(artifact(run_id, "summary.json").read_text())
    sync = report["config"].get("synchronization")
    if not sync:
        return {"sample": None}
    # Only associate media intervals actually declared as presented; never extrapolate.
    intervals = [f for f in sync["presented_frames"] if f["media_time_ms"] <= time_ms < f["media_time_ms"] + (f.get("media_duration_ms") or f["duration_ms"])]
    if not intervals:
        return {"sample": None}
    stamps = {f["media_time_ms"] for f in intervals}
    index = overlay_samples(str(artifact(run_id, "samples.jsonl")))
    candidates = [index[stamp] for stamp in stamps if stamp in index]
    return {"sample": max(candidates, key=lambda row: row["stimulus_time_ms"]) if candidates else None}


@router.get("/runs/{run_id}/export/{format}")
def export(run_id: str, format: str):
    if format not in ("csv", "jsonl"):
        raise HTTPException(422, "Formato esperado: csv ou jsonl.")
    return FileResponse(artifact(run_id, f"samples.{format}"), media_type="text/csv" if format == "csv" else "application/x-ndjson",
                        filename=f"gaze-{run_id}.{format}")


@router.get("/runs/{run_id}/previews/{frame_index}")
def preview(run_id: str, frame_index: int):
    if frame_index < 0:
        raise HTTPException(404)
    return FileResponse(artifact(run_id, f"crops-{frame_index}.jpg"), media_type="image/jpeg")


def execute(row):
    """Original hashes are checked again before any result is generated."""
    import hashlib
    directory, python = runtime()
    run_root = root() / "runs" / row["id"]
    try:
        run_root.mkdir(parents=True, exist_ok=True)
        with connect() as db:
            session = db.execute("SELECT * FROM sessions WHERE id = ?", (row["session_id"],)).fetchone()
        source = root() / "sessions" / session["id"]
        for filename, column in (("face.mp4", "video_hash"), ("sessao.json", "events_hash")):
            digest = hashlib.sha256()
            with (source / filename).open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != session[column]:
                raise ValueError("Integridade dos arquivos originais divergente.")
        settings = json.loads(row["config"])
        if settings.get("geometry"):
            with connect() as db:
                experiment = db.execute("SELECT stimulus FROM experiments WHERE id=?", (session["experiment_id"],)).fetchone()
            stimulus = json.loads(experiment["stimulus"]) if experiment and experiment["stimulus"] else None
            if stimulus and (settings["geometry"].get("stimulus_width_px"), settings["geometry"].get("stimulus_height_px")) != (stimulus["width"], stimulus["height"]):
                raise ValueError("Dimensões do estímulo na configuração divergem do vídeo do experimento.")
        config = run_root / "config.json"
        config.write_text(row["config"], encoding="utf-8")
        # Capture diagnostics in a private file, never in memory proportional to the video.
        with (run_root / "processor.log").open("w+") as log:
            result = subprocess.run([str(python), str(directory / "itracker.py"), "process",
                                     "--run-id", row["id"], "--session-id", row["session_id"], "--progress", str((run_root / "progress.json").resolve()),
                                     "--video", str((source / "face.mp4").resolve()), "--events", str((source / "sessao.json").resolve()),
                                     "--models", str(Path(os.environ.get("EYE_TRACKER_MODELS_DIR", str(directory.parent.parent / "modelos/itracker"))).resolve()),
                                     "--config", str(config.resolve()), "--output", str((run_root / "results").resolve())],
                                    stdout=log, stderr=log, timeout=7200,
                                    env={**os.environ, "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MPLCONFIGDIR": "/tmp/eye-tracker-mpl"})
            if result.returncode:
                log.seek(0, 2)
                size = log.tell()
                log.seek(max(0, size - 4000))
                raise ValueError("Processamento falhou: " + log.read())
        if not (run_root / "results/summary.json").is_file():
            raise ValueError("Processador não publicou o relatório.")
        status, error = "completed", None
    except (OSError, ValueError, subprocess.TimeoutExpired) as failure:
        status, error = "failed", str(failure)[-4000:]
    with connect() as db:
        db.execute("UPDATE processing_runs SET status=?,error=?,finished_at=? WHERE id=?", (status, error, now(), row["id"]))


def work():
    while not _stop.is_set():
        try:
            with connect() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("SELECT * FROM processing_runs WHERE status='queued' ORDER BY rowid LIMIT 1").fetchone()
                if row:
                    db.execute("UPDATE processing_runs SET status='running',started_at=? WHERE id=?", (now(), row["id"]))
                    row = dict(row)
            if row:
                execute(row)
            else:
                _stop.wait(1)
        except Exception:
            import logging
            logging.exception("Falha no worker de processamento")
            _stop.wait(2)


@asynccontextmanager
async def lifespan(app):
    # One API process per data directory. An interrupted attempt remains inspectable.
    with connect() as db:
        db.execute("UPDATE processing_runs SET status='failed',error='Servidor reiniciado durante processamento; inicie nova tentativa.',finished_at=? WHERE status='running'", (now(),))
    _stop.clear()
    thread = threading.Thread(target=work, daemon=True, name="gaze-worker")
    thread.start()
    yield
    _stop.set()
    thread.join(timeout=2)
