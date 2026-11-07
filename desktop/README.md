# Desktop-App (macOS)

Procurator Capsularum als App mit eigenem Fenster, ohne Terminal und ohne Browser. Die Hülle ist
[Tauri](https://tauri.app/) (Rust, `src-tauri/`). Sie startet den Server als mitgeliefertes Programm
(PyInstaller, `pc-server.spec`) und zeigt die Oberfläche in einem Fenster. Alles läuft wie sonst auf dem
eigenen Rechner, der Server hört nur auf `127.0.0.1`.

## Bauen

Voraussetzungen: `uv`, Node.js, [Rust](https://rustup.rs) und die Xcode-Kommandozeilenwerkzeuge.

```bash
desktop/build.sh
```

Das Skript baut die Oberfläche, bündelt den Server und baut die App. Ergebnis:
`desktop/src-tauri/target/release/bundle/macos/Procurator Capsularum.app`. Mit `BUNDLES=app,dmg` entsteht
zusätzlich ein Installationsabbild (ungetestet). Die App ist **nicht signiert und nicht beglaubigt**. Eine selbst
gebaute App öffnet sich normal. Eine heruntergeladene blockiert macOS zuerst (Rechtsklick, «Öffnen»).

**Virenscanner:** Manche Echtzeitschutz-Programme blockieren die frisch übersetzten Build-Skripte von Cargo. Typisch
ist `Failed to clean up … Operation not permitted (os error 1)` bei `proc-macro2`. Hilft eine Ausnahme nicht, baut
man mit einem Zielordner ausserhalb des Home-Ordners, zum Beispiel
`CARGO_TARGET_DIR=/private/tmp/pc-target desktop/build.sh`. Die App liegt dann unter diesem Ordner.
Ein Programm mit Verhaltensüberwachung fragt womöglich auch beim Start der App nach: Der gebündelte Server
(`pc-server`) legt Einstellungen, Verlauf und Index im Ordner der App-Daten ab. Die Freigabe gilt oft nur für genau
diese Programmdatei, nach einem neuen Bau fragt der Schutz erneut.

## Wie es zusammenhängt

1. Die Hülle startet `pc-server` und liest die erste Zeile seiner Ausgabe: `PROCURATOR_READY http://127.0.0.1:PORT`.
2. Das Fenster zeigt zuerst `splash/index.html` und wechselt dann auf diese Adresse. Scheitert der Start, steht der
   Grund im Fenster.
3. Der Server hört an einem freien Port. Schliesst die Hülle (oder stürzt sie ab), endet der Standardeingang des
   Servers, und er beendet sich selbst.

Den Server allein ohne Hülle starten: `uv run python -m procurator.desktop`. Zum Fehlersuchen zeigt
`PROCURATOR_LOG=info` jede Anfrage. Mit `PROCURATOR_SERVER=/Pfad/zum/pc-server` nimmt die Hülle einen anderen
Server (zum Beispiel bei `npx tauri dev`).

## Lizenzen

Die App steht unter der AGPL-3.0-or-later wie das ganze Programm. Mitgeliefert werden Tauri (MIT oder
Apache-2.0) und PyInstaller (GPL-2.0 mit Ausnahme für gebündelte Programme) sowie die Bausteine des Programms.
Der Dialog «Über das Programm» führt sie auf. `unar` und Ollama werden **nicht** mitgeliefert und bleiben separat
zu installieren.
