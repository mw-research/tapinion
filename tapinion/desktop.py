# Copyright (C) 2026 Markus Wilhelm, mw-research
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Desktop mode: this computer becomes the Tapinion server for tablets in the same network.

Starts the server on all interfaces, keeps the data in the user's application folder,
opens the browser and shows a small window with the addresses and a Quit button.
"""
import os
import secrets
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

APP = "Tapinion"
DEFAULT_PORT = 8765


def data_dir() -> Path:
    if os.environ.get("TAPINION_DATA"):
        base = Path(os.environ["TAPINION_DATA"])
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home())) / APP
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / APP
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "tapinion"
    base.mkdir(parents=True, exist_ok=True)
    return base


def secret_key(folder: Path) -> str:
    """Stable per installation, so logins survive a restart."""
    path = folder / "secret.key"
    if not path.is_file():
        path.write_text(secrets.token_urlsafe(48), encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass
    return path.read_text(encoding="utf-8").strip()


def free_port(preferred: int) -> int:
    for port in [preferred] + list(range(preferred + 1, preferred + 20)):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", port))
                return port
            except OSError:
                continue
    raise SystemExit("No free port found.")


def already_running(port: int) -> bool:
    """True if a Tapinion is already answering on this port (e.g. started at login)."""
    import json
    import urllib.request

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1.5) as r:
            return json.load(r).get("status") == "ok"
    except Exception:
        return False


MAX_LOG_BYTES = 1024 * 1024


def ensure_streams(folder: Path) -> None:
    """A windowed app (double-click, installer) has no console, so sys.stdout and sys.stderr
    are None – anything that prints or logs would crash. Send both to a log file instead."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    path = folder / "tapinion.log"
    if path.is_file() and path.stat().st_size > MAX_LOG_BYTES:
        path.unlink()
    log = open(path, "a", encoding="utf-8", buffering=1)  # noqa: SIM115 - lives as long as the app
    if sys.stdout is None:
        sys.stdout = log
    if sys.stderr is None:
        sys.stderr = log


def main():
    preferred = int(os.environ.get("TAPINION_PORT", DEFAULT_PORT))
    if already_running(preferred):
        # A second double-click: just show the running instance.
        if os.environ.get("TAPINION_HEADLESS") != "1":
            webbrowser.open(f"http://localhost:{preferred}")
        return
    folder = data_dir()
    ensure_streams(folder)
    os.environ.setdefault("DB_PATH", str(folder / "tapinion.sqlite3"))
    os.environ.setdefault("SECRET_KEY", secret_key(folder))
    os.environ.setdefault("COOKIE_SECURE", "0")
    port = free_port(preferred)

    import logging

    import uvicorn

    from .main import app
    from .netinfo import lan_ip

    # Plain logging to stderr (console or log file); uvicorn's own setup expects a terminal.
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_config=None, log_level="warning",
                            proxy_headers=False)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)

    local = f"http://localhost:{port}"
    ip = lan_ip()
    lan = f"http://{ip}:{port}" if ip else None
    from . import __version__
    from .discovery import announce

    from . import db as _db

    with _db.session() as conn:
        instance = _db.instance_id(conn)
    withdraw = announce(port, ip, __version__, instance)  # lets the Android app find this computer
    headless = os.environ.get("TAPINION_HEADLESS") == "1"  # servers, tests: no window, no browser
    if not headless:
        webbrowser.open(local)

    try:
        if headless:
            raise RuntimeError("headless")
        _window(local, lan, folder, server)
    except Exception:  # no display / no tkinter / headless: run in the console
        print(f"{APP} is running.\n  This computer: {local}")
        if lan:
            print(f"  Tablets in the same network: {lan}")
        print(f"  Data: {folder}\nPress Ctrl+C to stop.")
        try:
            while thread.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
    withdraw()
    server.should_exit = True
    thread.join(timeout=5)


def kiosk_browser_command(url: str, folder: Path) -> list[str] | None:
    """A full-screen browser window for the kiosk, with its own profile, so the normal browser
    stays logged in for the results. None if no suitable browser is installed."""
    import shutil

    profile = str(folder / "kiosk-browser")
    candidates = []
    if sys.platform == "win32":
        for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
            if base:
                candidates += [Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
                               Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"]
    elif sys.platform == "darwin":
        candidates += [Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                       Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
                       Path("/Applications/Chromium.app/Contents/MacOS/Chromium")]
    else:
        candidates += [Path(p) for p in (shutil.which("google-chrome"), shutil.which("chromium"),
                                         shutil.which("chromium-browser"), shutil.which("microsoft-edge")) if p]
    for exe in candidates:
        if exe.is_file():
            cmd = [str(exe), "--kiosk", url, f"--user-data-dir={profile}", "--no-first-run",
                   "--no-default-browser-check", "--disable-pinch", "--overscroll-history-navigation=0"]
            if exe.name.lower().startswith("msedge"):
                cmd.append("--edge-kiosk-type=fullscreen")
            return cmd
    return None


def open_kiosk_here(local: str, folder: Path) -> bool:
    """Open the login page (with the open events) as a full-screen kiosk on this computer."""
    import subprocess

    cmd = kiosk_browser_command(f"{local}/login", folder)
    if cmd:
        subprocess.Popen(cmd, close_fds=True)
        return True
    webbrowser.open(f"{local}/login")
    return False


def _window(local, lan, folder, server):
    import tkinter as tk
    from tkinter import ttk

    de = (os.environ.get("LANG", "") + os.environ.get("LC_ALL", "")).lower().startswith("de")
    if sys.platform == "win32":
        import locale
        de = (locale.getdefaultlocale()[0] or "").lower().startswith("de")
    quit_keys = "Cmd+Q" if sys.platform == "darwin" else "Alt+F4"
    txt = {
        "running": "Tapinion läuft." if de else "Tapinion is running.",
        "admin": "Verwaltung und Auswertung" if de else "Administration and results",
        "open": "Tapinion öffnen" if de else "Open Tapinion",
        "kiosk": "Kiosk auf diesem Rechner" if de else "Kiosk on this computer",
        "kiosk_hint": (f"Öffnet die Bewertung im Vollbild, z. B. für einen Laptop am Eingang. "
                       f"Veranstaltung wählen, PIN eingeben. Vollbild beenden: {quit_keys}.") if de else
                      (f"Opens the rating screen full screen, e.g. for a laptop at the entrance. "
                       f"Choose the event, enter the PIN. Leave full screen: {quit_keys}."),
        "no_kiosk_browser": ("Kein Browser mit Kiosk-Modus gefunden – geöffnet im normalen Browser. "
                             "Vollbild mit F11 (Mac: Ctrl+Cmd+F).") if de else
                            ("No browser with kiosk mode found – opened in the normal browser. "
                             "Full screen with F11 (Mac: Ctrl+Cmd+F)."),
        "tablets": "Tablets und Smartphones" if de else "Tablets and smartphones",
        "tablets_hint": ("Im selben WLAN: Android-App findet diesen Rechner selbst, sonst den QR-Code "
                         "unter Veranstaltungen scannen. Adresse:") if de else
                        ("In the same Wi-Fi: the Android app finds this computer by itself, otherwise "
                         "scan the QR code under Events. Address:"),
        "app": "Android-App fürs Tablet (QR-Code)" if de else "Android app for the tablet (QR code)",
        "nolan": "kein Netzwerk – nur auf diesem Rechner erreichbar" if de else
                 "no network – reachable on this computer only",
        "folder": "Datenordner" if de else "Data folder",
        "quit": "Tapinion beenden" if de else "Quit Tapinion",
    }

    root = tk.Tk()
    root.title(APP)
    root.resizable(False, False)
    try:
        icon = Path(__file__).parent / "static" / "icons" / "icon-192.png"
        root.iconphoto(True, tk.PhotoImage(file=str(icon)))
    except Exception:
        pass
    style = ttk.Style(root)
    style.configure("Big.TButton", font=("TkDefaultFont", 11, "bold"), padding=(14, 8))
    muted = "#5c6878"
    frm = ttk.Frame(root, padding=20)
    frm.grid()
    ttk.Label(frm, text=txt["running"], font=("TkDefaultFont", 14, "bold")).grid(row=0, column=0, sticky="w")

    ttk.Label(frm, text=txt["admin"], font=("TkDefaultFont", 10, "bold")).grid(row=1, column=0, sticky="w", pady=(16, 4))
    ttk.Button(frm, text=txt["open"], style="Big.TButton", command=lambda: webbrowser.open(local)).grid(row=2, column=0, sticky="we")

    ttk.Label(frm, text=txt["kiosk"], font=("TkDefaultFont", 10, "bold")).grid(row=3, column=0, sticky="w", pady=(16, 4))
    status = ttk.Label(frm, text=txt["kiosk_hint"], wraplength=420, foreground=muted)

    def kiosk():
        if not open_kiosk_here(local, folder):
            status.configure(text=txt["no_kiosk_browser"])

    ttk.Button(frm, text=txt["kiosk"], style="Big.TButton", command=kiosk).grid(row=4, column=0, sticky="we")
    status.grid(row=5, column=0, sticky="w", pady=(4, 0))

    ttk.Label(frm, text=txt["tablets"], font=("TkDefaultFont", 10, "bold")).grid(row=6, column=0, sticky="w", pady=(16, 4))
    ttk.Label(frm, text=txt["tablets_hint"], wraplength=420, foreground=muted).grid(row=7, column=0, sticky="w")
    ttk.Label(frm, text=lan or txt["nolan"], font=("TkFixedFont", 11)).grid(row=8, column=0, sticky="w", pady=(2, 0))
    ttk.Button(frm, text=txt["app"], command=lambda: webbrowser.open(local + "/app")).grid(row=9, column=0, sticky="w", pady=(8, 0))

    btns = ttk.Frame(frm)
    btns.grid(row=10, column=0, sticky="we", pady=(18, 0))
    btns.columnconfigure(0, weight=1)
    ttk.Button(btns, text=txt["folder"], command=lambda: _open_folder(folder)).grid(row=0, column=0, sticky="w")
    ttk.Button(btns, text=txt["quit"], command=root.destroy).grid(row=0, column=1, sticky="e")

    def watch():
        if server.should_exit:
            root.destroy()
        else:
            root.after(500, watch)

    root.after(500, watch)

    def to_front():
        # The browser opens at the same time and would cover the window (macOS in particular).
        root.lift()
        root.attributes("-topmost", True)
        root.after(1500, lambda: root.attributes("-topmost", False))
        try:
            root.focus_force()
        except tk.TclError:
            pass

    root.after(1200, to_front)
    root.mainloop()


def _open_folder(folder: Path):
    if sys.platform == "win32":
        os.startfile(folder)  # noqa: S606
    elif sys.platform == "darwin":
        os.system(f'open "{folder}"')  # noqa: S605
    else:
        os.system(f'xdg-open "{folder}"')  # noqa: S605


if __name__ == "__main__":
    main()
