import sys

import uvicorn

from tapinion import desktop
from tapinion.main import app


def test_windowed_start_without_console(tmp_path, monkeypatch):
    """Double-clicked apps have no console (sys.stdout/stderr are None); the server must still start."""
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    desktop.ensure_streams(tmp_path)
    try:
        assert sys.stdout is not None and sys.stderr is not None
        uvicorn.Config(app, host="127.0.0.1", port=0, log_config=None, log_level="warning").load()
        print("written to the log file")
        sys.stdout.flush()
        assert "written to the log file" in (tmp_path / "tapinion.log").read_text(encoding="utf-8")
    finally:
        sys.stdout.close()


def test_console_streams_untouched(tmp_path):
    before = sys.stdout
    desktop.ensure_streams(tmp_path)
    assert sys.stdout is before and not (tmp_path / "tapinion.log").exists()
