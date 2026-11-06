"""Verbindung zum konfigurierten Modell prüfen, ohne Dateien oder Schlüssel zu senden."""

from __future__ import annotations

from typing import Any

import httpx

from ..config import Config, api_key_present


def probe(cfg: Config) -> dict[str, Any]:
    """Ollama: fragt die lokale Modellliste ab. Claude: prüft nur, ob die Variable gesetzt ist.

    Für Claude gibt es absichtlich keinen Netzwerkaufruf (kostet Geld und sendet den Schlüssel).
    """
    if cfg.ai.provider == "claude":
        ok = api_key_present(cfg)
        return {
            "ok": ok, "provider": "claude", "models": [],
            "message": (f"Umgebungsvariable {cfg.ai.api_key_env} ist gesetzt. Es wurde keine "
                        "Anfrage an die Cloud gesendet." if ok
                        else f"Umgebungsvariable {cfg.ai.api_key_env} ist nicht gesetzt."),
        }
    try:
        r = httpx.get(f"{cfg.ai.ollama_host}/api/tags", timeout=3.0)
        r.raise_for_status()
        models = sorted(m.get("name", "") for m in r.json().get("models", []))
    except httpx.HTTPError as exc:
        return {"ok": False, "provider": "ollama", "models": [],
                "message": f"Ollama antwortet nicht unter {cfg.ai.ollama_host} "
                           f"({type(exc).__name__}). Läuft der Dienst? (ollama serve)"}
    except ValueError:
        return {"ok": False, "provider": "ollama", "models": [],
                "message": "Unerwartete Antwort, ist das wirklich Ollama?"}
    present = cfg.ai.ollama_model in models
    return {
        "ok": present, "provider": "ollama", "models": models,
        "message": (f"Ollama läuft, Modell {cfg.ai.ollama_model} ist geladen." if present else
                    f"Ollama läuft, aber das Modell {cfg.ai.ollama_model} fehlt. "
                    f"Laden mit: ollama pull {cfg.ai.ollama_model}"),
    }
