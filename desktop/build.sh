#!/usr/bin/env bash
# Baut die Desktop-App (macOS): Oberfläche, gebündelter Server, Tauri-Hülle.
# Voraussetzungen: uv, Node.js, Rust (rustup) und die Xcode-Kommandozeilenwerkzeuge.
# Ergebnis: desktop/src-tauri/target/release/bundle/macos/Procurator Capsularum.app
set -euo pipefail
cd "$(dirname "$0")/.."

# Rustup aus Homebrew liegt nicht im PATH (keg-only), ein rustup.rs-Install unter ~/.cargo/bin schon.
for dir in /opt/homebrew/opt/rustup/bin /usr/local/opt/rustup/bin "$HOME/.cargo/bin"; do
  [ -d "$dir" ] && PATH="$dir:$PATH"
done
command -v cargo >/dev/null || { echo "Rust fehlt (https://rustup.rs oder: brew install rustup && rustup default stable)." >&2; exit 1; }

echo "1/3 Oberfläche bauen"
(cd web && npm ci && npm run build)

echo "2/3 Server bündeln (PyInstaller)"
uv run --no-dev --group desktop --extra claude pyinstaller desktop/pc-server.spec --noconfirm \
  --distpath desktop/build/dist --workpath desktop/build/work

echo "3/3 App bauen (Tauri)"
(cd desktop && npm ci && npx tauri build --bundles "${BUNDLES:-app}")

echo "Fertig: ${CARGO_TARGET_DIR:-desktop/src-tauri/target}/release/bundle/"
