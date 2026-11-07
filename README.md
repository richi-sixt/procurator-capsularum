# Procurator Capsularum

[![CI](https://github.com/richi-sixt/procurator-capsularum/actions/workflows/ci.yml/badge.svg)](https://github.com/richi-sixt/procurator-capsularum/actions/workflows/ci.yml)

Procurator Capsularum bündelt, was man regelmässig mit vielen Dateien und Büchern tut: Ordner wählen,
Aktion wählen, in einer Vorschau prüfen, was passieren würde, und erst dann ausführen. Alles läuft lokal
auf deinem Rechner, als Web-Oberfläche im Browser oder auf der Kommandozeile. Unter macOS lässt sich auch eine Desktop-App bauen.

> **Dokumentation:** [Anleitung](docs/anleitung.md) für Anwender, [Entwicklung](docs/entwicklung.md) für alle, die am Code arbeiten.
>
> **Stand:** frühe Version (0.1), in Entwicklung. Entwickelt und getestet unter macOS. Mach vor dem ersten
> Einsatz auf wichtigen Daten ein Backup und lies immer die Vorschau.

## Was es kann

| Bereich | Funktionen |
|---|---|
| **Umbenennen** | Text ersetzen (erster, letzter, alle Treffer), Wildcard (`*`, `?`), regulärer Ausdruck mit `$1`-Rückverweisen, Anhängen, Voranstellen, Zeichen entfernen und einfügen, Gross-/Kleinschreibung, Laufnummer (mit eigener Reihenfolge per Ziehen), Name aus Vorlage (zum Beispiel `{date:%Y%m%d_%H-%M-%S}_{size}`), Datum (automatisch aus dem Aufnahmedatum der Fotos, sonst aus dem ältesten Dateidatum, nie vom Ausführungstag) |
| **Verschieben** | In einen anderen Ordner, flach oder mit nachgebauter Ordnerstruktur. Zielordner werden angelegt, auch auf ein anderes Laufwerk |
| **Nach Regeln sortieren** | Ohne KI in Ordner nach Vorlage sortieren, zum Beispiel `{type}/{date:%Y}` ergibt `Bilder/2024`. Platzhalter: Datum (bei Fotos das Aufnahmedatum), Dateityp, Endung, Anfangsbuchstabe, bisheriger Ordner |
| **Konvertieren** | CBR → CBZ (Seiten bleiben bitidentisch), Bilder (JPG, PNG, WebP, HEIC, TIFF, BMP → JPG, PNG, WebP, optional verkleinern) |
| **Dubletten** | Findet gleiche Dateien über ihren Inhalt und verschiebt alle bis auf eine in einen Ordner `_Dubletten`, nichts wird gelöscht. Ein lokaler Datei-Index sorgt dafür, dass so wenig wie möglich gelesen wird |
| **KI-Vorschläge** | Ein Sprachmodell schlägt Ordner und bessere Dateinamen vor, du prüfst und korrigierst in der Vorschau. Standardmässig mit einem lokalen Modell ([Ollama](https://ollama.com/)), optional mit Claude. Sensible Dateien werden nie gesendet. Die App lernt aus deinen Entscheidungen (angenommen, abgelehnt, korrigiert), lokal gespeichert und löschbar |
| **Sicherheit** | Konflikterkennung (gleiche Zielnamen, vorhandene Dateien werden nie überschrieben), Verlauf mit Rückgängig, sensible Dateien werden markiert |
| **Oberfläche** | Vorschau-Tabelle mit Checkbox pro Zeile, Fortschritt und Abbrechen bei langen Läufen, gespeicherte Einstellungen |

Konvertierungen erzeugen neue Dateien, die Originale bleiben unverändert.

## Voraussetzungen

- [Python](https://www.python.org/) 3.11 oder neuer und [uv](https://docs.astral.sh/uv/)
- [Node.js](https://nodejs.org/) 20.19 oder neuer (oder 22.12 oder neuer), nur um die Web-Oberfläche zu bauen
- Optional: [unar](https://theunarchiver.com/command-line) für CBR/RAR (macOS: `brew install unar`)
- Optional: [Ollama](https://ollama.com/) mit einem heruntergeladenen Modell für die KI-Vorschläge (`ollama pull gemma4:e2b`)
- Optional: für Claude als Cloud-Modell `uv sync --extra claude` und die Umgebungsvariable `ANTHROPIC_API_KEY`

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

Unter macOS lässt sich daraus auch eine **Desktop-App** mit eigenem Fenster bauen (`desktop/build.sh`, siehe [desktop/README.md](desktop/README.md)).

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
uv run pc duplicates ORDNER                    # gleiche Dateien anzeigen
uv run pc duplicates ORDNER --move             # Kopien verschieben (Vorschau, mit --apply ausführen)
uv run pc organize ORDNER                      # KI-Vorschläge für Ordner und Namen (Vorschau)
uv run pc organize ORDNER --hint "Dokumente nach Jahr" --apply
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
| `pc sort '{type}/{date:%Y}' ORDNER` | Ohne KI nach festen Regeln in Ordner sortieren: `{date}`, `{type}`, `{ext}`, `{initial}`, `{folder}`, mit `--to` in einen anderen Ordner |
| `pc rename template '{date:%Y%m%d_%H-%M-%S}_{size}' ORDNER` | Namen aus einer Vorlage bauen: `{date}`, `{size}`, `{name}`, `{ext}`, `{n}`, `{folder}` |
| `pc move` | In einen anderen Ordner verschieben |
| `pc convert cbr2cbz` / `images` | Dateien konvertieren |
| `pc index` / `pc duplicates` | Datei-Index pflegen, gleiche Dateien anzeigen oder mit `--move` verschieben |
| `pc sensitive` | Zeigt, welche Dateien als sensibel gelten |
| `pc config` | Pfad und Werte der Konfiguration anzeigen |
| `pc learned [--clear]` | Zeigt, was aus deinen Entscheidungen gemerkt wurde (nur lokal), oder löscht es |
| `pc about` / `pc --version` | Version, Autor, Lizenz und die Lizenzen der Bausteine (`--licenses`) |
| `pc history` / `pc undo` | Verlauf anzeigen, Lauf rückgängig machen |
| `pc serve` | Web-Oberfläche starten |

</details>

### Verschieben und Konvertieren im Detail

- **Auf ein anderes Laufwerk** wird kopiert, Byte für Byte geprüft und erst dann das Original gelöscht. Bei einem Fehler bleibt das Original liegen.
- **Zielordner bei Konvertierungen:** Ohne Angabe liegt das Ergebnis neben der Quelle, mit Zielordner wird die Ordnerstruktur der Quelle dort nachgebaut. Vorhandene Ziele werden übersprungen, ein abgebrochener Lauf lässt sich also fortsetzen.
- **Rückgängig beim Verschieben** holt die Dateien zurück und entfernt die dabei angelegten, leeren Ordner.
- **Rückgängig bei Konvertierungen** löscht die erzeugten Dateien. Die Kommandozeile fragt vorher nach (`pc undo --yes` überspringt die Frage), die Originale bleiben unverändert.

### Dubletten im Detail

- **Gleich heisst gleicher Inhalt**, nicht gleicher Name. Verglichen wird über einen lokalen Index: erst die Grösse, dann die ersten 64 KB, erst bei Gleichstand der ganze Inhalt (SHA-256). Unveränderte Dateien werden nie erneut gelesen.
- **Zwei Schritte:** Das Lesen der Dateien heisst «Analysieren» und läuft mit Fortschritt im Hintergrund (in der Oberfläche ein Knopf, auf der Kommandozeile automatisch bei `--move`). Die Vorschau selbst liest nichts und bleibt schnell.
- **Pro Gruppe bleibt genau eine Datei liegen.** Welche, bestimmst du: die älteste (Standard), die neueste, die mit dem kürzesten Pfad oder die erste alphabetisch.
- **Verschoben, nicht gelöscht:** Die Kopien landen in `_Dubletten` im gewählten Ordner (oder in einem Zielordner deiner Wahl), mit nachgebauter Ordnerstruktur. Löschen kannst du sie danach selbst. «Rückgängig» holt sie zurück.
- Mehrere gewählte Ordner werden miteinander verglichen. Hardlinks und Symlinks gelten nicht als Kopien, leere Dateien auch nicht.

### KI-Vorschläge im Detail

- **Zwei Schritte:** «Analysieren» befragt das Modell (im Hintergrund, mit Fortschritt und Abbrechen) und speichert die Vorschläge lokal. Die Vorschau liest nur diese gespeicherten Vorschläge, sie ruft das Modell nie auf. Bekannte, unveränderte Dateien werden nicht erneut gefragt.
- **Du behältst die Kontrolle:** Jede Zeile hat eine Checkbox, und das Ziel lässt sich mit ✎ von Hand ändern (`Ordner/Name`). Danach «Rückgängig» wie bei jeder Aktion. Ein leerer Ordnervorschlag lässt die Datei, wo sie liegt.
- **Vorschläge werden geprüft, bevor sie gelten:** Ein Pfad ausserhalb des gewählten Ordners, absolute Pfade, `..`, versteckte Ordner und eine geänderte Dateiendung werden nie übernommen. Unbrauchbare Vorschläge erscheinen als Fehler und werden nicht ausgeführt.
- **Was gesendet wird, bestimmt die Datenschutzstufe** (Einstellungen): Stufe 0 nur Dateiname, Endung, Grösse und Datum. Stufe 1 zusätzlich die Ordnernamen. Stufe 2 zusätzlich einen kurzen Textauszug aus Textdateien, PDF und Office-Dateien (`.docx`, `.xlsx`, `.pptx`).
- **Sensible Dateien gehen nicht ans Modell**, auch ihre Namen nicht. Nur bei einem lokalen Modell lässt sich das in den Einstellungen bewusst abschalten.
- **Lernen aus Entscheidungen:** Nach dem Anwenden merkt sich die App, was du übernommen, in der Vorschau abgewählt oder von Hand korrigiert hast. Bei der nächsten Analyse bekommt das Modell daraus Gewohnheiten («.pdf kommt meist nach Rechnungen») und wenige Beispiele mit. Gemerkt wird nur auf deinem Rechner, sensible Dateien nie. Bei Cloud gehen Beispiele erst ab Datenschutzstufe 1 mit und stehen in der Freigabe. Ausschalten in den Einstellungen, ansehen und löschen mit `pc learned`. Über die Kommandozeile (`pc organize --apply`) wird nichts gemerkt, dort fehlt die Prüfung in der Vorschau.
- **Cloud nur mit Bestätigung:** Bei Claude zeigt ein Dialog vor jedem Lauf, was gesendet würde (Anzahl, Stufe, erste Einträge). Auf der Kommandozeile fragt `pc organize` nach oder verlangt `--yes-cloud`.
- **Die Qualität hängt vom Modell ab.** Kleine lokale Modelle ordnen grob richtig, liegen aber gelegentlich daneben, und ihre «Sicherheit» sagt wenig aus. Mit «Eigene Anweisung» (`--hint`) lässt sich das Ergebnis steuern.

## Datenschutz und Sicherheit

- Der Server hört nur auf `127.0.0.1`, prüft den Host-Header und erlaubt keine fremden Webseiten (kein CORS).
- Der Browser schickt nie fertige Zielnamen, nur Parameter. Der Server berechnet den Plan beim Ausführen neu.
- Ohne KI-Vorschläge werden keine Daten ins Internet gesendet. Die KI-Vorschläge nutzen standardmässig ein lokales Modell (Ollama), dabei verlassen die Daten den Rechner nicht. Bei einem Cloud-Anbieter (Claude) braucht jeder Lauf eine Bestätigung.
- **Sensible Dateien** (Schlüsselwörter wie Pass, Steuer, Konto oder Endungen wie `.pem`) werden in der Vorschau mit 🔒 markiert und nie an ein Cloud-Modell gesendet. Die Listen sind in den Einstellungen änderbar.
- **Schlüssel stehen nie in einer Datei.** Für Claude wird nur der Name der Umgebungsvariable gespeichert.

### Wo Daten liegen

Konfiguration, Verlauf (Journal) und Datei-Index liegen im Benutzerordner, nicht im Projekt. Unter macOS
ist das `~/Library/Application Support/procurator-capsularum/`. Die genauen Pfade zeigen
`uv run pc config` und `uv run pc index --info`. Der Index enthält nur Pfade, Grössen, Zeitstempel und
Hashes, nie Dateiinhalte. Für Tests und eigene Experimente lassen sich die Orte mit den
Umgebungsvariablen `PC_CONFIG`, `PC_JOURNAL` und `PC_INDEX` überschreiben.

## Entwicklung

Ausführlicher in [docs/entwicklung.md](docs/entwicklung.md).

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
  ai/                      KI-Anbindung: Anbieter (Ollama, Claude), Vorschläge, Prüfung der Antworten
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
- Die Vorschau-Tabelle zeichnet ab 200 Zeilen nur die sichtbaren. Mit 20000 Dateien steht sie nach etwa zwei Sekunden, die Berechnung des Plans auf dem Server und das Übertragen brauchen dabei den grössten Teil. Gemessen ist das nur auf macOS.
- Ein Undo, das nur teilweise gelingt, lässt sich nicht wiederholen.
- KI-Vorschläge: Die Ollama-Anbindung ist mit einem echten Modell getestet. Die Claude-Anbindung ist automatisch nur mit simulierten Antworten getestet und vom Autor einmal von Hand mit der echten API ausprobiert. Messungen zur Geschwindigkeit stehen noch aus.
- Stufe 2 der Datenschutzstufen liest keinen Text aus gescannten PDF (keine Texterkennung) und nicht aus alten Office-Formaten (`.doc`, `.xls`, `.ppt`).
- Manche Ollama-Runner (zum Beispiel MLX) unterstützen kein erzwungenes Antwortformat. Dann liest das Programm die Antwort tolerant, was etwas fehleranfälliger ist.

## Geplant

PDF → Markdown und EPUB-Konvertierung.

## Lizenz

Copyright © 2026 Rüchan Sixt

Dieses Programm steht unter der [GNU Affero General Public License, Version 3 oder neuer](LICENSE)
(AGPL-3.0-or-later). Die Oberfläche zeigt Version, Lizenz, Credits und die Lizenzen der verwendeten Bausteine unter
«Über das Programm» (auf der Kommandozeile `pc about`). Du darfst es nutzen, ändern und weitergeben. Gibst du es geändert weiter, oder
bietest du eine geänderte Version als Dienst über ein Netzwerk an, musst du den Quellcode deiner Änderungen
unter derselben Lizenz offenlegen und den Copyright-Hinweis erhalten. Es gibt keine Gewährleistung.
