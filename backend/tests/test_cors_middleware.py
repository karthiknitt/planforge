from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_default_localhost_origin_allowed():
    response = client.get("/api/health", headers={"Origin": "http://localhost:3001"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:3001"


def test_vercel_preview_origin_for_this_project_allowed():
    origin = "https://planforge-lr8gl7ayx-karthikeyan-natarajans-projects.vercel.app"
    response = client.get("/api/health", headers={"Origin": origin})
    assert response.headers["access-control-allow-origin"] == origin


def test_other_vercel_tenant_origin_rejected():
    origin = "https://planforge-evil-someoneelses-team.vercel.app"
    response = client.get("/api/health", headers={"Origin": origin})
    assert "access-control-allow-origin" not in response.headers


def test_arbitrary_non_vercel_origin_rejected():
    response = client.get("/api/health", headers={"Origin": "https://evil.example.com"})
    assert "access-control-allow-origin" not in response.headers
