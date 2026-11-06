import os
import threading
from pathlib import Path

import pytest
from typer.testing import CliRunner

from procurator import index as idxmod
from procurator.cli import app as cli_app
from procurator.index import FileIndex
from procurator.scanner import scan


@pytest.fixture
def idx(tmp_path) -> FileIndex:
    return FileIndex(tmp_path / "idx.db")


@pytest.fixture
def counters(monkeypatch):
    """Zählt, wie oft Dateien gelesen werden."""
    calls = {"full": [], "partial": []}
    real_full, real_partial = idxmod._full_hash, idxmod._partial_hash
    monkeypatch.setattr(idxmod, "_full_hash", lambda p: (calls["full"].append(Path(p).name), real_full(p))[1])
    monkeypatch.setattr(idxmod, "_partial_hash", lambda p: (calls["partial"].append(Path(p).name), real_partial(p))[1])
    return calls


def write(folder: Path, name: str, data: bytes) -> Path:
    p = folder / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


# ---------- Index ----------


def test_refresh_records_and_skips_unchanged_files(idx, folder, counters):
    write(folder, "a.bin", b"aaa")
    write(folder, "b.bin", b"bbbb")
    r1 = idx.refresh(scan(folder), hash_all=True)
    assert (r1.seen, r1.new, r1.hashed) == (2, 2, 2)
    assert sorted(counters["full"]) == ["a.bin", "b.bin"]
    counters["full"].clear()
    r2 = idx.refresh(scan(folder), hash_all=True)
    assert (r2.new, r2.changed, r2.unchanged, r2.hashed) == (0, 0, 2, 0)
    assert counters["full"] == []  # nichts erneut gelesen
    assert idx.stats()["files"] == 2 and idx.stats()["hashed"] == 2


def test_changed_file_is_rehashed_and_first_seen_is_kept(idx, folder):
    p = write(folder, "a.bin", b"alt")
    idx.refresh(scan(folder), hash_all=True)
    before = idx.lookup(p)
    p.write_bytes(b"neuer inhalt")
    os.utime(p, ns=(1, before["mtime_ns"] + 5_000_000_000))
    res = idx.refresh(scan(folder), hash_all=True)
    after = idx.lookup(p)
    assert res.changed == 1 and res.hashed == 1
    assert after["sha256"] != before["sha256"] and after["first_seen"] == before["first_seen"]


def test_same_size_and_time_means_unchanged_even_if_content_differs(idx, folder):
    """Bewusste Regel: Grösse und Zeitstempel entscheiden, sonst müsste alles neu gelesen werden."""
    p = write(folder, "a.bin", b"1234")
    st = p.stat()
    idx.refresh(scan(folder), hash_all=True)
    p.write_bytes(b"abcd")
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns))
    assert idx.refresh(scan(folder), hash_all=True).unchanged == 1


def test_symlinks_are_skipped(idx, folder):
    t = write(folder, "echt.bin", b"x")
    (folder / "link.bin").symlink_to(t)
    res = idx.refresh(scan(folder), hash_all=True)
    assert res.seen == 1 and res.skipped_links == 1


def test_prune_removes_entries_of_deleted_files(idx, folder):
    a, b = write(folder, "a.bin", b"1"), write(folder, "b.bin", b"2")
    idx.refresh(scan(folder), hash_all=True)
    b.unlink()
    assert idx.prune([folder]) == 1
    assert idx.lookup(a) is not None and idx.lookup(b) is None
    assert idx.prune([folder]) == 0


def test_paths_with_hash_finds_known_content(idx, folder):
    a = write(folder, "a.bin", b"gleich")
    write(folder, "b.bin", b"gleich")
    idx.refresh(scan(folder), hash_all=True)
    sha = idx.lookup(a)["sha256"]
    assert sorted(p.name for p in idx.paths_with_hash(sha)) == ["a.bin", "b.bin"]
    assert idx.lookup(folder / "unbekannt") is None


def test_cancel_keeps_what_was_done(idx, folder):
    for n in "abc":
        write(folder, f"{n}.bin", n.encode())
    cancel = threading.Event()

    def progress(done, total, name):
        if done == 1:
            cancel.set()

    res = idx.refresh(scan(folder), hash_all=True, on_progress=progress, cancel=cancel)
    assert res.cancelled and 0 < idx.stats()["files"] < 3


def test_unreadable_file_is_reported_not_fatal(idx, folder):
    ok = write(folder, "ok.bin", b"1")
    bad = write(folder, "bad.bin", b"2")
    bad.chmod(0)
    try:
        res = idx.refresh(scan(folder), hash_all=True)
    finally:
        bad.chmod(0o600)
    if os.geteuid() != 0:
        assert [p.name for p, _ in res.errors] == ["bad.bin"]
    assert idx.lookup(ok)["sha256"]


# ---------- Dubletten ----------


def test_duplicate_groups_found(idx, folder):
    write(folder, "a.txt", b"inhalt A" * 100)
    write(folder, "sub/a kopie.txt", b"inhalt A" * 100)
    write(folder, "b.txt", b"inhalt B" * 100)
    write(folder, "c.txt", b"x")
    groups, _ = idx.duplicates(scan(folder, recursive=True))
    assert len(groups) == 1
    g = groups[0]
    assert sorted(p.name for p in g.files) == ["a kopie.txt", "a.txt"]
    assert g.size == 800 and g.reclaimable == 800


def test_only_necessary_files_are_read(idx, folder, counters):
    """Verschiedene Grösse: nie gelesen. Gleiche Grösse, anderer Anfang: nur Anfang gelesen."""
    write(folder, "klein.bin", b"x" * 10)                       # Grösse einzigartig
    write(folder, "gross.bin", b"y" * 200_000)                  # Grösse einzigartig
    write(folder, "p1.bin", b"A" * 100 + b"z" * 100_000)        # gleiche Grösse, anderer Anfang
    write(folder, "p2.bin", b"B" * 100 + b"z" * 100_000)
    write(folder, "d1.bin", b"C" * 150_000)                     # echte Dublette
    write(folder, "d2.bin", b"C" * 150_000)
    groups, res = idx.duplicates(scan(folder))
    assert [sorted(p.name for p in g.files) for g in groups] == [["d1.bin", "d2.bin"]]
    assert sorted(counters["partial"]) == ["d1.bin", "d2.bin", "p1.bin", "p2.bin"]
    assert sorted(counters["full"]) == ["d1.bin", "d2.bin"]  # p1/p2 nur Anfang, klein/gross nie
    assert res.hashed == 2


def test_second_run_reads_nothing(idx, folder, counters):
    write(folder, "d1.bin", b"C" * 1000)
    write(folder, "d2.bin", b"C" * 1000)
    idx.duplicates(scan(folder))
    counters["full"].clear()
    counters["partial"].clear()
    groups, _ = idx.duplicates(scan(folder))
    assert len(groups) == 1 and counters == {"full": [], "partial": []}


def test_empty_files_are_not_duplicates(idx, folder):
    write(folder, "leer1.txt", b"")
    write(folder, "leer2.txt", b"")
    assert idx.duplicates(scan(folder))[0] == []


def test_min_size(idx, folder):
    write(folder, "a", b"gleich")
    write(folder, "b", b"gleich")
    assert idx.duplicates(scan(folder), min_size=100)[0] == []
    assert len(idx.duplicates(scan(folder), min_size=1)[0]) == 1


def test_hardlinks_are_one_physical_file(idx, folder):
    a = write(folder, "a.bin", b"inhalt" * 50)
    os.link(a, folder / "hardlink.bin")
    write(folder, "kopie.bin", b"inhalt" * 50)
    groups, _ = idx.duplicates(scan(folder))
    assert len(groups) == 1 and len(groups[0].files) == 2  # Hardlink zählt nicht als Kopie
    assert groups[0].reclaimable == 300
    assert sum(len(v) for v in groups[0].hardlinks.values()) == 1


def test_only_hardlinks_is_no_duplicate_group(idx, folder):
    a = write(folder, "a.bin", b"inhalt")
    os.link(a, folder / "b.bin")
    assert idx.duplicates(scan(folder))[0] == []


def test_symlink_is_not_a_duplicate(idx, folder):
    a = write(folder, "a.bin", b"inhalt")
    (folder / "link.bin").symlink_to(a)
    assert idx.duplicates(scan(folder))[0] == []


def test_duplicates_only_consider_given_items(idx, folder, tmp_path):
    other = tmp_path / "andere"
    write(folder, "a.bin", b"gleich")
    write(other, "b.bin", b"gleich")
    idx.refresh(scan(other), hash_all=True)  # bekannt, aber nicht Teil dieser Suche
    assert idx.duplicates(scan(folder))[0] == []
    assert len(idx.duplicates(scan([folder, other]))[0]) == 1


def test_groups_sorted_by_reclaimable_space(idx, folder):
    write(folder, "k1", b"k" * 10)
    write(folder, "k2", b"k" * 10)
    write(folder, "g1", b"g" * 5000)
    write(folder, "g2", b"g" * 5000)
    groups, _ = idx.duplicates(scan(folder))
    assert [g.size for g in groups] == [5000, 10]


def test_file_changing_during_hashing_is_not_stored(idx, folder, monkeypatch):
    p = write(folder, "a.bin", b"abc")
    real = idxmod._full_hash

    def racy(path):
        digest = real(path)
        Path(path).write_bytes(b"geaendert und laenger")  # ändert sich während des Lesens
        return digest

    monkeypatch.setattr(idxmod, "_full_hash", racy)
    res = idx.refresh(scan(folder), hash_all=True)
    assert res.errors and "geändert" in res.errors[0][1]
    assert idx.lookup(p)["sha256"] is None


# ---------- CLI ----------


def test_cli_index_and_duplicates(folder, tmp_path):
    write(folder, "a.bin", b"gleich" * 20)
    write(folder, "b.bin", b"gleich" * 20)
    env = {"COLUMNS": "300"}
    out = CliRunner().invoke(cli_app, ["index", str(folder)], env=env).output
    assert "2 Dateien: 2 neu" in out and "2 Hashes" in out
    out = CliRunner().invoke(cli_app, ["index", str(folder)], env=env).output
    assert "2 unverändert" in out and "0 Hashes" in out
    out = CliRunner().invoke(cli_app, ["duplicates", str(folder)], env=env).output
    assert "1 Gruppen gleicher Dateien" in out and "a.bin" in out and "b.bin" in out
    out = CliRunner().invoke(cli_app, ["index", "--info"], env=env).output
    assert "2 Dateien" in out


def test_cli_index_needs_a_folder_or_info():
    assert CliRunner().invoke(cli_app, ["index"]).exit_code != 0


def test_files_differing_only_after_the_first_64kb_are_not_duplicates(idx, folder, counters):
    """Gleiche Grösse und gleicher Anfang: erst der volle Hash entscheidet."""
    head = b"H" * idxmod.PARTIAL_BYTES
    write(folder, "e1.bin", head + b"ende eins")
    write(folder, "e2.bin", head + b"ende zwei")
    groups, res = idx.duplicates(scan(folder))
    assert groups == []
    assert sorted(counters["full"]) == ["e1.bin", "e2.bin"] and res.hashed == 2
