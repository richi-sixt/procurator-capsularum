"""Register aller Operationen mit Formular-Beschreibung (für UI und API)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from ..i18n import tr
from .base import Operation
from .convert import CbrToCbz, ConvertImages
from .dedupe import MoveDuplicates
from .move import MoveToFolder, SortByTemplate
from .organize import AiOrganize
from .rename import (
    Append,
    ChangeCase,
    DateStamp,
    InsertChars,
    NameTemplate,
    Prepend,
    RegexReplace,
    RemoveChars,
    ReplaceText,
    Sequence,
    Wildcard,
)
from .trash import TrashDuplicates


@dataclass
class Field:
    key: str
    label: str
    type: str  # text | number | select | bool | date
    default: Any = None
    options: list[tuple[str, str]] = field(default_factory=list)  # (Wert, Anzeige)
    help: str = ""
    required: bool = False
    show_if: dict[str, Any] | None = None  # nur anzeigen, wenn param == wert


@dataclass
class OperationSpec:
    name: str
    label: str
    group: str
    cls: type[Operation]
    fields: list[Field]
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": tr(self.label),
            "group": tr(self.group),
            "description": tr(self.description) if self.description else "",
            "kind": self.cls.kind,
            "needsAnalysis": self.cls.needs_analysis,
            "sendsData": self.cls.sends_data,
            "destructive": self.cls.destructive,
            "fields": [
                {
                    "key": f.key, "label": tr(f.label), "type": f.type, "default": f.default,
                    "options": [{"value": v, "label": tr(lbl)} for v, lbl in f.options],
                    "help": tr(f.help) if f.help else "", "required": f.required, "showIf": f.show_if,
                }
                for f in self.fields
            ],
        }


_EXT = Field("keep_extension", "Endung unverändert lassen", "bool", True)
_IC = Field("ignore_case", "Gross-/Kleinschreibung ignorieren", "bool", False)
_POS = [("append", "Anhängen"), ("prepend", "Voranstellen"), ("replace", "Ganzen Namen ersetzen")]

SPECS: list[OperationSpec] = [
    OperationSpec("replace", "Text ersetzen", "Text", ReplaceText, [
        Field("find", "Suchen", "text", "", required=True),
        Field("replace", "Ersetzen durch", "text", ""),
        Field("mode", "Treffer", "select", "all",
              [("first", "Erster"), ("last", "Letzter"), ("all", "Alle")]),
        _IC, _EXT,
    ], "Ersetzt Text im Dateinamen."),
    OperationSpec("wildcard", "Wildcard", "Text", Wildcard, [
        Field("pattern", "Muster", "text", "", help="* = beliebig viele, ? = ein Zeichen",
              required=True),
        Field("replace", "Ersetzen durch", "text", ""),
        _IC, _EXT,
    ], "Ersetzt den ersten Treffer eines Wildcard-Musters."),
    OperationSpec("regex", "Regulärer Ausdruck", "Text", RegexReplace, [
        Field("pattern", "Muster", "text", "", required=True),
        Field("replace", "Ersetzen durch", "text", "", help="$1, $2 ... als Rückverweise"),
        _IC, _EXT,
    ], "Ersetzt den ersten Treffer eines regulären Ausdrucks."),
    OperationSpec("append", "Anhängen", "Text", Append, [
        Field("text", "Text", "text", "", required=True), _EXT,
    ]),
    OperationSpec("prepend", "Voranstellen", "Text", Prepend, [
        Field("text", "Text", "text", "", required=True), _EXT,
    ]),
    OperationSpec("remove", "Zeichen entfernen", "Struktur", RemoveChars, [
        Field("mode", "Modus", "select", "range", [("range", "Ab Position"), ("from_end", "Am Ende")]),
        Field("start", "Startposition (1 = erstes)", "number", 1, show_if={"mode": "range"}),
        Field("count", "Anzahl Zeichen", "number", 1, required=True),
        _EXT,
    ]),
    OperationSpec("insert", "Zeichen einfügen", "Struktur", InsertChars, [
        Field("text", "Text", "text", "", required=True),
        Field("index", "Position (0 = ganz vorn)", "number", 0),
        Field("from_end", "Position vom Ende zählen", "bool", False),
        Field("pad_to_length", "Auf Länge auffüllen (0 = aus)", "number", 0),
        _EXT,
    ]),
    OperationSpec("case", "Gross-/Kleinschreibung", "Struktur", ChangeCase, [
        Field("mode", "Schreibweise", "select", "title",
              [("title", "Titel"), ("lower", "klein"), ("upper", "GROSS")]),
        _EXT,
    ]),
    OperationSpec("sequence", "Laufnummer", "Nummer & Datum", Sequence, [
        Field("label", "Name (optional)", "text", ""),
        Field("digits", "Stellen", "number", 3),
        Field("start", "Startnummer", "number", 1),
        Field("position", "Position", "select", "append", _POS),
        Field("label_first", "Name vor der Nummer", "bool", True),
        Field("sep", "Trennzeichen", "text", "-"),
        Field("sort", "Reihenfolge", "select", "name",
              [("custom", "Eigene (Ziehen)"), ("name", "Name"),
               ("auto", "Datum (Aufnahmedatum, sonst ältestes Dateidatum)"),
               ("created", "Erstellt"), ("modified", "Geändert")]),
        Field("descending", "Absteigend", "bool", False),
        _EXT,
    ]),
    OperationSpec("template", "Name aus Vorlage", "Nummer & Datum", NameTemplate, [
        Field("template", "Vorlage", "text", "{date:%Y%m%d_%H-%M-%S}_{size}", required=True,
              help="Platzhalter: {date} oder {date:%Y%m%d_%H-%M-%S}, {size} (Byte), {name} (alter "
                   "Name), {ext}, {n} oder {n:3} (Laufnummer), {folder}. Die Vorlage ersetzt den "
                   "ganzen Namen."),
        Field("source", "Quelle des Datums", "select", "auto",
              [("auto", "Automatisch (Aufnahmedatum, sonst ältestes Dateidatum)"),
               ("created", "Erstellt"), ("modified", "Geändert")]),
        Field("start", "Startnummer für {n}", "number", 1),
        _EXT,
    ], "Baut den Namen aus Platzhaltern, zum Beispiel Zeitpunkt und Dateigrösse. Gut, wenn Bilder von "
       "mehreren Geräten im selben Ordner landen."),
    OperationSpec("date", "Datum", "Nummer & Datum", DateStamp, [
        Field("source", "Quelle", "select", "auto",
              [("auto", "Automatisch (Aufnahmedatum, sonst ältestes Dateidatum)"),
               ("created", "Erstellt"), ("modified", "Geändert"), ("custom", "Eigenes Datum")]),
        Field("custom_date", "Datum", "date", None, show_if={"source": "custom"}),
        Field("fmt", "Format (strftime)", "text", "%Y-%m-%d"),
        Field("position", "Position", "select", "prepend", _POS),
        Field("sep", "Trennzeichen", "text", "_"),
        _EXT,
    ]),
]

_OUT = Field("output_dir", "Zielordner (leer = neben der Quelle)", "folder", "",
             help="Mit Zielordner wird die Ordnerstruktur dort nachgebaut. Vorhandene Dateien werden übersprungen.")

SPECS += [
    OperationSpec("move", "In Ordner verschieben", "Organisieren", MoveToFolder, [
        Field("target_dir", "Zielordner", "folder", "", required=True,
              help="Wird angelegt, falls er fehlt. Funktioniert auch auf ein anderes Laufwerk."),
        Field("keep_structure", "Ordnerstruktur beibehalten", "bool", False,
              help="Aus: alle Dateien direkt in den Zielordner. Ein: Unterordner werden nachgebaut."),
    ], "Verschiebt Dateien, der Name bleibt gleich. Rückgängig macht den Lauf zurück."),
    OperationSpec("sort_template", "In Ordner nach Vorlage sortieren", "Organisieren", SortByTemplate, [
        Field("template", "Ordner-Vorlage", "text", "{type}/{date:%Y}", required=True,
              help="Platzhalter: {date:%Y} (Jahr), {date:%Y-%m} , {type} (Bilder, Dokumente, …), "
                   "{ext}, {initial}, {folder}. Ein / ergibt Unterordner. Der Dateiname bleibt."),
        Field("base_dir", "Zielordner (leer = im gewählten Ordner)", "folder", "",
              help="Wird angelegt, falls er fehlt."),
        Field("source", "Quelle des Datums", "select", "auto",
              [("auto", "Automatisch (Aufnahmedatum, sonst ältestes Dateidatum)"),
               ("created", "Erstellt"), ("modified", "Geändert")]),
    ], "Sortiert ohne KI nach festen Regeln, zum Beispiel Bilder/2024. Rückgängig macht den Lauf zurück."),
    OperationSpec("ai_organize", "KI-Vorschläge (ordnen und benennen)", "Organisieren", AiOrganize, [
        Field("mode", "Was soll vorgeschlagen werden?", "select", "both",
              [("both", "Ordner und Namen"), ("folders", "Nur Ordner"), ("names", "Nur Namen")]),
        Field("hint", "Eigene Anweisung (optional)", "text", "",
              help="Zum Beispiel: Dokumente nach Jahr und Art ordnen. Bis 500 Zeichen."),
        Field("max_depth", "Höchste Ordnertiefe", "number", 3),
        Field("reanalyze", "Vorhandene Vorschläge neu berechnen", "bool", False,
              help="Sonst werden schon bekannte Dateien nicht noch einmal gefragt."),
    ], "Ein Sprachmodell schlägt Ordner und Namen vor, du prüfst und korrigierst in der Vorschau."),
    OperationSpec("duplicates", "Dubletten verschieben", "Organisieren", MoveDuplicates, [
        Field("keep", "Welche Datei bleibt?", "select", "oldest",
              [("oldest", "Die älteste"), ("newest", "Die neueste"),
               ("shortest", "Die mit dem kürzesten Pfad"), ("first", "Die erste (alphabetisch)")],
              help="Pro Gruppe gleicher Dateien bleibt genau eine liegen."),
        Field("target_dir", "Zielordner (leer = _Dubletten im gewählten Ordner)", "folder", "",
              help="Die Kopien werden verschoben, nicht gelöscht. Rückgängig holt sie zurück."),
        Field("keep_structure", "Ordnerstruktur im Zielordner beibehalten", "bool", True),
        Field("min_size_kb", "Mindestgrösse in KB (0 = alle)", "number", 0),
    ], "Findet gleiche Dateien über ihren Inhalt und verschiebt alle bis auf eine. Zuerst «Analysieren»."),
    OperationSpec("trash_duplicates", "Dubletten-Ordner in den Papierkorb legen", "Organisieren", TrashDuplicates, [],
                  "Legt alle Dateien in «_Dubletten»-Ordnern des gewählten Ordners in den Papierkorb (Unterordner "
                  "einbeziehen). Das Programm kann das nicht rückgängig machen, im Papierkorb geht «Zurücklegen»."),
    OperationSpec("cbr2cbz", "CBR → CBZ", "Konvertieren", CbrToCbz, [
        _OUT,
        Field("copy_cbz", "Vorhandene CBZ mitkopieren (nur mit Zielordner)", "bool", False),
        Field("copy_pdf", "PDF mitkopieren (nur mit Zielordner)", "bool", False),
    ], "Comic-Archive von RAR zu ZIP, Seiten bleiben bitidentisch. Braucht unar."),
    OperationSpec("images", "Bilder konvertieren", "Konvertieren", ConvertImages, [
        _OUT,
        Field("format", "Format", "select", "jpg", [("jpg", "JPG"), ("png", "PNG"), ("webp", "WebP")]),
        Field("quality", "Qualität (JPG/WebP, 1 bis 100)", "number", 85),
        Field("max_edge", "Längste Seite in Pixeln (0 = Originalgrösse)", "number", 0),
    ], "JPG, PNG, WebP, HEIC, TIFF und BMP umwandeln und optional verkleinern."),
]

BY_NAME = {s.name: s for s in SPECS}


class ParamError(ValueError):
    pass


def build(name: str, params: dict[str, Any]) -> Operation:
    """Operation aus API-Parametern bauen (mit Typumwandlung und Prüfung)."""
    spec = BY_NAME.get(name)
    if spec is None:
        raise ParamError(tr("Unbekannte Operation: {name}", name=name))
    kwargs: dict[str, Any] = {}
    for f in spec.fields:
        value = params.get(f.key, f.default)
        if f.type == "number":
            try:
                value = int(value if value not in (None, "") else (f.default or 0))
            except (TypeError, ValueError) as exc:
                raise ParamError(tr("{label}: Zahl erwartet", label=tr(f.label))) from exc
        elif f.type == "bool":
            value = bool(value)
        elif f.type == "date":
            if value in (None, ""):
                value = None
            else:
                try:
                    value = date.fromisoformat(str(value))
                except ValueError as exc:
                    raise ParamError(tr("{label}: Datum als JJJJ-MM-TT erwartet", label=tr(f.label))) from exc
        elif f.type == "select":
            if value not in {v for v, _ in f.options}:
                raise ParamError(tr("{label}: ungültiger Wert", label=tr(f.label)))
        else:  # text, folder
            value = "" if value is None else str(value)
        kwargs[f.key] = value
    for f in spec.fields:
        if f.required and kwargs[f.key] in ("", None):
            raise ParamError(tr("{label} fehlt", label=tr(f.label)))
    try:
        return spec.cls(**kwargs)
    except ValueError as exc:  # zum Beispiel eine ungültige Vorlage
        raise ParamError(str(exc)) from exc
