import subprocess

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_contract() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "eye-tracker-api",
        "version": "0.1.0",
    }


def test_info_contract_marks_capabilities_as_unavailable() -> None:
    response = client.get("/api/info")

    assert response.status_code == 200
    assert response.json() == {
        "name": "Eye Tracker",
        "version": "0.1.0",
        "description": "Base de coleta e processamento de olhar.",
        "capabilities": {
            "session_upload": True,
            "gaze_processing": False,
        },
    }


def test_draft_lifecycle_and_idempotency(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EYE_TRACKER_DATA_DIR", str(tmp_path))
    headers = {"Idempotency-Key": "attempt-1"}
    payload = {"name": "Teste", "description": "Descrição"}
    created = client.post("/api/experiments", json=payload, headers=headers)
    assert created.status_code == 201
    draft = created.json()
    assert draft["state"] == "draft" and draft["code"] is None
    assert client.post("/api/experiments", json=payload, headers=headers).json()["id"] == draft["id"]
    assert client.post("/api/experiments", json={"name": "Outro"}, headers=headers).status_code == 409
    url = f"/api/experiments/{draft['id']}"
    assert client.patch(url, json={"name": "Alterado", "description": ""}).json()["name"] == "Alterado"
    assert client.get(url).json()["name"] == "Alterado"
    assert len(client.get("/api/experiments").json()["items"]) == 1
    assert client.post(url + "/publish").status_code == 409
    assert client.get("/api/experiments/inexistente").status_code == 404
    assert client.post("/api/experiments", json={"name": "   "}, headers={"Idempotency-Key": "2"}).status_code == 422
    assert client.post("/api/experiments", json=payload).status_code == 422


def test_video_protocol_publication_and_immutability(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EYE_TRACKER_DATA_DIR", str(tmp_path))
    draft = client.post("/api/experiments", json={"name": "Estudo"}, headers={"Idempotency-Key": "video"}).json()
    url = f"/api/experiments/{draft['id']}"
    invalid = client.put(url + "/stimulus", files={"file": ("fake.mp4", b"invalid", "video/mp4")})
    assert invalid.status_code == 422
    assert "MP4" in invalid.json()["detail"]
    video = tmp_path / "test.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)], check=True)
    with video.open("rb") as source:
        uploaded = client.put(url + "/stimulus", files={"file": ("test.mp4", source, "video/mp4")})
    assert uploaded.status_code == 200
    assert uploaded.json()["stimulus"]["codec"] == "h264"
    old_hash = uploaded.json()["stimulus"]["sha256"]
    long_video = tmp_path / "long.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:r=1:d=31", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(long_video)], check=True)
    with long_video.open("rb") as source:
        too_long = client.put(url + "/stimulus", files={"file": ("long.mp4", source, "video/mp4")})
    assert too_long.status_code == 422
    assert "30 segundos" in too_long.json()["detail"]
    assert client.get(url).json()["stimulus"]["sha256"] == old_hash
    assert client.put(url + "/stimulus", headers={"Content-Length": str(102 * 1024 * 1024)}, content=b"").status_code == 413
    partial = client.get(url + "/stimulus", headers={"Range": "bytes=0-9"})
    assert partial.status_code == 206 and len(partial.content) == 10
    assert client.post(url + "/publish").status_code == 409
    assert client.put(url + "/protocol").json()["protocol"]["label"] == "Android provisório"
    published = client.post(url + "/publish")
    assert published.status_code == 200
    assert published.json()["state"] == "published"
    assert client.post(url + "/publish").json()["code"] == published.json()["code"]
    assert client.patch(url, json={"name": "Mudança"}).status_code == 409
    assert client.put(url + "/protocol").status_code == 409
    with video.open("rb") as source:
        assert client.put(url + "/stimulus", files={"file": ("test.mp4", source, "video/mp4")}).status_code == 409
    assert client.get(url).json()["code"] == published.json()["code"]


def test_session_receipt_and_retry(tmp_path, monkeypatch):
    import hashlib
    import json
    import uuid

    monkeypatch.setenv("EYE_TRACKER_DATA_DIR", str(tmp_path))
    experiment = client.post("/api/experiments", json={"name": "Estudo"}, headers={"Idempotency-Key": "session"}).json()
    url = f"/api/experiments/{experiment['id']}"
    video = tmp_path / "video.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)], check=True)
    with video.open("rb") as source:
        assert client.put(url + "/stimulus", files={"file": ("video.mp4", source, "video/mp4")}).status_code == 200
    client.put(url + "/protocol")
    published = client.post(url + "/publish").json()
    assert client.get('/api/published-experiments/' + published['code'].lower()).json()['id'] == experiment['id']
    assert client.get('/api/published-experiments/UNKNOWN').status_code == 404
    local_id = str(uuid.uuid4())
    payload = {"experiment_id": experiment["id"], "local_id": local_id, "participant_code": "P01"}
    session = client.post("/api/sessions", json=payload).json()
    assert client.post("/api/sessions", json=payload).json() == session
    assert client.post("/api/sessions", json={**payload, "participant_code": "P02"}).status_code == 409
    metadata = json.dumps({"experimento": experiment["id"], "coleta_local": local_id, "estado": "concluida", "eventos": []}).encode()
    video_bytes = video.read_bytes()
    hashes = {"video_sha256": hashlib.sha256(video_bytes).hexdigest(), "events_sha256": hashlib.sha256(metadata).hexdigest()}
    files = {"video": ("face.mp4", video_bytes, "video/mp4"), "events": ("sessao.json", metadata, "application/json")}
    upload_url = f"/api/sessions/{session['id']}/files"
    assert client.put(upload_url, data={**hashes, "events_sha256": "0" * 64}, files=files).status_code == 422
    assert client.put(upload_url, data=hashes, files=files).json()["received"] is True
    assert client.put(upload_url, data=hashes, files=files).json()["received"] is True
    assert client.put(upload_url, data={**hashes, "video_sha256": "0" * 64}, files=files).status_code == 409
    assert (tmp_path / "sessions" / session["id"] / "face.mp4").read_bytes() == video_bytes
    assert (tmp_path / "sessions" / session["id"] / "sessao.json").read_bytes() == metadata
