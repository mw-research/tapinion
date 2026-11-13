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


def main():
    folder = data_dir()
    os.environ.setdefault("DB_PATH", str(folder / "tapinion.sqlite3"))
    os.environ.setdefault("SECRET_KEY", secret_key(folder))
    os.environ.setdefault("COOKIE_SECURE", "0")
    port = free_port(int(os.environ.get("TAPINION_PORT", DEFAULT_PORT)))

    import uvicorn

    from .main import app
    from .netinfo import lan_ip

    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning", proxy_headers=False)
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
    server.should_exit = True
    thread.join(timeout=5)


def _window(local, lan, folder, server):
    import tkinter as tk
    from tkinter import ttk

    de = (os.environ.get("LANG", "") + os.environ.get("LC_ALL", "")).lower().startswith("de")
    if sys.platform == "win32":
        import locale
        de = (locale.getdefaultlocale()[0] or "").lower().startswith("de")
    txt = {
        "running": "Tapinion läuft." if de else "Tapinion is running.",
        "here": "Auf diesem Rechner:" if de else "On this computer:",
        "lan": "Tablets im selben Netz:" if de else "Tablets in the same network:",
        "nolan": "Kein Netzwerk gefunden – nur auf diesem Rechner erreichbar." if de else
                 "No network found – reachable on this computer only.",
        "data": "Daten:" if de else "Data:",
        "open": "Im Browser öffnen" if de else "Open in browser",
        "folder": "Datenordner" if de else "Data folder",
        "quit": "Beenden" if de else "Quit",
        "hint": "Beim ersten Start fragt die Firewall, ob Tapinion im Netzwerk erreichbar sein darf – "
                "für Tablets mit „Zulassen“ (private Netzwerke) bestätigen." if de else
                "On first start the firewall asks whether Tapinion may be reachable in the network – "
                "allow it (private networks) so tablets can connect.",
    }

    root = tk.Tk()
    root.title(APP)
    root.resizable(False, False)
    try:
        icon = Path(__file__).parent / "static" / "icons" / "icon-192.png"
        root.iconphoto(True, tk.PhotoImage(file=str(icon)))
    except Exception:
        pass
    frm = ttk.Frame(root, padding=18)
    frm.grid()
    ttk.Label(frm, text=txt["running"], font=("TkDefaultFont", 13, "bold")).grid(column=0, row=0, columnspan=2, sticky="w")
    ttk.Label(frm, text=txt["here"]).grid(column=0, row=1, sticky="w", pady=(10, 0))
    ttk.Label(frm, text=local, font=("TkFixedFont", 11)).grid(column=1, row=1, sticky="w", pady=(10, 0), padx=(8, 0))
    ttk.Label(frm, text=txt["lan"]).grid(column=0, row=2, sticky="w")
    ttk.Label(frm, text=lan or txt["nolan"], font=("TkFixedFont", 11) if lan else None).grid(column=1, row=2, sticky="w", padx=(8, 0))
    ttk.Label(frm, text=txt["data"]).grid(column=0, row=3, sticky="w")
    ttk.Label(frm, text=str(folder)).grid(column=1, row=3, sticky="w", padx=(8, 0))
    ttk.Label(frm, text=txt["hint"], wraplength=440, foreground="#5c6878").grid(column=0, row=4, columnspan=2, sticky="w", pady=(10, 0))
    btns = ttk.Frame(frm)
    btns.grid(column=0, row=5, columnspan=2, sticky="e", pady=(14, 0))
    ttk.Button(btns, text=txt["open"], command=lambda: webbrowser.open(local)).grid(column=0, row=0, padx=4)
    ttk.Button(btns, text=txt["folder"], command=lambda: _open_folder(folder)).grid(column=1, row=0, padx=4)
    ttk.Button(btns, text=txt["quit"], command=root.destroy).grid(column=2, row=0, padx=4)

    def watch():
        if server.should_exit:
            root.destroy()
        else:
            root.after(500, watch)

    root.after(500, watch)
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
