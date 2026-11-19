from fastapi.testclient import TestClient

from tapinion.main import app


def test_app_page_without_apk(users, tmp_path, monkeypatch):
    monkeypatch.setenv("TAPINION_APK", str(tmp_path / "missing.apk"))
    c = TestClient(app)
    r = c.get("/app")
    assert r.status_code == 200
    assert "/app/tapinion.apk" not in r.text
    assert "releases/latest" in r.text
    assert "<svg" in r.text  # QR code for the tablet
    assert c.get("/app/tapinion.apk").status_code == 404


def test_app_page_offers_the_apk(users, tmp_path, monkeypatch):
    apk = tmp_path / "tapinion-android-1.2.0.apk"
    apk.write_bytes(b"PK\x03\x04" + b"0" * 2_000_000)
    monkeypatch.setenv("TAPINION_APK", str(apk))
    c = TestClient(app)
    r = c.get("/app")
    assert r.status_code == 200 and 'href="/app/tapinion.apk"' in r.text
    assert "(2 MB)" in r.text
    d = c.get("/app/tapinion.apk")
    assert d.status_code == 200
    assert d.headers["content-type"] == "application/vnd.android.package-archive"
    assert "tapinion-android.apk" in d.headers["content-disposition"]
    assert d.content == apk.read_bytes()


def test_app_page_needs_no_login(users, tmp_path, monkeypatch):
    """Tablets open the page without an account (the APK is free software anyway)."""
    monkeypatch.setenv("TAPINION_APK", str(tmp_path / "missing.apk"))
    r = TestClient(app).get("/app", follow_redirects=False)
    assert r.status_code == 200
