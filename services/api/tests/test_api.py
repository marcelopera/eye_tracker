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
            "session_upload": False,
            "gaze_processing": False,
        },
    }


def test_only_the_two_read_only_api_routes_are_published() -> None:
    schema = client.get("/openapi.json").json()

    assert set(schema["paths"]) == {"/api/health", "/api/info"}
    assert all(set(path_item) == {"get"} for path_item in schema["paths"].values())
    assert client.post("/api/upload").status_code == 404
