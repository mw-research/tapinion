# Changelog

## 1.0.0 – 2026-11-13

First public version.

- Kiosk with smileys or 0–10 scale, German and English, question per language.
- PIN to open and leave a kiosk; open kiosks listed on the login page; a kiosk device is never logged in.
- Votes are buffered on the device when the network drops and sent later with their time.
- Roles organizer, analyst, administrator.
- Results per event and day, individual ratings (delete for administrators), CSV export.
- PDF reports for one or many events, in German or English.
- Settings: name, logo, colours, users.
- Setup wizard: language, administrator account, look, first event, connect the tablet.
- Installers: Windows setup (shortcuts, optional autostart, firewall rule), macOS disk image, Linux AppImage.
- Desktop app with QR codes for tablets in the same network; a second start opens the running instance.
- Android kiosk app (full screen, screen on, optional app pinning, QR setup).
- Docker image and Kubernetes manifest.
