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
  unbekannter Apps“ erlauben), *QR-Code scannen* antippen, PIN der Veranstaltung eingeben. Die App
  läuft im Vollbild, hält den Bildschirm an und heftet sich an, solange der Kiosk läuft.
- **iPad / iPhone**: QR-Code mit der Kamera scannen, PIN eingeben, dann *Teilen → Zum
  Home-Bildschirm*. Für einen abgesicherten Kiosk: *Einstellungen → Bedienungshilfen → Geführter Zugriff*.

Die Daten liegen im Anwendungsordner des Benutzers (`%APPDATA%\Tapinion`,
`~/Library/Application Support/Tapinion`, `~/.local/share/tapinion`): eine SQLite-Datei, leicht zu sichern.

Die Downloads sind noch nicht codesigniert; beim ersten Start erscheint deshalb einmal eine Warnung:
Windows *„Der Computer wurde durch Windows geschützt“* → *Weitere Informationen* → *Trotzdem ausführen*;
macOS *„kann nicht geöffnet werden“* → *Systemeinstellungen → Datenschutz & Sicherheit* → *Dennoch öffnen*.

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
