"""Zweisprachige Meldungen des Servers (Deutsch ist die Quellsprache, Englisch die Übersetzung).

`tr("Dublette von {name}", name=x)`: der deutsche Text ist zugleich der Schlüssel. Fehlt eine englische
Übersetzung, erscheint der deutsche Text (nie ein Fehler). Die Sprache gilt pro Anfrage (`X-Lang`-Kopf
oder `Accept-Language`) und wird in einer Kontextvariablen geführt. Hintergrundaufträge übernehmen sie
mit `bind()`. Die Kommandozeile bleibt Deutsch, ausser `PC_LANG=en` ist gesetzt.
"""

from __future__ import annotations

import contextvars
import os
from collections.abc import Callable
from typing import Any

from .locale_en import EN

LANGUAGES = ("de", "en")
_lang: contextvars.ContextVar[str] = contextvars.ContextVar("pc_lang", default="")


def normalize(value: str | None) -> str:
    """«en-US,en;q=0.9» → «en». Unbekanntes ergibt Deutsch."""
    first = (value or "").split(",")[0].split(";")[0].strip().lower()
    code = first.split("-")[0]
    return code if code in LANGUAGES else "de"


def set_language(value: str | None) -> contextvars.Token[str]:
    return _lang.set(normalize(value))


def language() -> str:
    return _lang.get() or normalize(os.environ.get("PC_LANG"))


def tr(text: str, /, **params: Any) -> str:
    """Der Text in der Sprache der Anfrage, mit eingesetzten Werten."""
    out = EN.get(text, text) if language() == "en" else text
    return out.format(**params) if params else out


def bind(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Für Threads: führt `fn` mit der Sprache der aktuellen Anfrage aus."""
    ctx = contextvars.copy_context()

    def run(*args: Any, **kwargs: Any) -> Any:
        return ctx.run(fn, *args, **kwargs)

    return run
