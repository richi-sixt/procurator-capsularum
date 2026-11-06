"""Sensible Dateien erkennen. Solche Dateien werden nie an ein Modell gesendet."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .config import Config
from .model import FileItem


def _norm(text: str) -> str:
    """Gross-/Kleinschreibung und Akzente ignorieren (Steuererklärung = steuererklarung)."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


@dataclass(frozen=True)
class SensitiveRules:
    """Ein Schlüsselwort trifft, wenn es am Anfang eines Wortes im Namen steht.

    «pass» trifft «Passwort» und «Pass_2024.pdf», aber nicht «Compass» oder «bypass».
    Geprüft werden Dateiname, alle Ordnernamen unterhalb des gewählten Ordners und dieser
    Ordner selbst. Ordner darüber zählen nicht.
    """

    keywords: tuple[str, ...] = ()
    extensions: tuple[str, ...] = ()
    _pattern: re.Pattern[str] | None = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        words = sorted({_norm(k) for k in self.keywords if k.strip()}, key=len, reverse=True)
        pattern = (
            re.compile(r"(?<![^\W\d_])(?:" + "|".join(re.escape(w) for w in words) + ")")
            if words else None
        )
        object.__setattr__(self, "_pattern", pattern)

    def match(self, item: FileItem) -> str:
        """Gibt den Treffer (Schlüsselwort oder Endung) zurück, sonst einen leeren Text."""
        if item.suffix.lower() in {e.lower() for e in self.extensions}:
            return item.suffix.lower()
        if self._pattern is None:
            return ""
        parts = [item.path.name]
        if item.root is not None:
            try:
                parts = [item.root.name, *item.path.relative_to(item.root).parts]
            except ValueError:
                pass
        for part in parts:
            m = self._pattern.search(_norm(part))
            if m:
                return m.group(0)
        return ""


def split_for_ai(
    items: list[FileItem],
    rules: SensitiveRules,
    *,
    cloud: bool,
    allow_sensitive_local: bool = False,
) -> tuple[list[FileItem], dict[FileItem, str]]:
    """Trennt Dateien in solche, die ein Modell sehen darf, und zurückgehaltene mit Grund.

    Das ist die einzige Stelle, durch die Dateien zu einem Modell gelangen dürfen.
    Bei einem Cloud-Anbieter werden sensible Dateien immer zurückgehalten. Bei einem lokalen
    Modell nur, solange `allow_sensitive_local` aus ist (Standard).
    """
    if not cloud and allow_sensitive_local:
        return list(items), {}
    allowed: list[FileItem] = []
    withheld: dict[FileItem, str] = {}
    for item in items:
        hit = rules.match(item)
        if hit:
            withheld[item] = hit
        else:
            allowed.append(item)
    return allowed, withheld


def split_for_config(
    items: list[FileItem], cfg: Config
) -> tuple[list[FileItem], dict[FileItem, str]]:
    """Wie `split_for_ai`, mit den Einstellungen aus der Konfiguration."""
    return split_for_ai(
        items, rules_from_config(cfg),
        cloud=cfg.is_cloud, allow_sensitive_local=cfg.privacy.allow_sensitive_local,
    )


def rules_from_config(cfg: Config) -> SensitiveRules:
    return SensitiveRules(tuple(cfg.privacy.sensitive_keywords),
                          tuple(cfg.privacy.sensitive_extensions))
