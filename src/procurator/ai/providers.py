"""Anbieter für Sprachmodelle: Ollama (lokal) und Claude (Cloud) hinter einer Schnittstelle."""

from __future__ import annotations

import json
import os
from typing import Any, Protocol

import httpx

from ..config import Config

# Antwortformat, das beide Anbieter erzwingen: eine Liste mit einem Eintrag pro Datei.
RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "files": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "folder": {"type": "string"},
                    "name": {"type": "string"},
                    "reason": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["id", "folder", "name", "reason", "confidence"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["files"],
    "additionalProperties": False,
}


class ProviderError(RuntimeError):
    """Verständliche Fehlermeldung für die Oberfläche (nie mit Schlüsseln oder Dateiinhalten)."""


class LLMClient(Protocol):
    provider: str
    model: str

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> str:
        """Antwort des Modells als JSON-Text, passend zum Schema."""
        ...


class OllamaClient:
    """Spricht den lokalen Ollama-Dienst an. Nichts verlässt den Rechner."""

    provider = "ollama"

    def __init__(self, host: str, model: str, *, timeout: float = 600.0, num_ctx: int = 8192) -> None:
        self.host = host.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.num_ctx = num_ctx
        self._structured = True  # false, sobald Ollama für dieses Modell kein erzwungenes Format kann

    def _post(self, system: str, user: str, schema: dict[str, Any] | None) -> httpx.Response:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "stream": False,
            "options": {"temperature": 0, "num_ctx": self.num_ctx},
        }
        if schema is not None:
            payload["format"] = schema  # Ollama erzwingt das Schema bei der Erzeugung
        try:
            return httpx.post(f"{self.host}/api/chat", json=payload, timeout=self.timeout)
        except httpx.ConnectError as exc:
            raise ProviderError(
                f"Ollama antwortet nicht unter {self.host}. Läuft der Dienst? (ollama serve)"
            ) from exc
        except httpx.TimeoutException as exc:
            raise ProviderError(
                "Ollama hat nicht rechtzeitig geantwortet. Das Modell ist vielleicht zu gross "
                "für diesen Rechner oder lädt noch."
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Verbindung zu Ollama fehlgeschlagen ({type(exc).__name__})") from exc

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> str:
        r = self._post(system, user, schema) if self._structured else None
        if r is not None and r.status_code == 501 and "structured output" in r.text:
            self._structured = False  # zum Beispiel beim MLX-Runner: ohne Format weitermachen
            r = None
        if r is None:  # das Schema steht dann im Prompt, die Antwort wird tolerant gelesen
            hint = "\n\nReply with a single JSON object that follows this JSON schema:\n"
            r = self._post(system + hint + json.dumps(schema), user, None)
        if r.status_code == 404:
            raise ProviderError(f"Das Modell {self.model} fehlt. Laden mit: ollama pull {self.model}")
        if r.status_code >= 400:
            raise ProviderError(f"Ollama meldet einen Fehler ({r.status_code}): {r.text[:200]}")
        try:
            return str(r.json()["message"]["content"])
        except (ValueError, KeyError, TypeError) as exc:
            raise ProviderError("Unerwartete Antwort von Ollama") from exc


class ClaudeClient:
    """Spricht die Claude-API an. Dateinamen und Metadaten verlassen den Rechner."""

    provider = "claude"

    def __init__(self, api_key: str, model: str, *, client: Any = None) -> None:
        self.model = model
        if client is None:
            client = _sdk().Anthropic(api_key=api_key)
        self._client = client

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> str:
        sdk = _sdk()
        try:
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=16000,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
            )
        except sdk.AuthenticationError as exc:
            raise ProviderError("Der API-Schlüssel wurde abgelehnt. Prüfe die Umgebungsvariable.") from exc
        except sdk.PermissionDeniedError as exc:
            raise ProviderError("Der API-Schlüssel hat dafür keine Berechtigung.") from exc
        except sdk.NotFoundError as exc:
            raise ProviderError(f"Das Modell {self.model} wurde nicht gefunden.") from exc
        except sdk.BadRequestError as exc:
            raise ProviderError(f"Die Anfrage wurde abgelehnt: {exc.message}") from exc
        except sdk.RateLimitError as exc:
            raise ProviderError("Zu viele Anfragen. Warte kurz und versuche es erneut.") from exc
        except sdk.APIStatusError as exc:
            raise ProviderError(f"Claude meldet einen Fehler ({exc.status_code}).") from exc
        except sdk.APIConnectionError as exc:
            raise ProviderError("Keine Verbindung zu Anthropic. Netzwerk prüfen.") from exc
        if resp.stop_reason == "refusal":
            raise ProviderError("Das Modell hat diese Anfrage abgelehnt.")
        if resp.stop_reason == "max_tokens":
            raise ProviderError("Die Antwort wurde abgeschnitten. Weniger Dateien pro Lauf versuchen.")
        for block in resp.content:
            if block.type == "text":
                return str(block.text)
        raise ProviderError("Claude hat keine Textantwort geliefert.")


def _sdk() -> Any:
    try:
        import anthropic
    except ImportError as exc:
        raise ProviderError(
            "Das Paket «anthropic» fehlt. Installieren mit: uv sync --extra claude") from exc
    return anthropic


def make_client(cfg: Config) -> LLMClient:
    """Anbieter gemäss Konfiguration. Der Schlüssel wird nur aus der Umgebung gelesen."""
    if cfg.ai.provider == "claude":
        key = os.environ.get(cfg.ai.api_key_env, "")
        if not key:
            raise ProviderError(f"Die Umgebungsvariable {cfg.ai.api_key_env} ist nicht gesetzt.")
        return ClaudeClient(key, cfg.ai.claude_model)
    return OllamaClient(cfg.ai.ollama_host, cfg.ai.ollama_model)
