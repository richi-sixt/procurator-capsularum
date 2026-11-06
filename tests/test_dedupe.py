import os
from pathlib import Path

from procurator.engine import apply_plan, make_plan
from procurator.model import Status
from procurator.ops import MoveDuplicates
from procurator.scanner import scan


def write(folder: Path, name: str, data: bytes, mtime: int | None = None) -> Path:
    p = folder / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    if mtime is not None:
        os.utime(p, ns=(mtime * 10**9, mtime * 10**9))
    return p


def run(op: MoveDuplicates, folder, **kw):
    """Analysieren, dann planen, wie es die Oberfläche tut."""
    items = scan(folder, recursive=True)
    op.analyze(items)
    return make_plan(op, items, **kw)


def by_name(plan):
    return {c.src.name: c for c in plan.changes}


def names(folder: Path) -> list[str]:
    return sorted(str(p.relative_to(folder)) for p in folder.rglob("*") if p.is_file())


def test_oldest_is_kept_and_copies_are_moved_with_structure(folder):
    write(folder, "neu/foto.jpg", b"inhalt" * 100, mtime=3000)
    write(folder, "alt/foto.jpg", b"inhalt" * 100, mtime=1000)
    write(folder, "mitte/kopie.jpg", b"inhalt" * 100, mtime=2000)
    write(folder, "einzeln.jpg", b"anders")
    plan = run(MoveDuplicates(), folder)
    moved = sorted(str(c.dst.relative_to(folder)) for c in plan.changes if c.dst)
    assert moved == ["_Dubletten/mitte/kopie.jpg", "_Dubletten/neu/foto.jpg"]
    result = apply_plan(plan)
    assert not result.failed
    assert names(folder) == ["_Dubletten/mitte/kopie.jpg", "_Dubletten/neu/foto.jpg",
                             "alt/foto.jpg", "einzeln.jpg"]


def test_keep_rules(folder):
    write(folder, "a/x.bin", b"gleich" * 50, mtime=2000)
    write(folder, "b/lang/tief/x.bin", b"gleich" * 50, mtime=1000)
    write(folder, "c/x.bin", b"gleich" * 50, mtime=3000)

    def kept(rule):
        plan = run(MoveDuplicates(keep=rule), folder)
        return [str(c.src.relative_to(folder)) for c in plan.changes if c.status != Status.OK
                and c.src.name == "x.bin" and "Behalten" in c.reason]

    assert kept("oldest") == ["b/lang/tief/x.bin"]
    assert kept("newest") == ["c/x.bin"]
    assert kept("shortest") in (["a/x.bin"], ["c/x.bin"])  # gleich kurz: einer von beiden
    assert kept("first") == ["a/x.bin"]


def test_exactly_one_file_per_group_always_stays(folder):
    for i in range(5):
        write(folder, f"d{i}/gleich.bin", b"X" * 300, mtime=1000 + i)
    write(folder, "e1.bin", b"Y" * 300, mtime=1)
    write(folder, "e2.bin", b"Y" * 300, mtime=2)
    apply_plan(run(MoveDuplicates(), folder))
    remaining = [p for p in folder.rglob("*") if p.is_file() and "_Dubletten" not in p.parts]
    assert len(remaining) == 2  # genau eine pro Gruppe
    assert sum(1 for p in remaining if p.name == "gleich.bin") == 1
    assert sum(1 for p in remaining if p.name.startswith("e")) == 1
    assert len(list((folder / "_Dubletten").rglob("*.bin"))) == 5  # 4 + 1 verschoben, nichts gelöscht


def test_reasons_are_shown(folder):
    write(folder, "a.bin", b"gleich" * 20, mtime=1)
    write(folder, "b.bin", b"gleich" * 20, mtime=2)
    write(folder, "c.bin", b"anders")
    by = by_name(run(MoveDuplicates(), folder))
    assert by["b.bin"].status == Status.OK and by["b.bin"].reason == "Dublette von a.bin"
    assert by["a.bin"].status == Status.SKIP and "Behalten (älteste), 1 Kopie davon" in by["a.bin"].reason
    assert by["c.bin"].status == Status.SKIP and by["c.bin"].reason == "Keine Dublette"


def test_already_moved_copies_are_ignored_on_rerun(folder):
    write(folder, "a.bin", b"gleich" * 20, mtime=1)
    write(folder, "b.bin", b"gleich" * 20, mtime=2)
    apply_plan(run(MoveDuplicates(), folder))
    plan = run(MoveDuplicates(), folder)  # zweiter Lauf
    assert not any(c.status == Status.OK for c in plan.changes)
    moved = [c for c in plan.changes if "Dubletten-Ordner" in c.reason]
    assert len(moved) == 1


def test_custom_target_dir_and_flat_with_force_unique(folder, tmp_path):
    write(folder, "x/a.bin", b"gleich" * 20, mtime=1)
    write(folder, "y/a.bin", b"gleich" * 20, mtime=2)
    write(folder, "z/a.bin", b"gleich" * 20, mtime=3)
    out = tmp_path / "ziel"
    plan = run(MoveDuplicates(target_dir=str(out), keep_structure=False), folder)
    assert all(c.status == Status.CONFLICT for c in plan.changes if c.dst)  # gleicher Name zweimal
    plan = run(MoveDuplicates(target_dir=str(out), keep_structure=False), folder, force_unique=True)
    apply_plan(plan)
    assert sorted(p.name for p in out.iterdir()) == ["a 1.bin", "a.bin"]


def test_custom_target_inside_scan_root_is_not_rescanned(folder):
    write(folder, "a.bin", b"gleich" * 20, mtime=1)
    write(folder, "b.bin", b"gleich" * 20, mtime=2)
    target = folder / "sammlung"
    apply_plan(run(MoveDuplicates(target_dir=str(target)), folder))
    plan = run(MoveDuplicates(target_dir=str(target)), folder)
    assert not any(c.status == Status.OK for c in plan.changes)


def test_hardlinks_stay_and_all_names_of_a_copy_move_together(folder):
    a = write(folder, "behalten.bin", b"inhalt" * 50, mtime=1)
    os.link(a, folder / "behalten-link.bin")  # zweiter Name der behaltenen Datei
    k = write(folder, "kopie.bin", b"inhalt" * 50, mtime=5)
    os.link(k, folder / "kopie-link.bin")  # zweiter Name der Kopie
    plan = run(MoveDuplicates(), folder)
    by = by_name(plan)
    # Von den zwei Namen der behaltenen Datei bleibt einer «Behalten», der andere ist der Hardlink
    kept_names = {by["behalten.bin"].reason.split(",")[0].split(" (")[0],
                  by["behalten-link.bin"].reason.split(",")[0].split(" (")[0]}
    assert by["behalten.bin"].status == Status.SKIP and by["behalten-link.bin"].status == Status.SKIP
    assert any("Hardlink" in by[n].reason for n in ("behalten.bin", "behalten-link.bin"))
    assert kept_names == {"Behalten", "Zweiter Name derselben behaltenen Datei"}
    assert by["kopie.bin"].status == Status.OK and by["kopie-link.bin"].status == Status.OK
    apply_plan(plan)
    assert names(folder) == ["_Dubletten/kopie-link.bin", "_Dubletten/kopie.bin",
                             "behalten-link.bin", "behalten.bin"]


def test_preview_without_analysis_reads_nothing_and_reports_pending(folder, monkeypatch):
    from procurator import index as idxmod

    write(folder, "a.bin", b"gleich" * 20)
    write(folder, "b.bin", b"gleich" * 20)
    reads = []
    monkeypatch.setattr(idxmod, "_full_hash", lambda p: reads.append(p) or "x")
    monkeypatch.setattr(idxmod, "_partial_hash", lambda p: reads.append(p) or "x")
    plan = make_plan(MoveDuplicates(), scan(folder))  # ohne Analyse
    assert reads == []  # die Vorschau liest keine Datei
    assert not any(c.status == Status.OK for c in plan.changes)
    assert plan.info["pendingFiles"] == 2 and plan.info["duplicates"] == 0
    assert all("Analyse unvollständig" in c.reason for c in plan.changes)
    assert plan.needs_analysis is True


def test_after_analysis_the_preview_is_complete_and_fast(folder, monkeypatch):
    from procurator import index as idxmod

    write(folder, "a.bin", b"gleich" * 20, mtime=1)
    write(folder, "b.bin", b"gleich" * 20, mtime=2)
    write(folder, "c.bin", b"anders" * 20)
    run(MoveDuplicates(), folder)  # Analyse
    reads = []
    monkeypatch.setattr(idxmod, "_full_hash", lambda p: reads.append(p) or "x")
    monkeypatch.setattr(idxmod, "_partial_hash", lambda p: reads.append(p) or "x")
    plan = make_plan(MoveDuplicates(), scan(folder))
    assert reads == [] and plan.info["pendingFiles"] == 0
    assert plan.info["duplicates"] == 1 and plan.info["groups"] == 1 and plan.info["bytes"] == 120


def test_changed_file_needs_a_new_analysis(folder):
    a = write(folder, "a.bin", b"gleich" * 20, mtime=1)
    write(folder, "b.bin", b"gleich" * 20, mtime=2)
    run(MoveDuplicates(), folder)
    a.write_bytes(b"ganz anders" * 20)  # Inhalt und Grösse ändern sich
    plan = make_plan(MoveDuplicates(), scan(folder))
    assert not any(c.status == Status.OK for c in plan.changes)


def test_min_size_ignores_small_files(folder):
    write(folder, "a.bin", b"klein", mtime=1)
    write(folder, "b.bin", b"klein", mtime=2)
    assert not any(c.status == Status.OK for c in run(MoveDuplicates(min_size_kb=1), folder).changes)
    assert any(c.status == Status.OK for c in run(MoveDuplicates(min_size_kb=0), folder).changes)


def test_undo_brings_everything_back_and_removes_the_empty_dir(folder, journal):
    write(folder, "a/x.bin", b"gleich" * 20, mtime=1)
    write(folder, "b/x.bin", b"gleich" * 20, mtime=2)
    before = names(folder)
    result = apply_plan(run(MoveDuplicates(), folder), journal)
    assert names(folder) != before and (folder / "_Dubletten").is_dir()
    journal.undo(result.batch_id)
    assert names(folder) == before and not (folder / "_Dubletten").exists()


def test_empty_files_and_unique_files_are_never_moved(folder):
    write(folder, "leer1", b"")
    write(folder, "leer2", b"")
    write(folder, "u1", b"eins")
    write(folder, "u2", b"zwei")
    assert not any(c.status == Status.OK for c in run(MoveDuplicates(), folder).changes)


def test_two_selected_folders_are_compared_with_each_other(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    write(a, "x.bin", b"gleich" * 20, mtime=1)
    write(b, "x.bin", b"gleich" * 20, mtime=2)
    items = scan([a, b], recursive=True)
    op = MoveDuplicates()
    op.analyze(items)
    plan = make_plan(op, items)
    ok = [c for c in plan.changes if c.status == Status.OK]
    assert len(ok) == 1 and ok[0].src == b / "x.bin"
    assert ok[0].dst == b / "_Dubletten" / "x.bin"  # _Dubletten im Ordner der Kopie
