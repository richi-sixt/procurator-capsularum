"""Verbindung zum konfigurierten Modell prüfen, ohne Dateien oder Schlüssel zu senden."""

from __future__ import annotations

from typing import Any

import httpx

from ..config import Config, api_key_present
from ..i18n import tr


def probe(cfg: Config) -> dict[str, Any]:
    """Ollama: fragt die lokale Modellliste ab. Claude: prüft nur, ob die Variable gesetzt ist.

    Für Claude gibt es absichtlich keinen Netzwerkaufruf (kostet Geld und sendet den Schlüssel).
    """
    if cfg.ai.provider == "claude":
        ok = api_key_present(cfg)
        return {
            "ok": ok, "provider": "claude", "models": [],
            "message": (tr("Umgebungsvariable {name} ist gesetzt. Es wurde keine Anfrage an die Cloud gesendet.",
                           name=cfg.ai.api_key_env) if ok
                        else tr("Umgebungsvariable {name} ist nicht gesetzt.", name=cfg.ai.api_key_env)),
        }
    try:
        r = httpx.get(f"{cfg.ai.ollama_host}/api/tags", timeout=3.0)
        r.raise_for_status()
        models = sorted(m.get("name", "") for m in r.json().get("models", []))
    except httpx.HTTPError as exc:
        return {"ok": False, "provider": "ollama", "models": [],
                "message": tr("Ollama antwortet nicht unter {host} ({error}). Läuft der Dienst? (ollama serve)",
                              host=cfg.ai.ollama_host, error=type(exc).__name__)}
    except ValueError:
        return {"ok": False, "provider": "ollama", "models": [],
                "message": tr("Unerwartete Antwort, ist das wirklich Ollama?")}
    present = cfg.ai.ollama_model in models
    return {
        "ok": present, "provider": "ollama", "models": models,
        "message": (tr("Ollama läuft, Modell {model} ist geladen.", model=cfg.ai.ollama_model) if present else
                    tr("Ollama läuft, aber das Modell {model} fehlt. Laden mit: ollama pull {model}",
                       model=cfg.ai.ollama_model)),
    }
