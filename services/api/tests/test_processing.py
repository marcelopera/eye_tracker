import hashlib
import json
import subprocess

from fastapi.testclient import TestClient

from app.experiments import connect
from app.main import app
from app import processing

client = TestClient(app)


def seed(tmp_path, monkeypatch):
    monkeypatch.setenv("EYE_TRACKER_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(processing, "enabled", lambda: True)
    with connect() as db:
        db.execute("INSERT INTO sessions(id, local_id, experiment_id, participant_code, video_hash, events_hash) VALUES ('session','local','exp','P01',?,?)",
                   (hashlib.sha256(b"video").hexdigest(), hashlib.sha256(b"events").hexdigest()))
    source = tmp_path / "sessions/session"
    source.mkdir(parents=True)
    (source / "face.mp4").write_bytes(b"video")
    (source / "sessao.json").write_bytes(b"events")
    return {"config": {"schema_version": 1, "capture": {"rotation_degrees": 0, "mirrored": False}}}


def test_processing_queue_fail_retry_exports_and_integrity(tmp_path, monkeypatch):
    data = seed(tmp_path, monkeypatch)
    assert client.post('/api/sessions/missing/runs', json=data).status_code == 404
    first = client.post('/api/sessions/session/runs', json=data)
    assert first.status_code == 202 and first.json()["status"] == "queued"
    run_id = first.json()["id"]
    assert client.post('/api/sessions/session/runs', json=data).status_code == 409
    assert client.get(f'/api/runs/{run_id}/summary').status_code == 409
    with connect() as db:
        db.execute("UPDATE processing_runs SET status='running' WHERE id=?", (run_id,))
        row = dict(db.execute("SELECT * FROM processing_runs WHERE id=?", (run_id,)).fetchone())
    def fail(*args, **kwargs):
        raise subprocess.TimeoutExpired('processor', 7200)
    monkeypatch.setattr(processing.subprocess, 'run', fail)
    processing.execute(row)
    assert client.get(f'/api/runs/{run_id}').json()["status"] == "failed"
    second = client.post('/api/sessions/session/runs', json=data).json()
    assert second["id"] != run_id
    with connect() as db:
        db.execute("UPDATE processing_runs SET status='running' WHERE id=?", (second["id"],))
        row = dict(db.execute("SELECT * FROM processing_runs WHERE id=?", (second["id"],)).fetchone())
    (tmp_path / 'sessions/session/face.mp4').write_bytes(b'changed')
    processing.execute(row)
    assert 'Integridade' in client.get(f'/api/runs/{second["id"]}').json()["error"]
    result = tmp_path / 'runs' / second['id'] / 'results'
    result.mkdir()
    (result / 'summary.json').write_text(json.dumps({"config": {"synchronization": {"presented_frames": [{"media_time_ms": 50, "duration_ms": 30}]}}}))
    sample = {"frame_index": 0, "stimulus_time_ms": 50, "valid": False, "stimulus_px": None}
    (result / 'samples.jsonl').write_text(json.dumps(sample) + '\n')
    (result / 'samples.csv').write_text('frame_index,valid\n0,False\n')
    with connect() as db:
        db.execute("UPDATE processing_runs SET status='completed' WHERE id=?", (second["id"],))
    url = f'/api/runs/{second["id"]}'
    assert client.get(url + '/samples?offset=0&limit=1').json()['items'] == [sample]
    assert client.get(url + '/samples?offset=1').json()['items'] == []
    assert client.get(url + '/at?time_ms=55').json()['sample'] == sample
    assert client.get(url + '/at?time_ms=90').json()['sample'] is None
    assert client.get(url + '/export/csv').headers['content-disposition'].startswith('attachment')
    assert client.get(url + '/export/xml').status_code == 422
    assert client.get(url + '/samples?limit=1001').status_code == 422
    assert len(client.get('/api/sessions/session/runs').json()) == 2


def test_missing_runtime_and_originals(tmp_path, monkeypatch):
    data = seed(tmp_path, monkeypatch)
    with connect() as db:
        db.execute("UPDATE sessions SET events_hash=NULL")
    assert client.post('/api/sessions/session/runs', json=data).status_code == 409
    monkeypatch.setattr(processing, 'enabled', lambda: False)
    assert client.post('/api/sessions/session/runs', json=data).status_code == 503


def test_restart_marks_interrupted_attempt_and_keeps_history(tmp_path, monkeypatch):
    data = seed(tmp_path, monkeypatch)
    run = client.post('/api/sessions/session/runs', json=data).json()
    with connect() as db:
        db.execute("UPDATE processing_runs SET status='running' WHERE id=?", (run['id'],))
    with TestClient(app) as restarted:
        previous = restarted.get('/api/runs/' + run['id']).json()
        assert previous['status'] == 'failed' and 'reiniciado' in previous['error']
        assert len(restarted.get('/api/sessions/session/runs').json()) == 1
    # A new request is a separate attempt; the original attempt stays auditable.
    retried = client.post('/api/sessions/session/runs', json=data)
    assert retried.status_code == 202 and retried.json()['id'] != run['id']
