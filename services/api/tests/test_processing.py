import hashlib
import json
import subprocess
from pathlib import Path
import pytest

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


@pytest.mark.parametrize("mode", ["measured", "demo"])
def test_collection_preparation_uses_verified_original_and_private_settings(tmp_path, monkeypatch, mode):
    from types import SimpleNamespace
    seed(tmp_path, monkeypatch)
    source = tmp_path / 'sessions/session/sessao.json'
    source.write_text(json.dumps({'estado':'concluida','eventos':[]}))
    with connect() as db:
        db.execute('UPDATE sessions SET events_hash=?', (hashlib.sha256(source.read_bytes()).hexdigest(),))
    calls = []
    def prepare(command, **kwargs):
        calls.append(command)
        assert command[2] == 'prepare'
        assert ('--demo' in command) == (mode == 'demo')
        assert json.loads(Path(command[-1]).read_text()) == {'settling_ms':500}
        return SimpleNamespace(returncode=0, stdout=json.dumps({'config':{'schema_version':1},'issues':['missing_camera_instrumentation'],'ready_for_pilot':False}))
    monkeypatch.setattr(processing.subprocess, 'run', prepare)
    assert client.post('/api/sessions/missing/analysis-config',json={'settings':{}}).status_code == 404
    response = client.post('/api/sessions/session/analysis-config',json={'settings':{'settling_ms':500},'mode':mode})
    assert response.status_code == 200 and not response.json()['ready_for_pilot']
    assert len(calls) == 1
    assert not Path(calls[0][-1]).exists()
    source.write_text('{}')
    assert client.post('/api/sessions/session/analysis-config',json={}).status_code == 409
    assert len(calls) == 1


def test_preparation_validation_failure_and_media_interval_are_explicit(tmp_path, monkeypatch):
    from types import SimpleNamespace
    seed(tmp_path, monkeypatch)
    monkeypatch.setattr(processing.subprocess,'run',lambda *a,**kw: SimpleNamespace(returncode=1,stderr='Medidas inválidas'))
    assert client.post('/api/sessions/session/analysis-config',json={'settings':{}}).status_code == 422
    first = client.post('/api/sessions/session/runs', json={'config':{'schema_version':1,'capture':{}}}).json()
    result = tmp_path / 'runs' / first['id'] / 'results'
    result.mkdir(parents=True)
    (result/'summary.json').write_text(json.dumps({'config':{'synchronization':{'presented_frames':[
        {'media_time_ms':100,'duration_ms':400,'media_duration_ms':100}]}}}))
    (result/'samples.jsonl').write_text(json.dumps({'stimulus_time_ms':100,'valid':True})+'\n')
    with connect() as db: db.execute("UPDATE processing_runs SET status='completed' WHERE id=?",(first['id'],))
    assert client.get(f"/api/runs/{first['id']}/at?time_ms=150").json()['sample'] is not None
    assert client.get(f"/api/runs/{first['id']}/at?time_ms=300").json()['sample'] is None


def demo_setup(tmp_path, monkeypatch):
    data = seed(tmp_path, monkeypatch)
    config = {**data['config'], 'demonstration': True, 'geometry': {
        'stimulus_width_px': 32, 'stimulus_height_px': 24, 'stimulus_coordinate_space': 'display'}}
    stimulus = tmp_path / 'videos/stimulus.mp4'
    stimulus.parent.mkdir()
    stimulus.write_bytes(b'stimulus')
    with connect() as db:
        db.execute('INSERT INTO experiments(id,name,description,created_at,request_hash,stimulus) VALUES (?,?,?,?,?,?)',
                   ('exp', 'Test', '', 'now', 'hash', json.dumps({'path': stimulus.name, 'width': 32, 'height': 24,
                    'sha256': hashlib.sha256(b'stimulus').hexdigest()})))
    monkeypatch.setattr(processing, 'collection_config', lambda session_id, data: {'config': config, 'issues': []})
    return stimulus


def run_queued(run_id):
    with connect() as db:
        db.execute("UPDATE processing_runs SET status='running' WHERE id=?", (run_id,))
        row = dict(db.execute('SELECT * FROM processing_runs WHERE id=?', (run_id,)).fetchone())
    processing.execute(row)


def test_demo_job_generates_downloadable_mp4_and_supports_range_requests(tmp_path, monkeypatch):
    from types import SimpleNamespace
    demo_setup(tmp_path, monkeypatch)
    calls = []
    def processor(command, **kwargs):
        calls.append(command)
        if 'process' in command:
            results = Path(command[command.index('--output') + 1])
            results.mkdir()
            (results / 'summary.json').write_text('{}')
        else:
            assert Path(command[1]).name == 'demonstration.py'
            assert '--camera' in command and '--stimulus' in command and '--progress' in command
            Path(command[command.index('--output') + 1]).write_bytes(b'complete-mp4')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(processing.subprocess, 'run', processor)
    first = client.post('/api/sessions/session/demonstration')
    assert first.status_code == 202
    run = first.json()
    assert run['kind'] == 'demonstration' and not run['demonstration_available']
    assert client.post('/api/sessions/session/demonstration').status_code == 409
    url = '/api/runs/' + run['id']
    assert client.get(url + '/demonstration').status_code == 409
    run_queued(run['id'])
    result = client.get(url).json()
    assert result['status'] == 'completed' and result['demonstration_available']
    assert len(calls) == 2
    assert client.get(url + '/demonstration').headers['content-disposition'].startswith('inline')
    download = client.get(url + '/demonstration?download=true')
    assert download.content == b'complete-mp4' and download.headers['content-type'] == 'video/mp4'
    assert download.headers['content-disposition'].startswith('attachment')
    partial = client.get(url + '/demonstration', headers={'Range': 'bytes=0-3'})
    assert partial.status_code == 206 and partial.content == b'comp'
    assert client.get('/api/sessions/session/runs').json()[0]['demonstration_available']


def test_demo_preparation_failures_and_render_failure_can_be_retried(tmp_path, monkeypatch):
    from types import SimpleNamespace
    demo_setup(tmp_path, monkeypatch)
    prepared = processing.collection_config
    monkeypatch.setattr(processing, 'collection_config', lambda *a: {'issues': ['missing_camera_instrumentation']})
    assert client.post('/api/sessions/session/demonstration').status_code == 422
    assert client.get('/api/sessions/session/runs').json() == []
    monkeypatch.setattr(processing, 'collection_config', prepared)
    def processor(command, **kwargs):
        if 'process' in command:
            results = Path(command[command.index('--output') + 1])
            results.mkdir()
            (results / 'summary.json').write_text('{}')
            return SimpleNamespace(returncode=0)
        kwargs['stderr'].write('sem amostras de calibração')
        return SimpleNamespace(returncode=1)
    monkeypatch.setattr(processing.subprocess, 'run', processor)
    run = client.post('/api/sessions/session/demonstration').json()
    run_queued(run['id'])
    result = client.get('/api/runs/' + run['id']).json()
    assert result['status'] == 'failed' and not result['demonstration_available']
    assert 'calibração' in result['error']
    assert client.get('/api/runs/' + run['id'] + '/demonstration').status_code == 409
    assert client.post('/api/sessions/session/demonstration').status_code == 202


def test_demo_verifies_stimulus_integrity_before_rendering(tmp_path, monkeypatch):
    from types import SimpleNamespace
    stimulus = demo_setup(tmp_path, monkeypatch)
    def processor(command, **kwargs):
        assert 'process' in command  # The renderer must not be invoked.
        results = Path(command[command.index('--output') + 1])
        results.mkdir()
        (results / 'summary.json').write_text('{}')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(processing.subprocess, 'run', processor)
    run = client.post('/api/sessions/session/demonstration').json()
    stimulus.write_bytes(b'changed')
    run_queued(run['id'])
    result = client.get('/api/runs/' + run['id']).json()
    assert result['status'] == 'failed' and 'Integridade' in result['error']


def test_existing_processing_runs_migrate_as_analysis_without_losing_history(tmp_path, monkeypatch):
    import sqlite3
    monkeypatch.setenv('EYE_TRACKER_DATA_DIR', str(tmp_path))
    with sqlite3.connect(tmp_path / 'experiments.sqlite3') as db:
        db.execute('CREATE TABLE processing_runs (id TEXT PRIMARY KEY,session_id TEXT,status TEXT,config TEXT,created_at TEXT,started_at TEXT,finished_at TEXT,error TEXT)')
        db.execute("INSERT INTO processing_runs(id,session_id,status,config,created_at) VALUES ('old','session','completed','{}','now')")
        db.execute('PRAGMA user_version = 2')
    with connect() as db:
        row = dict(db.execute('SELECT * FROM processing_runs').fetchone())
        assert row['id'] == 'old' and row['kind'] == 'analysis' and row['status'] == 'completed'
        assert db.execute('PRAGMA user_version').fetchone()[0] == 3
    with connect() as db:
        assert db.execute('SELECT count(*) FROM processing_runs').fetchone()[0] == 1
