<p align="center"><img src="tapinion/static/logo.svg" alt="Tapinion" width="300"></p>

<p align="center"><b>Tap your opinion.</b> A feedback kiosk for events, receptions, canteens and anywhere
people pass by: one tap on a smiley or on a 0–10 scale, results live, PDF reports, roles.</p>

<p align="center"><a href="README.de.md">Deutsch</a> · <a href="#install">Install</a> · <a href="#roles">Roles</a> · <a href="LICENSE">AGPL-3.0</a></p>

---

## What it does

- **Kiosk** on a tablet, phone or laptop: smileys (satisfied / neutral / dissatisfied) or the
  recommendation scale 0–10, thank-you screen, back to the question after 4 seconds.
  German and English, switchable on the kiosk; the question can be set per language.
- **PIN-protected**: opening and leaving the kiosk on a device needs the event's PIN.
  Shortening the URL in the kiosk leads to the login page, never into the results.
- **Keeps votes when the network drops** and sends them later with their original time.
- **Results** per event and day: Net Promoter Score or satisfaction balance (−100 to +100),
  groups, single values, ratings per hour, individual ratings, live refresh, CSV export.
- **PDF reports** for one event or for many (date range, type, optional page per event),
  in the user's language and in the installation's colours and logo.
- **Roles** for organizers, analysts and administrators (see below).
- **Your look**: administrators set name, logo and colours (e.g. corporate design) in the app.
- **Runs anywhere**: as a desktop app on a laptop (tablets connect via QR code in the same
  network), as an Android kiosk app, in any browser (iPad: add to home screen), or on a
  server with Docker or Kubernetes.

## Install

### Without a server: laptop + tablets

| Computer | Download from the [releases](https://github.com/mw-research/tapinion/releases/latest) | |
|---|---|---|
| Windows 10/11 | `Tapinion-Setup-….exe` | Double-click, *Next*, *Next*, *Finish* |
| macOS (Apple silicon) | `Tapinion-…-macos.dmg` | Open, drag Tapinion into *Applications* |
| Linux | `Tapinion-…-x86_64.AppImage` | Make executable, double-click |

Tapinion starts, opens the browser and guides you through five steps: **language →
administrator account → look (logo, colour, optional) → first event → connect the tablet**
(QR code). A small window shows that Tapinion is running; closing it stops Tapinion.

On Windows the installer also creates the firewall rule so tablets can connect, a desktop icon
and – if ticked – starts Tapinion at login. Uninstall via *Settings → Apps*; your data is kept
unless you choose to delete it.

**Tablets** (same Wi-Fi as the computer):

- **Android**: install `tapinion-android-….apk` from the releases (allow "install unknown apps"
  once), tap *Scan QR code*, enter the event's PIN. The app runs full screen, keeps the screen on
  and pins itself while the kiosk runs.
- **iPad / iPhone**: scan the QR code with the camera, enter the PIN, then *Share → Add to Home
  Screen*. For a locked-down kiosk: *Settings → Accessibility → Guided Access*.

Data lives in the user's application folder (`%APPDATA%\Tapinion`, `~/Library/Application Support/Tapinion`,
`~/.local/share/tapinion`): one SQLite file, easy to back up.

The downloads are not code-signed yet, so the first start shows a warning once:
Windows *"Windows protected your PC"* → *More info* → *Run anyway*;
macOS *"cannot be opened"* → *System Settings → Privacy & Security* → *Open Anyway*.

### On a server

**Docker** (image built from this repository):

```bash
docker compose up -d
```

Then open `http://<server>:8000/setup?token=<SETUP_TOKEN>` (see `docker-compose.yml`) or set
`ADMIN_USER` / `ADMIN_PASSWORD` for the first account. Put a reverse proxy with HTTPS in front
and set `COOKIE_SECURE=1`.

**Python** (3.11 or newer):

```bash
pip install .
tapinion serve --host 0.0.0.0 --port 8000
```

**Kubernetes**: [`deploy/kubernetes/tapinion.yaml`](deploy/kubernetes/tapinion.yaml) (one pod, SQLite on a volume).

### Configuration

| Variable | Meaning |
|---|---|
| `SECRET_KEY` | Long random string for session cookies (required on servers) |
| `DB_PATH` | SQLite file (default `data/tapinion.sqlite3`) |
| `ADMIN_USER`, `ADMIN_PASSWORD` | First administrator, created only if there are no users |
| `SETUP_TOKEN` | Allows the first-time setup at `/setup?token=…` from another computer |
| `COOKIE_SECURE` | `1` behind HTTPS |
| `PUBLIC_URL` | Address used in QR codes, e.g. `https://feedback.example.org` |
| `DEFAULT_LANG` | `en` or `de`, when the browser language is not supported |
| `SQLITE_WAL` | `0` on network file systems (NFS) |

## Roles

| | Organizer | Analyst | Administrator |
|---|:-:|:-:|:-:|
| See open events, start the kiosk, see/change PIN | ✓ | ✓ | ✓ |
| Create events | ✓ | ✓ | ✓ |
| Overall result (counts, score) | ✓ | ✓ | ✓ |
| All events, individual ratings, CSV, PDF reports | | ✓ | ✓ |
| Edit events, open/close, new kiosk link | | ✓ | ✓ |
| Delete events and individual ratings | | | ✓ |
| Users, appearance (name, logo, colours) | | | ✓ |

The organizer role suits a shared account on a tablet, e.g. for student assistants who set up
the kiosk but should not see individual ratings.

## Scores

- **Net Promoter Score** (0–10): promoters 9–10, passives 7–8, detractors 0–6;
  NPS = % promoters − % detractors.
- **Satisfaction balance** (smileys): % satisfied − % dissatisfied.

Both range from −100 to +100.

## Tools

```bash
tapinion create-user NAME --role admin     # password is asked
tapinion import-csv ratings.csv            # columns: event;date;time;rating (0-10 or happy/neutral/unhappy)
tapinion demo                              # two demo events (kiosk PIN 1234)
```

## Development

```bash
pip install -e ".[dev]"
python -m pytest
tapinion demo && tapinion serve
```

Stack: FastAPI, Jinja2 templates, [htmx](https://htmx.org) (vendored), SQLite, fpdf2 for PDFs.
Translations live in `tapinion/locales/*.json`; a new language is a new file.

Builds: desktop app with PyInstaller (`packaging/pyinstaller/tapinion.spec`), Windows installer with Inno Setup (`packaging/windows/tapinion.iss`), Android app with
Gradle (`android/`, `./gradlew assembleRelease`). GitHub Actions builds both for every release.

## Licence

Copyright © 2026 Markus Wilhelm, mw-research.
Tapinion is free software under the [GNU Affero General Public License v3.0 or later](LICENSE).
If you run a modified version for others over a network, you must offer them its source code.

See [ACKNOWLEDGMENTS.md](ACKNOWLEDGMENTS.md).
