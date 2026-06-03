from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_security_headers_present():
    resp = client.get("/api/health")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "max-age=" in resp.headers["Strict-Transport-Security"]
    assert "default-src 'self'" in resp.headers["Content-Security-Policy"]


def test_xss_header_absent():
    resp = client.get("/api/health")
    assert "X-XSS-Protection" not in resp.headers


def test_csp_img_src_allows_blob():
    # Avatars (useAuthedImage) and image-processor previews render via
    # blob: object URLs in <img>. img-src must permit blob: or they render
    # as broken/black images.
    resp = client.get("/api/health")
    csp = resp.headers["Content-Security-Policy"]
    img_src = next(d for d in csp.split(";") if d.strip().startswith("img-src"))
    assert "blob:" in img_src
