"""Kommandozeile `pc`. Standard ist immer die Vorschau; erst `--apply` benennt wirklich um."""

from __future__ import annotations

from datetime import date as Date
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn
from rich.table import Table

from . import config as cfgmod
from .engine import apply_plan, make_plan
from .index import FileIndex
from .journal import Journal
from .model import Status
from .ops import (
    Append,
    CbrToCbz,
    ChangeCase,
    ConvertImages,
    DateStamp,
    InsertChars,
    MoveDuplicates,
    MoveToFolder,
    Operation,
    Prepend,
    RegexReplace,
    RemoveChars,
    ReplaceText,
    Sequence,
    Wildcard,
)
from .privacy import rules_from_config
from .scanner import scan

app = typer.Typer(help="Procurator Capsularum: Dateien umbenennen und konvertieren, mit Vorschau.", no_args_is_help=True)
rename = typer.Typer(help="Dateien umbenennen. Ohne --apply wird nur eine Vorschau gezeigt.",
                     no_args_is_help=True)
app.add_typer(rename, name="rename")
convert = typer.Typer(help="Dateien konvertieren. Ohne --apply wird nur eine Vorschau gezeigt.",
                      no_args_is_help=True)
app.add_typer(convert, name="convert")
console = Console()

Paths = Annotated[list[Path], typer.Argument(exists=True, help="Ordner oder Dateien")]
Recursive = Annotated[bool, typer.Option("--recursive", "-r", help="Unterordner einbeziehen")]
Apply = Annotated[bool, typer.Option("--apply", help="Wirklich umbenennen (sonst nur Vorschau)")]
Unique = Annotated[bool, typer.Option("--force-unique", help="Bei Kollision Nummer anhängen")]
WithExt = Annotated[bool, typer.Option("--with-ext", help="Endung mitbearbeiten")]
IgnoreCase = Annotated[bool, typer.Option("--ignore-case", "-i", help="Gross/Klein ignorieren")]
ShowAll = Annotated[bool, typer.Option("--all", help="Auch übersprungene Dateien anzeigen")]

STYLE = {Status.OK: "green", Status.SKIP: "dim", Status.CONFLICT: "red", Status.ERROR: "red"}


def _run(op: Operation, paths: list[Path], recursive: bool, apply: bool,
         force_unique: bool, show_all: bool) -> None:
    items = scan(paths, recursive=recursive)
    if not items:
        console.print("[yellow]Keine Dateien gefunden.[/yellow]")
        raise typer.Exit(1)
    cfg, _warning = cfgmod.load()
    plan = make_plan(op, items, force_unique=force_unique, sensitive=rules_from_config(cfg))

    table = Table(show_lines=False)
    table.add_column("Original")
    table.add_column("Neu")
    table.add_column("Status")
    for c in plan.changes:
        if c.status == Status.SKIP and not show_all:
            continue
        new = c.dst.name if c.dst else ""
        if c.dst and c.dst.parent != c.src.parent:
            new = f"{c.dst.parent}/{c.dst.name}"
        note = c.status.value + (f": {c.reason}" if c.reason else "")
        if c.sensitive:
            note += f" · sensibel ({c.sensitive})"
        table.add_row(c.src.name, new, f"[{STYLE[c.status]}]{note}[/]")
    console.print(table)

    counts = plan.counts()
    console.print(
        f"{counts[Status.OK]} bereit, {counts[Status.SKIP]} übersprungen, "
        f"{counts[Status.CONFLICT]} Konflikte, {counts[Status.ERROR]} Fehler"
    )
    if "duplicates" in plan.info:
        i = plan.info
        n, g = i["duplicates"], i["groups"]
        console.print(f"{n} Kopie{'n' if n != 1 else ''} in {g} Gruppe{'n' if g != 1 else ''} "
                      f"belegen {_human(i['bytes'])}. Sie werden verschoben, nicht gelöscht.")
        if i.get("pendingFiles"):
            console.print(f"[yellow]Analyse unvollständig: {i['pendingFiles']} Dateien sind noch nicht "
                          "gelesen.[/yellow]")
    if not apply:
        console.print("[dim]Nur Vorschau. Mit --apply ausführen.[/dim]")
        return

    def progress(done: int, total: int, name: str) -> None:
        if name:
            console.print(f"[dim][{done + 1}/{total}] {name}[/dim]")

    verb = "konvertiert" if plan.kind == "convert" else (
        "verschoben" if plan.operation in ("move", "duplicates") else "umbenannt")
    result = apply_plan(plan, Journal(), progress)
    console.print(f"[green]{len(result.done)} {verb}[/green]"
                  + (f" (Lauf {result.batch_id}, rückgängig mit `pc undo`)" if result.batch_id else ""))
    for change, msg in result.failed:
        console.print(f"[red]{change.src.name}: {msg}[/red]")
    if result.failed:
        raise typer.Exit(1)


@rename.command()
def replace(
    paths: Paths, find: Annotated[str, typer.Option("--find", "-f")],
    to: Annotated[str, typer.Option("--to", "-t")] = "",
    mode: Annotated[str, typer.Option(help="first, last oder all")] = "all",
    ignore_case: IgnoreCase = False, with_ext: WithExt = False, recursive: Recursive = False,
    apply: Apply = False, force_unique: Unique = False, show_all: ShowAll = False,
) -> None:
    """Text ersetzen (erster, letzter oder alle Treffer)."""
    if mode not in ("first", "last", "all"):
        raise typer.BadParameter("mode muss first, last oder all sein")
    op = ReplaceText(find, to, mode, ignore_case, keep_extension=not with_ext)  # type: ignore[arg-type]
    _run(op, paths, recursive, apply, force_unique, show_all)


@rename.command()
def wildcard(
    paths: Paths, pattern: Annotated[str, typer.Option("--pattern", "-p", help="* und ?")],
    to: Annotated[str, typer.Option("--to", "-t")] = "",
    ignore_case: IgnoreCase = False, with_ext: WithExt = False, recursive: Recursive = False,
    apply: Apply = False, force_unique: Unique = False, show_all: ShowAll = False,
) -> None:
    """Ersten Treffer eines Wildcard-Musters ersetzen."""
    _run(Wildcard(pattern, to, ignore_case, not with_ext), paths, recursive, apply,
         force_unique, show_all)


@rename.command()
def regex(
    paths: Paths, pattern: Annotated[str, typer.Option("--pattern", "-p")],
    to: Annotated[str, typer.Option("--to", "-t", help="$1, $2 ... als Rückverweise")] = "",
    ignore_case: IgnoreCase = False, with_ext: WithExt = False, recursive: Recursive = False,
    apply: Apply = False, force_unique: Unique = False, show_all: ShowAll = False,
) -> None:
    """Ersten Treffer eines regulären Ausdrucks ersetzen."""
    _run(RegexReplace(pattern, to, ignore_case, not with_ext), paths, recursive, apply,
         force_unique, show_all)


@rename.command()
def append(
    paths: Paths, text: Annotated[str, typer.Option("--text", "-t")],
    with_ext: WithExt = False, recursive: Recursive = False, apply: Apply = False,
    force_unique: Unique = False, show_all: ShowAll = False,
) -> None:
    """Text ans Ende des Namens anhängen."""
    _run(Append(text, not with_ext), paths, recursive, apply, force_unique, show_all)


@rename.command()
def prepend(
    paths: Paths, text: Annotated[str, typer.Option("--text", "-t")],
    with_ext: WithExt = False, recursive: Recursive = False, apply: Apply = False,
    force_unique: Unique = False, show_all: ShowAll = False,
) -> None:
    """Text an den Anfang des Namens setzen."""
    _run(Prepend(text, not with_ext), paths, recursive, apply, force_unique, show_all)


@rename.command()
def remove(
    paths: Paths, count: Annotated[int, typer.Option("--count", "-n", help="Anzahl Zeichen")],
    start: Annotated[int, typer.Option(help="Startposition (1 = erstes Zeichen)")] = 1,
    from_end: Annotated[bool, typer.Option("--from-end", help="Am Ende entfernen")] = False,
    with_ext: WithExt = False, recursive: Recursive = False, apply: Apply = False,
    force_unique: Unique = False, show_all: ShowAll = False,
) -> None:
    """Zeichen entfernen (ab Position oder am Ende)."""
    op = RemoveChars(count, start, "from_end" if from_end else "range", not with_ext)
    _run(op, paths, recursive, apply, force_unique, show_all)


@rename.command()
def insert(
    paths: Paths, text: Annotated[str, typer.Option("--text", "-t")],
    index: Annotated[int, typer.Option(help="Position (0 = ganz vorn)")] = 0,
    from_end: Annotated[bool, typer.Option("--from-end")] = False,
    pad_to: Annotated[int, typer.Option(help="Auf diese Länge auffüllen")] = 0,
    with_ext: WithExt = False, recursive: Recursive = False, apply: Apply = False,
    force_unique: Unique = False, show_all: ShowAll = False,
) -> None:
    """Zeichen an einer Position einfügen oder den Namen auffüllen."""
    _run(InsertChars(text, index, from_end, pad_to, not with_ext), paths, recursive, apply,
         force_unique, show_all)


@rename.command("case")
def change_case(
    paths: Paths,
    mode: Annotated[str, typer.Option(help="title, lower oder upper")] = "title",
    with_ext: WithExt = False, recursive: Recursive = False, apply: Apply = False,
    force_unique: Unique = False, show_all: ShowAll = False,
) -> None:
    """Gross-/Kleinschreibung ändern."""
    if mode not in ("title", "lower", "upper"):
        raise typer.BadParameter("mode muss title, lower oder upper sein")
    _run(ChangeCase(mode, not with_ext), paths, recursive, apply, force_unique, show_all)  # type: ignore[arg-type]


@rename.command()
def sequence(
    paths: Paths, label: Annotated[str, typer.Option(help="Name vor/nach der Nummer")] = "",
    digits: Annotated[int, typer.Option(min=1, max=6)] = 3,
    start: Annotated[int, typer.Option()] = 1,
    position: Annotated[str, typer.Option(help="append, prepend oder replace")] = "append",
    number_first: Annotated[bool, typer.Option("--number-first", help="001-Name statt Name-001")] = False,
    sort: Annotated[str, typer.Option(help="custom, name, created oder modified")] = "name",
    descending: Annotated[bool, typer.Option("--descending")] = False,
    with_ext: WithExt = False, recursive: Recursive = False, apply: Apply = False,
    force_unique: Unique = False, show_all: ShowAll = False,
) -> None:
    """Laufnummer hinzufügen."""
    if position not in ("append", "prepend", "replace"):
        raise typer.BadParameter("position muss append, prepend oder replace sein")
    if sort not in ("custom", "name", "created", "modified"):
        raise typer.BadParameter("sort muss custom, name, created oder modified sein")
    op = Sequence(label, digits, start, position, not number_first, "-", sort,  # type: ignore[arg-type]
                  descending, not with_ext)
    _run(op, paths, recursive, apply, force_unique, show_all)


@rename.command("date")
def date_cmd(
    paths: Paths,
    source: Annotated[str, typer.Option(help="custom, created oder modified")] = "modified",
    on: Annotated[str, typer.Option("--on", help="Datum YYYY-MM-DD (bei source=custom)")] = "",
    fmt: Annotated[str, typer.Option("--format", help="strftime-Format")] = "%Y-%m-%d",
    position: Annotated[str, typer.Option(help="append, prepend oder replace")] = "prepend",
    with_ext: WithExt = False, recursive: Recursive = False, apply: Apply = False,
    force_unique: Unique = False, show_all: ShowAll = False,
) -> None:
    """Datum in den Namen einfügen."""
    if source not in ("custom", "created", "modified"):
        raise typer.BadParameter("source muss custom, created oder modified sein")
    if position not in ("append", "prepend", "replace"):
        raise typer.BadParameter("position muss append, prepend oder replace sein")
    custom: Date | None = None
    if source == "custom":
        try:
            custom = Date.fromisoformat(on)
        except ValueError as exc:
            raise typer.BadParameter("--on braucht ein Datum als YYYY-MM-DD") from exc
    op = DateStamp(source, custom, fmt, position, "_", not with_ext)  # type: ignore[arg-type]
    _run(op, paths, recursive, apply, force_unique, show_all)


OutDir = Annotated[str, typer.Option("--to", "-o", help="Zielordner (leer = neben der Quelle)")]


@convert.command("cbr2cbz")
def convert_cbr2cbz(
    paths: Paths, to: OutDir = "",
    copy_cbz: Annotated[bool, typer.Option("--copy-cbz", help="Vorhandene CBZ mitkopieren")] = False,
    copy_pdf: Annotated[bool, typer.Option("--copy-pdf", help="PDF mitkopieren")] = False,
    recursive: Recursive = True, apply: Apply = False, show_all: ShowAll = False,
) -> None:
    """CBR (RAR) zu CBZ (ZIP), Seiten bleiben bitidentisch. Braucht unar."""
    _run(CbrToCbz(to, copy_cbz, copy_pdf), paths, recursive, apply, False, show_all)


@convert.command("images")
def convert_images(
    paths: Paths, to: OutDir = "",
    fmt: Annotated[str, typer.Option("--format", help="jpg, png oder webp")] = "jpg",
    quality: Annotated[int, typer.Option(min=1, max=100)] = 85,
    max_edge: Annotated[int, typer.Option(help="Längste Seite in Pixeln, 0 = Original")] = 0,
    recursive: Recursive = False, apply: Apply = False, show_all: ShowAll = False,
) -> None:
    """Bilder in JPG, PNG oder WebP umwandeln, optional verkleinern."""
    if fmt not in ("jpg", "png", "webp"):
        raise typer.BadParameter("format muss jpg, png oder webp sein")
    _run(ConvertImages(to, fmt, quality, max_edge), paths, recursive, apply, False, show_all)  # type: ignore[arg-type]


@app.command("move")
def move_files(
    paths: Paths,
    to: Annotated[str, typer.Option("--to", "-o", help="Zielordner (wird angelegt)")],
    keep_structure: Annotated[bool, typer.Option("--keep-structure", help="Unterordner nachbauen")] = False,
    recursive: Recursive = False, apply: Apply = False, force_unique: Unique = False,
    show_all: ShowAll = False,
) -> None:
    """Dateien in einen anderen Ordner verschieben (auch auf ein anderes Laufwerk)."""
    _run(MoveToFolder(to, keep_structure), paths, recursive, apply, force_unique, show_all)


@app.command()
def serve(
    port: Annotated[int, typer.Option(help="Port")] = 8765,
    reload: Annotated[bool, typer.Option(help="Nur für die Entwicklung")] = False,
) -> None:
    """Web-Oberfläche starten (nur lokal erreichbar)."""
    import uvicorn

    if reload:
        uvicorn.run("procurator.server.main:app", host="127.0.0.1", port=port, reload=True)
    else:
        from .server.main import STATIC
        from .server.main import app as web_app

        if not STATIC.is_dir():
            console.print("[yellow]Die Web-Oberfläche ist noch nicht gebaut: "
                          "cd web && npm install && npm run build[/yellow]")
        console.print(f"Procurator Capsularum läuft auf http://127.0.0.1:{port}")
        console.print("[dim]© 2026 Rüchan Sixt, AGPL-3.0-or-later, ohne jede Gewährleistung.[/dim]")
        uvicorn.run(web_app, host="127.0.0.1", port=port)


@app.command()
def sensitive(
    paths: Paths, recursive: Recursive = True,
) -> None:
    """Zeigt, welche Dateien als sensibel gelten (würden nie an ein Modell gesendet)."""
    cfg, warning = cfgmod.load()
    if warning:
        console.print(f"[yellow]{warning}[/yellow]")
    rules = rules_from_config(cfg)
    hits = [(i, rules.match(i)) for i in scan(paths, recursive=recursive)]
    table = Table()
    table.add_column("Datei")
    table.add_column("Treffer")
    for item, hit in hits:
        if hit:
            table.add_row(str(item.path), hit)
    console.print(table)
    console.print(f"{sum(1 for _, h in hits if h)} von {len(hits)} Dateien sind sensibel.")


@app.command("config")
def show_config() -> None:
    """Pfad und Werte der Konfiguration anzeigen (bearbeiten in der Oberfläche oder per Hand)."""
    cfg, warning = cfgmod.load()
    console.print(f"Datei: {cfgmod.config_path()}")
    if warning:
        console.print(f"[yellow]{warning}[/yellow]")
    ai = cfg.ai
    console.print(f"Anbieter: {ai.provider} · Modell: "
                  f"{ai.claude_model if cfg.is_cloud else ai.ollama_model} · "
                  f"Datenschutzstufe {ai.privacy_level}: {cfgmod.PRIVACY_LEVELS[ai.privacy_level]}")
    if cfg.is_cloud:
        console.print(f"[yellow]Cloud: Dateinamen würden an Anthropic gesendet. Schlüssel aus "
                      f"{ai.api_key_env}: {'gesetzt' if cfgmod.api_key_present(cfg) else 'fehlt'}[/yellow]")
    console.print(f"Sensible Schlüsselwörter: {len(cfg.privacy.sensitive_keywords)}, "
                  f"Endungen: {', '.join(cfg.privacy.sensitive_extensions)}")


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return str(n)


def _with_progress(run):
    """Führt `run(on_progress)` mit einem Fortschrittsbalken aus."""
    with Progress(TextColumn("[dim]{task.fields[name]}[/dim]", justify="left"), BarColumn(),
                  TextColumn("{task.completed}/{task.total}"), console=console,
                  transient=True) as bar:
        task = bar.add_task("", total=1, name="")

        def on_progress(done: int, total: int, name: str) -> None:
            bar.update(task, completed=done, total=max(total, 1), name=name[:50])

        return run(on_progress)


@app.command("index")
def index_cmd(
    paths: Annotated[list[Path] | None, typer.Argument(exists=True, help="Ordner oder Dateien")] = None,
    recursive: Recursive = True,
    info: Annotated[bool, typer.Option("--info", help="Nur den Zustand des Index anzeigen")] = False,
    prune: Annotated[bool, typer.Option("--prune", help="Einträge gelöschter Dateien entfernen")] = False,
) -> None:
    """Datei-Index aktualisieren: merkt sich Grösse, Zeitstempel und Inhalts-Hash jeder Datei."""
    idx = FileIndex()
    if not info and not paths:
        raise typer.BadParameter("Ordner angeben oder --info verwenden")
    if not info:
        items = scan(paths or [], recursive=recursive)
        res = _with_progress(lambda cb: idx.refresh(items, hash_all=True, on_progress=cb))
        console.print(f"{res.seen} Dateien: {res.new} neu, {res.changed} geändert, "
                      f"{res.unchanged} unverändert. {res.hashed} Hashes berechnet"
                      + (f", {res.skipped_links} Links übersprungen" if res.skipped_links else "") + ".")
        for p, msg in res.errors[:10]:
            console.print(f"[red]{p.name}: {msg}[/red]")
        if prune:
            console.print(f"{idx.prune(paths or [])} Einträge gelöschter Dateien entfernt.")
    st = idx.stats()
    console.print(f"Index: {st['files']} Dateien, {st['hashed']} mit Hash, "
                  f"{_human(st['bytes'])} erfasst. Datei: {st['path']} ({_human(st['dbBytes'])})")


@app.command()
def duplicates(
    paths: Paths, recursive: Recursive = True,
    min_size: Annotated[int, typer.Option(help="Kleinere Dateien (in Bytes) ignorieren")] = 1,
    limit: Annotated[int, typer.Option(help="Höchstens so viele Gruppen anzeigen")] = 20,
    move: Annotated[bool, typer.Option("--move", help="Kopien in einen Dubletten-Ordner verschieben (Vorschau)")] = False,
    keep: Annotated[str, typer.Option(help="Welche Datei bleibt: oldest, newest, shortest oder first")] = "oldest",
    to: Annotated[str, typer.Option("--to", "-o", help="Zielordner (leer = _Dubletten im gewählten Ordner)")] = "",
    flat: Annotated[bool, typer.Option("--flat", help="Ohne Ordnerstruktur im Zielordner")] = False,
    apply: Apply = False, force_unique: Unique = False, show_all: ShowAll = False,
) -> None:
    """Gleiche Dateien finden. Mit --move werden die Kopien verschoben (nichts wird gelöscht)."""
    if keep not in ("oldest", "newest", "shortest", "first"):
        raise typer.BadParameter("keep muss oldest, newest, shortest oder first sein")
    items = scan(paths, recursive=recursive)

    if move:
        op = MoveDuplicates(keep, to, not flat, min_size // 1024)  # type: ignore[arg-type]
        _with_progress(lambda cb: op.analyze(items, cb))  # Dateien lesen, Fortschritt zeigen
        _run(op, paths, recursive, apply, force_unique, show_all)
        return

    idx = FileIndex()
    groups, res = _with_progress(lambda cb: idx.duplicates(items, min_size=min_size, on_progress=cb))
    for g in groups[:limit]:
        console.print(f"\n[bold]{len(g.files)} × {_human(g.size)}[/bold]  "
                      f"(Kopien belegen: {_human(g.reclaimable)})  [dim]{g.sha256[:12]}[/dim]")
        for f in g.files:
            extra = g.hardlinks.get(f)
            console.print(f"  {f}" + (f"  [dim](+{len(extra)} Hardlinks)[/dim]" if extra else ""))
    if len(groups) > limit:
        console.print(f"\n… und {len(groups) - limit} weitere Gruppen (mit --limit anzeigen)")
    total = sum(g.reclaimable for g in groups)
    console.print(f"\n{len(groups)} Gruppen gleicher Dateien, {_human(total)} belegt durch Kopien. "
                  f"{res.hashed} Dateien mussten dafür ganz gelesen werden (von {res.seen}).")
    if groups:
        console.print("[dim]Zum Aufräumen: pc duplicates ORDNER --move (Vorschau), dann --apply.[/dim]")
    for p, msg in res.errors[:10]:
        console.print(f"[red]{p.name}: {msg}[/red]")


@app.command()
def history(limit: int = 15) -> None:
    """Letzte Läufe anzeigen."""
    table = Table()
    for col in ("Lauf", "Zeit", "Operation", "Dateien", "Rückgängig"):
        table.add_column(col)
    for b in Journal().batches(limit):
        table.add_row(str(b.id), b.ts, b.operation, str(b.count), "ja" if b.undone else "")
    console.print(table)


@app.command()
def undo(
    batch_id: Annotated[int | None, typer.Argument(help="Lauf-Nummer, Standard: letzter")] = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Nicht nachfragen")] = False,
) -> None:
    """Einen Lauf rückgängig machen. Bei Konvertierungen werden die erzeugten Dateien gelöscht."""
    journal = Journal()
    if batch_id is None:
        batch_id = journal.latest_undoable()
        if batch_id is None:
            console.print("[yellow]Nichts rückgängig zu machen.[/yellow]")
            raise typer.Exit(1)
    convert = journal.batch_kind(batch_id) == "convert"
    if convert and not yes:
        typer.confirm(
            f"Lauf {batch_id}: Die erzeugten Dateien werden gelöscht, die Originale bleiben "
            "unverändert. Fortfahren?", abort=True)
    count, errors = journal.undo(batch_id)
    if convert:
        console.print(f"{count} erzeugte Dateien gelöscht (Lauf {batch_id}). Die Originale sind unverändert.")
    else:
        console.print(f"{count} Dateien zurückbenannt (Lauf {batch_id}).")
    for e in errors:
        console.print(f"[red]{e}[/red]")
    if errors:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
