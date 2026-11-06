# Procurator Capsularum

**Dateien umbenennen, verschieben und konvertieren, mit Vorschau vor jeder Aktion und Rückgängig für jeden Lauf.**

Procurator Capsularum bündelt, was man regelmässig mit vielen Dateien und Büchern tut: Ordner wählen,
Aktion wählen, in einer Vorschau prüfen, was passieren würde, und erst dann ausführen. Alles läuft lokal
auf deinem Rechner, als Web-Oberfläche im Browser oder auf der Kommandozeile. Eine Desktop-App ist geplant.

> **Stand:** frühe Version (0.1), in Entwicklung. Entwickelt und getestet unter macOS. Mach vor dem ersten
> Einsatz auf wichtigen Daten ein Backup und lies immer die Vorschau.

## Was es kann

| Bereich | Funktionen |
|---|---|
| **Umbenennen** | Text ersetzen (erster, letzter, alle Treffer), Wildcard (`*`, `?`), regulärer Ausdruck mit `$1`-Rückverweisen, Anhängen, Voranstellen, Zeichen entfernen und einfügen, Gross-/Kleinschreibung, Laufnummer (mit eigener Reihenfolge per Ziehen), Datum |
| **Verschieben** | In einen anderen Ordner, flach oder mit nachgebauter Ordnerstruktur. Zielordner werden angelegt, auch auf ein anderes Laufwerk |
| **Konvertieren** | CBR → CBZ (Seiten bleiben bitidentisch), Bilder (JPG, PNG, WebP, HEIC, TIFF, BMP → JPG, PNG, WebP, optional verkleinern) |
| **Dubletten** | Lokaler Datei-Index mit Hashes, findet gleiche Dateien und liest dafür so wenig wie möglich |
| **Sicherheit** | Konflikterkennung (gleiche Zielnamen, vorhandene Dateien werden nie überschrieben), Verlauf mit Rückgängig, sensible Dateien werden markiert |
| **Oberfläche** | Vorschau-Tabelle mit Checkbox pro Zeile, Fortschritt und Abbrechen bei langen Läufen, gespeicherte Einstellungen |

Konvertierungen erzeugen neue Dateien, die Originale bleiben unverändert.

## Voraussetzungen

- [Python](https://www.python.org/) 3.11 oder neuer und [uv](https://docs.astral.sh/uv/)
- [Node.js](https://nodejs.org/) 20.19 oder neuer (oder 22.12 oder neuer), nur um die Web-Oberfläche zu bauen
- Optional: [unar](https://theunarchiver.com/command-line) für CBR/RAR (macOS: `brew install unar`)
- Optional: [Ollama](https://ollama.com/) für die geplanten KI-Vorschläge. Sie sind noch nicht gebaut, die Verbindung lässt sich aber schon testen

## Installation und Start

```bash
git clone https://github.com/richi-sixt/procurator-capsularum.git
cd procurator-capsularum
uv sync
```

Web-Oberfläche einmalig bauen und starten:

```bash
cd web && npm install && npm run build && cd ..
uv run pc serve
```

Dann im Browser <http://127.0.0.1:8765> öffnen. Ohne die Oberfläche läuft auch die Kommandozeile (siehe unten).

## Benutzung

### Web-Oberfläche

1. **Ordner** wählen (Pfad eintippen oder «Wählen …», auch mehrere, optional mit Unterordnern). Die Dateien erscheinen sofort.
2. **Aktion** wählen und ausfüllen. Die Vorschau zeigt pro Datei alt und neu, den Status (bereit, übersprungen, Konflikt, Fehler) und den Grund.
3. Einzelne Zeilen abwählen, wenn sie nicht betroffen sein sollen, dann **ausführen**.
4. Unter **Verlauf** lässt sich jeder Lauf rückgängig machen. Bei Konvertierungen werden dabei die erzeugten Dateien gelöscht.

### Kommandozeile

Jeder Befehl zeigt zuerst nur die Vorschau. Erst mit `--apply` wird etwas verändert.

```bash
uv run pc rename replace ORDNER -f " " -t "_"             # Vorschau
uv run pc rename replace ORDNER -f " " -t "_" --apply     # ausführen
uv run pc rename sequence ORDNER --label Urlaub --position replace --sort name
uv run pc move ORDNER -r --to ZIEL --keep-structure --apply
uv run pc convert cbr2cbz QUELLE --to ZIEL --apply
uv run pc convert images ORDNER --to ZIEL --format webp --max-edge 1600 --apply
uv run pc duplicates ORDNER
uv run pc history
uv run pc undo
```

Alle Befehle: `uv run pc --help`. Nützliche Optionen: `-r` (Unterordner einbeziehen), `--with-ext`
(Endung mitbearbeiten), `--force-unique` (bei Kollision Nummer anhängen), `--all` (auch übersprungene
Dateien zeigen).

<details>
<summary>Alle Befehle im Überblick</summary>

| Befehl | Zweck |
|---|---|
| `pc rename replace` / `wildcard` / `regex` | Text im Namen ersetzen |
| `pc rename append` / `prepend` | Text anhängen oder voranstellen |
| `pc rename remove` / `insert` | Zeichen entfernen oder einfügen |
| `pc rename case` | Gross-/Kleinschreibung ändern |
| `pc rename sequence` / `date` | Laufnummer oder Datum einfügen |
| `pc move` | In einen anderen Ordner verschieben |
| `pc convert cbr2cbz` / `images` | Dateien konvertieren |
| `pc index` / `pc duplicates` | Datei-Index pflegen, gleiche Dateien anzeigen |
| `pc sensitive` | Zeigt, welche Dateien als sensibel gelten |
| `pc config` | Pfad und Werte der Konfiguration anzeigen |
| `pc history` / `pc undo` | Verlauf anzeigen, Lauf rückgängig machen |
| `pc serve` | Web-Oberfläche starten |

</details>

### Verschieben und Konvertieren im Detail

- **Auf ein anderes Laufwerk** wird kopiert, Byte für Byte geprüft und erst dann das Original gelöscht. Bei einem Fehler bleibt das Original liegen.
- **Zielordner bei Konvertierungen:** Ohne Angabe liegt das Ergebnis neben der Quelle, mit Zielordner wird die Ordnerstruktur der Quelle dort nachgebaut. Vorhandene Ziele werden übersprungen, ein abgebrochener Lauf lässt sich also fortsetzen.
- **Rückgängig beim Verschieben** holt die Dateien zurück und entfernt die dabei angelegten, leeren Ordner.
- **Rückgängig bei Konvertierungen** löscht die erzeugten Dateien. Die Kommandozeile fragt vorher nach (`pc undo --yes` überspringt die Frage), die Originale bleiben unverändert.

## Datenschutz und Sicherheit

- Der Server hört nur auf `127.0.0.1`, prüft den Host-Header und erlaubt keine fremden Webseiten (kein CORS).
- Der Browser schickt nie fertige Zielnamen, nur Parameter. Der Server berechnet den Plan beim Ausführen neu.
- Es werden keine Daten ins Internet gesendet. Die geplante KI-Anbindung nutzt standardmässig ein lokales Modell (Ollama). Bei einem Cloud-Anbieter braucht jeder Lauf eine Freigabe.
- **Sensible Dateien** (Schlüsselwörter wie Pass, Steuer, Konto oder Endungen wie `.pem`) werden in der Vorschau mit 🔒 markiert und würden nie an ein Cloud-Modell gesendet. Die Listen sind in den Einstellungen änderbar.
- **Schlüssel stehen nie in einer Datei.** Für Claude wird nur der Name der Umgebungsvariable gespeichert.

### Wo Daten liegen

Konfiguration, Verlauf (Journal) und Datei-Index liegen im Benutzerordner, nicht im Projekt. Unter macOS
ist das `~/Library/Application Support/procurator-capsularum/`. Die genauen Pfade zeigen
`uv run pc config` und `uv run pc index --info`. Der Index enthält nur Pfade, Grössen, Zeitstempel und
Hashes, nie Dateiinhalte. Für Tests und eigene Experimente lassen sich die Orte mit den
Umgebungsvariablen `PC_CONFIG`, `PC_JOURNAL` und `PC_INDEX` überschreiben.

## Entwicklung

```bash
uv run pytest                      # Python-Tests
uv run ruff check .                # Stil und Fehler
cd web && npm run build            # Typen prüfen und Oberfläche bauen
cd web && npm run lint
```

Mit Hot-Reload für die Oberfläche: `uv run pc serve` und in einem zweiten Terminal `cd web && npm run dev`
(<http://localhost:5173>, Vite leitet `/api` an Port 8765 weiter).

### Aufbau

```
src/procurator/
  model.py  scanner.py     Datei-Objekte, Ordner einlesen
  ops/                     Operationen: rename, move, convert, Register mit Formular-Beschreibung
  engine.py                Plan berechnen (Konflikte) und ausführen
  fsops.py  journal.py     sicheres Verschieben, Verlauf und Rückgängig (SQLite)
  index.py                 Datei-Index und Dubletten
  config.py  privacy.py    Konfiguration, sensible Dateien
  server/                  FastAPI-Server (nur lokal)
  cli.py                   Kommandozeile `pc`
web/                       React-Oberfläche (Vite, TypeScript)
tests/
```

**Kernidee:** Jede Operation berechnet zuerst einen Plan (alt → neu, Status, Grund) und verändert dabei
nichts. Erst das Ausführen schreibt auf die Platte, atomar und mit Eintrag im Journal. Vorschau,
Konflikterkennung und Rückgängig funktionieren deshalb für jede Operation gleich.

**Neue Operation hinzufügen:**

1. Eine Klasse in `src/procurator/ops/` schreiben, die `Operation` erweitert (`transform` liefert den neuen Namen, `destination` den Zielpfad, Konvertierungen zusätzlich `convert`).
2. In `src/procurator/ops/registry.py` mit ihren Formularfeldern eintragen. Die Oberfläche baut das Formular daraus selbst.
3. Tests in `tests/` ergänzen (Plan, Konflikte, Ausführen, Rückgängig).

## Bekannte Einschränkungen

- Nur unter macOS getestet. Linux funktioniert vermutlich, Windows ist ungetestet.
- Die Vorschau-Tabelle ist nicht virtualisiert und wird bei Zehntausenden Dateien langsam.
- Ein Undo, das nur teilweise gelingt, lässt sich nicht wiederholen.
- Die KI-Vorschläge zum Ordnen sind noch nicht gebaut.

## Geplant

Dubletten verschieben, KI-Vorschläge zum Ordnen mit einem lokalen Modell, PDF → Markdown,
EPUB-Konvertierung und eine Desktop-App.

## Lizenz

Copyright © 2026 Rüchan Sixt

Dieses Programm steht unter der [GNU Affero General Public License, Version 3 oder neuer](LICENSE)
(AGPL-3.0-or-later). Du darfst es nutzen, ändern und weitergeben. Gibst du es geändert weiter, oder
bietest du eine geänderte Version als Dienst über ein Netzwerk an, musst du den Quellcode deiner Änderungen
unter derselben Lizenz offenlegen und den Copyright-Hinweis erhalten. Es gibt keine Gewährleistung.
