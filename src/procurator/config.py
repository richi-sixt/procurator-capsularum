"""Konfigurationsdatei (config.toml): KI-Anbieter, Datenschutzstufe, sensible Dateien.

Geheimnisse stehen nie in der Datei. Für Claude wird nur der **Name** der Umgebungsvariable
gespeichert, in der der Schlüssel liegt.
"""

from __future__ import annotations

import os
import re
import tempfile
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import tomli_w
from platformdirs import user_config_path

from .i18n import tr

UI_LANGUAGES = ("auto", "de", "en")
UI_THEMES = ("auto", "light", "dark")
PROVIDERS = ("ollama", "claude")
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

PRIVACY_LEVELS = {
    0: "Nur Dateiname, Endung, Grösse und Datum",
    1: "Zusätzlich der Ordnerkontext (Namen der übergeordneten Ordner)",
    2: "Zusätzlich ein Text-Auszug aus dem Inhalt (bei Cloud jedes Mal freizugeben)",
}

DEFAULT_KEYWORDS = [
    "pass", "passport", "reisepass", "ausweis", "identität", "visum", "visa",
    "steuer", "tax", "bank", "konto", "iban", "kredit", "hypothek",
    "versicherung", "police", "vertrag", "lohn", "gehalt", "salary", "payslip",
    "arzt", "medizin", "diagnose", "rezept", "krankenkasse", "befund",
    "testament", "scheidung", "betreibung", "ahv", "pensionskasse",
    "kennwort", "geheim", "secret", "vertraulich", "confidential", "privat",
]
DEFAULT_EXTENSIONS = [".pem", ".key", ".p12", ".pfx", ".kdbx", ".gpg"]

ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


class ConfigError(ValueError):
    pass


@dataclass
class AiConfig:
    provider: str = "ollama"
    ollama_model: str = "gemma4:e2b"
    ollama_host: str = "http://localhost:11434"
    claude_model: str = "claude-sonnet-5-5"
    api_key_env: str = "ANTHROPIC_API_KEY"  # Name der Variable, nie der Schlüssel selbst
    privacy_level: int = 0
    # Aus angenommenen, abgelehnten und korrigierten Vorschlägen lernen (nur lokal gespeichert)
    learn: bool = True


@dataclass
class PrivacyConfig:
    sensitive_keywords: list[str] = field(default_factory=lambda: list(DEFAULT_KEYWORDS))
    sensitive_extensions: list[str] = field(default_factory=lambda: list(DEFAULT_EXTENSIONS))
    # Nur für ein lokales Modell: sensible Dateien dürfen dorthin. Bei Cloud ohne Wirkung.
    allow_sensitive_local: bool = False


@dataclass
class UiConfig:
    """Darstellung. Liegt hier und nicht im Browser, weil die Desktop-App bei jedem Start einen anderen
    Port (und damit einen anderen Browserspeicher) hat."""

    language: str = "auto"  # auto = Sprache des Browsers
    theme: str = "auto"  # auto = Einstellung des Systems
    thumbs: bool = True  # Vorschaubilder bei Bildern


@dataclass
class Config:
    ai: AiConfig = field(default_factory=AiConfig)
    privacy: PrivacyConfig = field(default_factory=PrivacyConfig)
    ui: UiConfig = field(default_factory=UiConfig)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def is_cloud(self) -> bool:
        return self.ai.provider == "claude"

    @property
    def requires_confirmation(self) -> bool:
        """Freigabe vor jedem Lauf: nur wenn Daten den Rechner verlassen würden."""
        return self.is_cloud


def config_path() -> Path:
    env = os.environ.get("PC_CONFIG")
    if env:
        return Path(env)
    return user_config_path("procurator-capsularum", ensure_exists=True) / "config.toml"


def _clean_list(values: Any, label: str, *, ext: bool = False) -> list[str]:
    if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
        raise ConfigError(tr("{label}: Liste von Texten erwartet", label=tr(label)))
    out: list[str] = []
    for v in values:
        v = v.strip().casefold()
        if ext and v and not v.startswith("."):
            v = "." + v
        if not v or v in out:
            continue
        if len(v) > 50:
            raise ConfigError(tr("{label}: Eintrag zu lang: {value}…", label=tr(label), value=v[:20]))
        out.append(v)
    if len(out) > 200:
        raise ConfigError(tr("{label}: höchstens 200 Einträge", label=tr(label)))
    return out


def parse(data: dict[str, Any]) -> Config:
    """Prüft und normalisiert Eingaben (aus der Datei oder der Oberfläche)."""
    base = Config()
    ai_in = data.get("ai", {}) or {}
    pr_in = data.get("privacy", {}) or {}
    ai = AiConfig(**{**asdict(base.ai), **{k: v for k, v in ai_in.items() if k in asdict(base.ai)}})

    if ai.provider not in PROVIDERS:
        raise ConfigError(tr("Anbieter muss ollama oder claude sein"))
    for label, value in (("Ollama-Modell", ai.ollama_model), ("Claude-Modell", ai.claude_model)):
        if not isinstance(value, str) or not value.strip() or len(value) > 100:
            raise ConfigError(tr("{label} fehlt oder ist zu lang", label=label))
    ai.ollama_model, ai.claude_model = ai.ollama_model.strip(), ai.claude_model.strip()
    if not isinstance(ai.privacy_level, int) or isinstance(ai.privacy_level, bool) \
            or ai.privacy_level not in PRIVACY_LEVELS:
        raise ConfigError(tr("Datenschutzstufe muss 0, 1 oder 2 sein"))
    if not isinstance(ai.learn, bool):
        raise ConfigError(tr("«Aus Entscheidungen lernen»: ja oder nein erwartet"))
    if not isinstance(ai.api_key_env, str) or not ENV_NAME.match(ai.api_key_env.strip()):
        raise ConfigError(tr(
            "Hier steht der Name der Umgebungsvariable (zum Beispiel ANTHROPIC_API_KEY), "
            "nicht der Schlüssel selbst"))
    ai.api_key_env = ai.api_key_env.strip()
    parsed = urlparse(str(ai.ollama_host).strip())
    if parsed.scheme not in ("http", "https") or parsed.hostname not in LOCAL_HOSTS:
        raise ConfigError(tr("Ollama darf nur über localhost oder 127.0.0.1 angesprochen werden"))
    ai.ollama_host = str(ai.ollama_host).strip().rstrip("/")

    allow_local = pr_in.get("allow_sensitive_local", base.privacy.allow_sensitive_local)
    if not isinstance(allow_local, bool):
        raise ConfigError(tr("«Sensible Dateien an lokales Modell»: ja oder nein erwartet"))

    privacy = PrivacyConfig(
        allow_sensitive_local=allow_local,
        sensitive_keywords=_clean_list(
            pr_in.get("sensitive_keywords", base.privacy.sensitive_keywords), "Schlüsselwörter"),
        sensitive_extensions=_clean_list(
            pr_in.get("sensitive_extensions", base.privacy.sensitive_extensions),
            "Endungen", ext=True),
    )
    return Config(ai, privacy, parse_ui(data.get("ui", {}) or {}))


def parse_ui(data: dict[str, Any]) -> UiConfig:
    base = UiConfig()
    ui = UiConfig(**{**asdict(base), **{k: v for k, v in data.items() if k in asdict(base)}})
    if ui.language not in UI_LANGUAGES:
        raise ConfigError(tr("Sprache muss auto, de oder en sein"))
    if ui.theme not in UI_THEMES:
        raise ConfigError(tr("Darstellung muss auto, light oder dark sein"))
    if not isinstance(ui.thumbs, bool):
        raise ConfigError(tr("«Vorschaubilder»: ja oder nein erwartet"))
    return ui


def load(path: Path | None = None) -> tuple[Config, str | None]:
    """Config laden. Fehlt die Datei oder ist sie kaputt, gelten die Standardwerte.

    Gibt (Config, Warnung) zurück; die Warnung nennt den Grund bei einer kaputten Datei.
    """
    p = path or config_path()
    if not p.exists():
        return Config(), None
    try:
        return parse(tomllib.loads(p.read_text(encoding="utf-8"))), None
    except (tomllib.TOMLDecodeError, ConfigError, OSError, TypeError) as exc:
        return Config(), tr("Konfigurationsdatei nicht lesbar, Standardwerte gelten: {error}", error=exc)


def save(cfg: Config, path: Path | None = None) -> Path:
    """Atomar schreiben (temporäre Datei, dann ersetzen)."""
    p = path or config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".config-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            tomli_w.dump(cfg.to_dict(), fh)
        os.replace(tmp, p)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return p


def api_key_present(cfg: Config) -> bool:
    """Nur ob die Variable gesetzt ist. Der Wert wird nie gelesen oder weitergegeben."""
    return bool(os.environ.get(cfg.ai.api_key_env))
