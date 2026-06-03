import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client_with_dist(tmp_path, monkeypatch):
    dist = tmp_path / "frontend_dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>SPA</title>")
    (dist / "assets").mkdir()
    (dist / "assets" / "app.js").write_text("console.log('app')")

    monkeypatch.setenv("FRONTEND_DIST_DIR", str(dist))
    import importlib
    import app.core.config as config_mod
    importlib.reload(config_mod)
    import app.main as main_mod
    importlib.reload(main_mod)
    return TestClient(main_mod.app)


def test_root_serves_index(client_with_dist):
    resp = client_with_dist.get("/")
    assert resp.status_code == 200
    assert "SPA" in resp.text


def test_client_route_falls_back_to_index(client_with_dist):
    resp = client_with_dist.get("/me")
    assert resp.status_code == 200
    assert "SPA" in resp.text


def test_api_not_shadowed_by_static(client_with_dist):
    resp = client_with_dist.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_asset_served(client_with_dist):
    resp = client_with_dist.get("/assets/app.js")
    assert resp.status_code == 200
    assert "console.log" in resp.text
