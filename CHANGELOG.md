# Changelog

## 1.0.0 – 2026-11-13

First public version.

- Kiosk with smileys or 0–10 scale, German and English, question per language.
- PIN to open and leave a kiosk; open kiosks listed on the login page; a kiosk device is never logged in.
- Votes are buffered on the device when the network drops and sent later with their time.
- Kiosk devices: own key per device, optional name, any number per event; resume after restart without PIN;
  device list with last seen, ratings per device, switch off; ratings per device in the results.
- Offline cache (service worker, HTTPS): the kiosk page opens without internet; queued votes survive expired sessions.
- Roles organizer, analyst, administrator.
- Results per event and day, individual ratings (delete for administrators), CSV export.
- PDF reports for one or many events, in German or English.
- Settings: name, logo, colours, users.
- Setup wizard: language, administrator account, look, first event, connect the tablet.
- Installers: Windows setup (shortcuts, optional autostart, firewall rule), macOS disk image, Linux AppImage.
- Desktop app with QR codes for tablets in the same network; a second start opens the running instance.
- Android kiosk app: finds Tapinion in the Wi-Fi by itself (DNS-SD), QR code as main action, full screen, screen on, optional app pinning;
  offline mode: events opened in the app are kept on the device (own device key), the kiosk runs without
  the computer, results on the device, sync of ratings exactly once when the computer is reachable again;
  finds a computer with a new address again in the Wi-Fi (installation id); events can be deleted in the app.
  Never waits on an unreachable computer: short connection check that can be cancelled, then the offline kiosk
  or the start screen; back leaves loading and PIN pages. A running kiosk is left with the PIN only, also when
  the connection drops or the app restarts (cancel then continues the kiosk offline).
  Full lock as device owner (set up once per tablet with adb): a running kiosk can only be left with the
  PIN – no home, recent apps, notifications, power menu or unpinning; it opens again after a restart.
- Device sync API (`/api/kiosk/<token>`, `/pair`, `/votes`) and installation id in `/healthz`.
- Kiosk on the base computer: full-screen browser window from the desktop app; full-screen button in the kiosk.
- Docker image and Kubernetes manifest.
