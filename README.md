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
  once). The app finds the computer in the Wi-Fi by itself – tap it, or tap *Scan QR code* –
  then enter the event's PIN. The app runs full screen, keeps the screen on
  and pins itself while the kiosk runs. It is the slim companion of the computer program: every event opened in the app is
  kept on the device (*Available offline*). Prepare a tablet in the office by scanning the QR code
  once; at the venue it runs the kiosk without the computer, also after a restart, and the app
  shows the results collected on the device. Back in reach of the computer – also at a new
  address, found again in the Wi-Fi – the ratings are sent automatically (each exactly once).
  Events are created on the computer; in the app they can only be deleted.
- **The computer itself**: *Kiosk on this computer* in the Tapinion window opens the rating screen
  full screen in its own browser window (Edge on Windows; Chrome or Edge on macOS/Linux), while you
  stay logged in in your normal browser.
- **iPad / iPhone** (no app needed; an App Store app would require Apple's paid developer program):
  scan the QR code with the camera, enter the PIN, then *Share → Add to Home
  Screen*. For a locked-down kiosk: *Settings → Accessibility → Guided Access*.

Data lives in the user's application folder (`%APPDATA%\Tapinion`, `~/Library/Application Support/Tapinion`,
`~/.local/share/tapinion`): one SQLite file, easy to back up.

The downloads are not code-signed yet, so the first start shows a warning once:
Windows *"Windows protected your PC"* → *More info* → *Run anyway*;
macOS *"cannot be opened"* → *System Settings → Privacy & Security* → *Open Anyway*.

### Without a shared Wi-Fi: tablets anywhere with internet

For a tablet that stays at an exit or reception for days – with power and internet, but not in
the network of your computer: run Tapinion on a server reachable over the internet with HTTPS
(see *On a server*) and set `PUBLIC_URL`. Create the event, scan its QR code with the tablet once,
enter the PIN and give the device a name, e.g. *Exit north*. From then on:

- after a restart or reload the tablet continues the kiosk by itself – no PIN, until it is left
  with the PIN or switched off under *Events → Devices*;
- during internet outages ratings are kept on the tablet with their time and sent later; on HTTPS
  the kiosk page also opens without internet;
- *Events → Devices* shows every device, when it was last seen and how many ratings it collected;
  the results show the share per device.

Any number of devices can collect for the same event, e.g. at several entrances.

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
