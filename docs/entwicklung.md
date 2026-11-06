# Entwicklung

Diese Seite ist für alle, die am Code arbeiten wollen. Wie man das Programm benutzt, steht in der
[Anleitung](anleitung.md).

## Entwicklungsumgebung

```bash
uv sync                          # Python-Abhängigkeiten (inklusive Entwicklungswerkzeuge)
cd web && npm install && cd ..   # Oberfläche
```

```bash
uv run pytest                    # Python-Tests
uv run ruff check .              # Stil und Fehler
cd web && npm run build          # Typen prüfen (tsc) und Oberfläche bauen
cd web && npm run lint
```

Mit Hot-Reload für die Oberfläche: `uv run pc serve` in einem Terminal und `cd web && npm run dev` in einem
zweiten (<http://localhost:5173>, Vite leitet `/api` an Port 8765 weiter). Ohne den Dev-Server liefert
`pc serve` den gebauten Ordner `web/dist` aus. Änderungen am Quelltext kommen dort erst nach `npm run build` an.

Die Tests lesen und schreiben nie die echte Konfiguration oder den echten Index. Eine `autouse`-Fixture in
`tests/conftest.py` setzt dafür `PC_CONFIG` und `PC_INDEX` auf temporäre Dateien, den Verlauf legt die
Fixture `journal` in einem temporären Ordner an. Mit `PC_CONFIG`, `PC_JOURNAL` und `PC_INDEX` lässt sich auch
das Programm selbst für Experimente isolieren.

## Aufbau

```
src/procurator/
  model.py  scanner.py     Datei-Objekte, Ordner einlesen
  engine.py                Plan berechnen (Konflikte) und ausführen
  fsops.py  journal.py     sicheres Verschieben, Verlauf und Rückgängig (SQLite)
  ops/                     Operationen, Register mit Formular-Beschreibung
  meta.py                  Datum aus EXIF und Dateistempeln
  index.py                 Datei-Index und Dubletten
  config.py  privacy.py    Konfiguration, sensible Dateien
  ai/                      Anbieter (Ollama, Claude), Vorschläge, Prüfung, Lernen
  about.py                 Version, Autor, Lizenzen der Bausteine
  server/                  FastAPI-Server (nur lokal)
  cli.py                   Kommandozeile `pc`
web/src/                   React-Oberfläche (Vite, TypeScript)
tests/
```

## Die Kernidee: Plan vor Aktion

Jede Operation berechnet zuerst einen **Plan** und verändert dabei nichts. Erst `apply_plan` schreibt auf die
Platte, atomar und mit Eintrag im Journal. Vorschau, Konflikterkennung und Rückgängig funktionieren deshalb
für jede Operation gleich.

```
Operation.transform / destination   rein, schnell, ohne Seiteneffekte
        │
make_plan(op, items)                prüft Konflikte, Rechte, ungültige Namen → Plan(changes)
        │
apply_plan(plan, journal)           führt aus, schreibt das Journal
        │
journal.undo(batch_id)              nimmt den Lauf zurück
```

- `PlannedChange(src, dst, status, reason, enabled, sensitive, editable)` beschreibt eine Zeile.
  `will_run` ist wahr, wenn sie angehakt, `ok` und mit Ziel versehen ist.
- Der Browser schickt nie fertige Zielnamen, nur Parameter und die abgewählten Quellpfade. Der Server
  berechnet den Plan beim Ausführen **neu** (`/api/apply`).
- Zwei Arten (`Plan.kind`): `move` benennt oder verschiebt, `convert` erzeugt neue Dateien (Ziel erst als
  `.part`, dann `os.replace`). Undo löscht bei `convert` nur die erzeugten Dateien, nie Quellen.
- `fsops.execute_moves` benennt in zwei Phasen über temporäre Namen um (so gehen Vertauschungen und Ketten) und
  legt fehlende Zielordner an. Auf einem anderen Laufwerk wird kopiert, mit `filecmp` Byte für Byte geprüft und
  erst dann das Original gelöscht. Angelegte Ordner stehen im Journal und werden beim Rückgängig entfernt,
  wenn sie leer sind.

## Analysieren und Planen trennen

Die Vorschau rechnet bei jeder Eingabe neu und muss schnell bleiben. Langsame Arbeit (Hashes für Dubletten,
Aufrufe eines Sprachmodells) ist deshalb ein eigener Schritt:

- `Operation.needs_analysis = True` und `analyze(items, on_progress, cancel, confirmed)` laufen als
  Hintergrund-Job (`POST /api/analyze`, Fortschritt über `GET /api/jobs/{id}`, Abbrechen über `/cancel`).
- Die Ergebnisse stehen in SQLite (Index bzw. Vorschläge). `prepare` und `transform` lesen **nur** von dort,
  sie rufen weder die Platte in grossem Stil noch ein Modell auf.
- `info()` meldet der Oberfläche, wie viel noch zu analysieren ist.

## Hooks einer Operation (`ops/base.py`)

| Hook | Zweck |
|---|---|
| `transform(item, index)` | Neuer Name oder `None` (übersprungen). **Pflicht** |
| `destination(item, new_name)` | Zielpfad, Standard: gleicher Ordner |
| `order(items)` | Reihenfolge der Verarbeitung (Laufnummern) |
| `check(item)` | Fehlermeldung, wenn nicht verarbeitbar (zum Beispiel fehlendes Programm) |
| `convert(src, dst)` | Nur für `kind = "convert"`: erzeugt die Datei |
| `prepare(items)` | Einmal vor der Vorschau mit allen Dateien, nur lesen |
| `skip_reason(item)` | Grund, wenn `transform` `None` liefert |
| `note(item)` | Kurze Begründung für eine Zeile, die ausgeführt wird |
| `info()` | Zusatzangaben zur ganzen Vorschau |
| `analyze(...)` | Langsamer Vorbereitungsschritt, siehe oben |
| `send_preview(items)` | Was würde ein Modell erhalten (nur mit `sends_data`) |
| `editable_target` / `edit_target` | Ziel in der Vorschau von Hand ändern |
| `record_decisions(accepted, rejected)` | Nach dem Anwenden, für das Lernen |

Ein `ValueError` aus `transform` oder `destination` wird als Fehlerzeile mit dieser Meldung gezeigt. Die
Meldung ist also für Nutzer gedacht.

## Neue Operation hinzufügen

1. Eine Klasse in `src/procurator/ops/` schreiben, die `Operation` erweitert (oder `RenameOperation`, wenn nur
   der Name bearbeitet wird). Als `@dataclass` mit `name: ClassVar[str]`. Die Felder sind die Parameter.
2. In `ops/registry.py` als `OperationSpec` mit ihren `Field`s eintragen. **Die Oberfläche baut das Formular
   daraus selbst**, es braucht keinen Frontend-Code. `build()` wandelt Typen um und meldet eine ungültige
   Eingabe als `ParamError` (HTTP 422).
3. In `ops/__init__.py` exportieren. Optional einen Befehl in `cli.py` ergänzen.
4. Tests in `tests/` schreiben: Plan, Konflikte, Ausführen, Rückgängig, ungültige Parameter.
5. Die Anleitung unter `docs/` und die Befehlsübersicht im README nachführen. Ein Test
   (`tests/test_docs.py`) schlägt an, wenn eine Aktion oder ein Befehl in `docs/` fehlt.

## Datenschutz im Code

- **Ein Tor zum Modell:** Dateien erreichen ein Modell nur über `privacy.split_for_config` bzw.
  `split_for_ai`. Sensible Dateien bleiben dabei zurück, bei Cloud immer. Was gesendet wird, bestimmt
  `ai.organizer.build_payload` nach der Datenschutzstufe.
- **Bestätigung nur bei Cloud:** `Config.requires_confirmation`. Der Server antwortet mit 409, wenn
  `confirm_cloud` fehlt.
- **Schlüssel nie in Dateien:** `config.py` speichert nur den Namen der Umgebungsvariable und lehnt einen
  eingefügten Schlüssel ab. `api_key_present` meldet nur ja oder nein.
- **Modellantworten sind Daten:** `ai.validate` prüft jeden Vorschlag (kein `..`, kein absoluter Pfad, keine
  versteckten Ordner, Endung bleibt, Tiefe begrenzt). Dateinamen gehen als JSON in den Prompt, damit sie nicht
  als Anweisung gelesen werden.
- **Server nur lokal:** `127.0.0.1`, `TrustedHostMiddleware`, CORS nur für den Vite-Dev-Server.

## KI-Anbindung

- `ai/providers.py`: `OllamaClient` (HTTP, fällt bei HTTP 501 auf «ohne Antwortformat» zurück) und
  `ClaudeClient` (offizielles SDK, `output_config` mit JSON-Schema). `make_client(cfg)` wählt nach Anbieter.
- `ai/organizer.py`: Pakete zu 20 Dateien bilden, Prompt nach Stufe bauen, Antwort tolerant lesen, prüfen.
- `ai/proposals.py`: Vorschläge pro (Pfad, Lauf-Schlüssel), gültig solange Grösse und Änderungszeit gleich sind.
- `ai/learning.py`: Entscheidungen merken und als Gewohnheiten und Beispiele in den Prompt geben.
- Die Tests ersetzen das Modell durch einen Fake (`FakeClient` in `tests/test_ai.py`). Es gibt keinen
  automatischen Test gegen eine echte API.

## Oberfläche

- `web/src/App.tsx`: Zustand, Jobs mit Polling, Vorschau-Tabelle.
- `web/src/api.ts` und `types.ts`: Aufrufe an `/api` und ihre Typen.
- `web/src/components/`: `OperationForm` (aus der Beschreibung der Registry), `PreviewTable`,
  `FolderPicker`, `HistoryPanel`, `SettingsDialog`, `SendDialog`, `AboutDialog`.
- Ein neues Formularfeld braucht nur einen Eintrag in `registry.py`. Eigene Bedienelemente nur, wenn ein Feld
  nicht genügt.

## Was nicht ins Repository gehört

Das Repository ist öffentlich gedacht. Deshalb nie committen: Zugangsdaten und Schlüssel, persönliche Daten
und Pfade, Angaben zu eigenen Servern, einmalige Skripte oder Testdaten aus dem eigenen Bestand. Beispiele in
Tests und Doku nutzen erfundene Namen. Lokale Planungsnotizen gehören in eine ignorierte Datei.
