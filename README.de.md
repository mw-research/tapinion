<p align="center"><img src="tapinion/static/logo.svg" alt="Tapinion" width="300"></p>

<p align="center"><b>Tap your opinion.</b> Feedback-Kiosk für Veranstaltungen, Empfang, Kantine und überall,
wo Menschen vorbeikommen: ein Tipp auf einen Smiley oder die Skala 0–10, Ergebnisse live, PDF-Berichte, Rollen.</p>

<p align="center"><a href="README.md">English</a> · <a href="#installation">Installation</a> · <a href="#rollen">Rollen</a> · <a href="LICENSE">AGPL-3.0</a></p>

---

## Funktionen

- **Kiosk** auf Tablet, Handy oder Laptop: Smileys (zufrieden / neutral / unzufrieden) oder die
  Weiterempfehlungsskala 0–10, Danke-Bildschirm, nach 4 Sekunden zurück zur Frage. Deutsch und
  Englisch, am Kiosk umschaltbar; die Frage lässt sich je Sprache festlegen.
- **PIN-geschützt**: Öffnen und Verlassen des Kiosks auf einem Gerät erfordern die PIN der
  Veranstaltung. Wer im Kiosk die URL kürzt, landet auf der Anmeldeseite, nie in der Auswertung.
- **Stimmen bleiben erhalten, wenn das Netz ausfällt**, und werden später mit ihrer Uhrzeit übertragen.
- **Auswertung** je Veranstaltung und Tag: Net Promoter Score bzw. Zufriedenheitssaldo (−100 bis +100),
  Gruppen, Einzelwerte, Bewertungen je Stunde, einzelne Bewertungen, Live-Aktualisierung, CSV-Export.
- **PDF-Berichte** zu einer oder vielen Veranstaltungen (Zeitraum, Abfrageart, auf Wunsch eine Seite je
  Veranstaltung), in der Sprache des Benutzers und mit Farben und Logo der Installation.
- **Rollen** für Veranstalter, Auswerter und Administratoren (siehe unten).
- **Eigene Gestaltung**: Administratoren legen Name, Logo und Farben (etwa im Corporate Design) in der App fest.
- **Läuft überall**: als Desktop-App auf einem Laptop (Tablets verbinden sich per QR-Code im selben Netz),
  als Android-Kiosk-App, in jedem Browser (iPad: zum Home-Bildschirm hinzufügen) oder auf einem Server
  mit Docker oder Kubernetes.

## Installation

### Ohne Server: Laptop und Tablets

| Rechner | Download unter [Releases](https://github.com/mw-research/tapinion/releases/latest) | |
|---|---|---|
| Windows 10/11 | `Tapinion-Setup-….exe` | Doppelklick, *Weiter*, *Weiter*, *Fertigstellen* |
| macOS (Apple-Chip) | `Tapinion-…-macos.dmg` | Öffnen, Tapinion in *Programme* ziehen |
| Linux | `Tapinion-…-x86_64.AppImage` | Ausführbar machen, doppelklicken |

Tapinion startet, öffnet den Browser und führt in fünf Schritten durch die Einrichtung:
**Sprache → Administratorkonto → Aussehen (Logo, Farbe, optional) → erste Veranstaltung →
Tablet verbinden** (QR-Code). Ein kleines Fenster zeigt, dass Tapinion läuft; wer es schließt,
beendet Tapinion.

Unter Windows legt der Installer auch die Firewall-Regel für die Tablets an, ein Desktop-Symbol
und – falls angehakt – den Autostart. Deinstallieren über *Einstellungen → Apps*; die Daten
bleiben erhalten, außer Sie wählen das Löschen.

**Tablets** (im selben WLAN wie der Rechner):

- **Android**: `tapinion-android-….apk` aus den Releases installieren (einmalig „Installation
  unbekannter Apps“ erlauben). Die App findet den Rechner im WLAN selbst – antippen, oder
  *QR-Code scannen* –, dann die PIN der Veranstaltung eingeben. Die App
  läuft im Vollbild, hält den Bildschirm an und heftet sich an, solange der Kiosk läuft. Sie ist die
  schlanke Ergänzung zum Programm auf dem Rechner: Jede in der App geöffnete Veranstaltung bleibt
  auf dem Gerät gespeichert (*Offline verfügbar*). Ein Tablet wird im Büro mit einmal QR-Code
  scannen vorbereitet; am Einsatzort läuft der Kiosk ohne den Rechner, auch nach einem Neustart,
  und die App zeigt die auf dem Gerät gesammelten Ergebnisse. Wieder in Reichweite des Rechners –
  auch unter neuer Adresse, die im WLAN neu gefunden wird – werden die Bewertungen automatisch
  übertragen (jede genau einmal). Veranstaltungen entstehen am Rechner; in der App lassen sie sich
  nur löschen.

  **Vollsperre** (empfohlen für Tablets im öffentlichen Raum): Standardmäßig schützt die
  Bildschirmfixierung von Android den Kiosk; ein Besucher kann sie lösen (*Zurück* und *Übersicht*
  halten). Mit der Vollsperre lässt sich ein laufender Kiosk nur mit der PIN verlassen – keine
  Home-Taste, kein App-Wechsel, keine Benachrichtigungen, kein Ein/Aus-Menü, kein Lösen der
  Fixierung, und nach einem Neustart öffnet sich der Kiosk von selbst wieder. Einmal pro Tablet,
  kostenlos: alle Konten auf dem Tablet entfernen (oder es zurücksetzen), USB-Debugging einschalten,
  mit einem Rechner mit den [Android-Plattform-Tools](https://developer.android.com/tools/releases/platform-tools)
  verbinden und ausführen:

  ```
  adb shell dpm set-device-owner io.github.mwresearch.tapinion/.KioskAdmin
  ```

  Der Startbildschirm der App zeigt dann *Vollsperre ist aktiv*. *Tablet freigeben* auf diesem
  Bildschirm schaltet sie wieder ab (danach lässt sich die App normal deinstallieren).
- **Der Rechner selbst**: *Kiosk auf diesem Rechner* im Tapinion-Fenster öffnet die Bewertung im
  Vollbild in einem eigenen Browserfenster (Edge unter Windows; Chrome oder Edge unter macOS/Linux);
  im normalen Browser bleiben Sie für die Auswertung angemeldet.
- **iPad / iPhone** (keine App nötig; eine App-Store-App setzt Apples kostenpflichtiges
  Entwicklerprogramm voraus): QR-Code mit der Kamera scannen, PIN eingeben, dann *Teilen → Zum
  Home-Bildschirm*. Für einen abgesicherten Kiosk: *Einstellungen → Bedienungshilfen → Geführter Zugriff*.

Die Daten liegen im Anwendungsordner des Benutzers (`%APPDATA%\Tapinion`,
`~/Library/Application Support/Tapinion`, `~/.local/share/tapinion`): eine SQLite-Datei, leicht zu sichern.

Die Downloads sind noch nicht codesigniert; beim ersten Start erscheint deshalb einmal eine Warnung:
Windows *„Der Computer wurde durch Windows geschützt“* → *Weitere Informationen* → *Trotzdem ausführen*;
macOS *„kann nicht geöffnet werden“* → *Systemeinstellungen → Datenschutz & Sicherheit* → *Dennoch öffnen*.

### Ohne gemeinsames WLAN: Tablets überall mit Internet

Für ein Tablet, das tagelang an einem Ausgang oder Empfang steht – mit Strom und Internet, aber
nicht im Netz Ihres Rechners: Tapinion auf einem über das Internet erreichbaren Server mit HTTPS
betreiben (siehe *Auf einem Server*) und `PUBLIC_URL` setzen. Veranstaltung anlegen, ihren QR-Code
einmal mit dem Tablet scannen, PIN eingeben und dem Gerät einen Namen geben, etwa *Ausgang Nord*.
Danach gilt:

- nach einem Neustart oder Neuladen setzt das Tablet den Kiosk selbst fort – ohne PIN, bis es mit
  der PIN verlassen oder unter *Veranstaltungen → Geräte* abgemeldet wird;
- bei Internetausfällen bleiben Bewertungen mit ihrer Uhrzeit auf dem Tablet und werden später
  übertragen; über HTTPS öffnet sich die Kiosk-Seite auch ohne Internet;
- *Veranstaltungen → Geräte* zeigt jedes Gerät, wann es zuletzt aktiv war und wie viele Bewertungen
  es gesammelt hat; die Auswertung zeigt den Anteil je Gerät.

Beliebig viele Geräte können für dieselbe Veranstaltung sammeln, etwa an mehreren Eingängen.

### Auf einem Server

**Docker** (Abbild aus diesem Repository):

```bash
docker compose up -d
```

Dann `http://<server>:8000/setup?token=<SETUP_TOKEN>` öffnen (siehe `docker-compose.yml`) oder für das
erste Konto `ADMIN_USER` / `ADMIN_PASSWORD` setzen. Einen Reverse Proxy mit HTTPS davorschalten und
`COOKIE_SECURE=1` setzen.

**Python** (ab 3.11):

```bash
pip install .
tapinion serve --host 0.0.0.0 --port 8000
```

**Kubernetes**: [`deploy/kubernetes/tapinion.yaml`](deploy/kubernetes/tapinion.yaml) (ein Pod, SQLite auf einem Volume).

Die Umgebungsvariablen stehen in der [englischen README](README.md#configuration).

## Rollen

| | Veranstalter | Auswerter | Administrator |
|---|:-:|:-:|:-:|
| Offene Veranstaltungen sehen, Kiosk starten, PIN ansehen/ändern | ✓ | ✓ | ✓ |
| Veranstaltungen anlegen | ✓ | ✓ | ✓ |
| Gesamtergebnis (Anzahlen, Score) | ✓ | ✓ | ✓ |
| Alle Veranstaltungen, einzelne Bewertungen, CSV, PDF-Berichte | | ✓ | ✓ |
| Veranstaltungen bearbeiten, öffnen/schließen, neuer Kiosk-Link | | ✓ | ✓ |
| Veranstaltungen und einzelne Bewertungen löschen | | | ✓ |
| Benutzer, Darstellung (Name, Logo, Farben) | | | ✓ |

Die Rolle Veranstalter eignet sich für ein gemeinsames Konto am Tablet, etwa für Hilfskräfte, die den
Kiosk aufbauen, aber keine einzelnen Bewertungen sehen sollen.

## Kennzahlen

- **Net Promoter Score** (0–10): Promotoren 9–10, Indifferente 7–8, Detraktoren 0–6;
  NPS = % Promotoren − % Detraktoren.
- **Zufriedenheitssaldo** (Smileys): % zufrieden − % unzufrieden.

Beide reichen von −100 bis +100.

## Lizenz

Copyright © 2026 Markus Wilhelm, mw-research.
Tapinion ist freie Software unter der [GNU Affero General Public License v3.0 oder später](LICENSE).
Wer eine veränderte Fassung anderen über ein Netzwerk anbietet, muss ihnen den Quellcode zugänglich machen.

Siehe [ACKNOWLEDGMENTS.md](ACKNOWLEDGMENTS.md).
