"""Konvertierungen: erzeugen neue Dateien, die Quelle bleibt unverändert."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Literal

from ..i18n import tr
from ..model import FileItem
from .base import Operation

# --- gemeinsame Basis ---------------------------------------------------------


class ConvertOperation(Operation):
    """Zielordner optional. Ohne Zielordner liegt das Ergebnis neben der Quelle; mit Zielordner
    wird die Ordnerstruktur der Quelle dort nachgebaut."""

    kind = "convert"
    output_dir: str = ""

    def order(self, items: list[FileItem]) -> list[FileItem]:
        return items

    def destination(self, item: FileItem, new_name: str) -> Path:
        if not self.output_dir.strip():
            return item.path.with_name(new_name)
        out = Path(self.output_dir).expanduser().resolve()
        root = (item.root or item.path.parent).resolve()
        if out == root or root in out.parents:
            raise ValueError(tr("Zielordner muss ausserhalb des Quellordners liegen"))
        rel = item.path.resolve().relative_to(root)
        return out / rel.with_name(new_name)


def _atomic_name(dst: Path) -> Path:
    return dst.with_name(dst.name + ".part")


# --- CBR -> CBZ (aus tools/cbr2cbz.py übernommen) ---------------------------------

# Seiten in diesen Formaten sind schon komprimiert: unverändert speichern (bitidentisch).
STORED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".jxl"}
JUNK_NAMES = {"thumbs.db", ".ds_store", "desktop.ini"}
JUNK_DIRS = {"__macosx"}


def _natural_key(path: str) -> list[object]:
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", path)]


def sniff(path: Path) -> str:
    with open(path, "rb") as fh:
        head = fh.read(8)
    if head[:4] == b"PK\x03\x04":
        return "zip"
    if head[:7] == b"Rar!\x1a\x07\x00" or head[:8] == b"Rar!\x1a\x07\x01\x00":
        return "rar"
    return "unknown"


def _is_junk(rel: Path) -> bool:
    return rel.name.lower() in JUNK_NAMES or any(p.lower() in JUNK_DIRS for p in rel.parts)


def _list_rar(archive: Path) -> int:
    """Anzahl Dateien (ohne Ordner und Müll), die das Archiv angibt."""
    r = subprocess.run(["lsar", "-j", str(archive)], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(tr("lsar fehlgeschlagen: {error}", error=r.stderr.strip()[:200]))
    entries = json.loads(r.stdout).get("lsarContents", [])
    return sum(
        1 for e in entries
        if not e.get("XADIsDirectory") and not _is_junk(Path(e.get("XADFileName", "")))
    )


def _extract_rar(archive: Path, out: Path) -> None:
    r = subprocess.run(["unar", "-q", "-D", "-o", str(out), str(archive)],
                       capture_output=True, text=True)
    if r.returncode == 0:
        return
    tar = subprocess.run(["bsdtar", "-xf", str(archive), "-C", str(out)],
                         capture_output=True, text=True)
    if tar.returncode == 0:
        return
    raise RuntimeError(tr("unar fehlgeschlagen: {error}", error=(r.stderr or r.stdout).strip()[:200]))


def _build_cbz(folder: Path, target: Path) -> int:
    files = [p for p in folder.rglob("*") if p.is_file() and not _is_junk(p.relative_to(folder))]
    if not files:
        raise RuntimeError(tr("Archiv enthält keine Dateien"))
    files.sort(key=lambda p: _natural_key(p.relative_to(folder).as_posix()))
    with zipfile.ZipFile(target, "w", allowZip64=True) as zf:
        for p in files:
            method = zipfile.ZIP_STORED if p.suffix.lower() in STORED_EXTS else zipfile.ZIP_DEFLATED
            zf.write(p, p.relative_to(folder).as_posix(), compress_type=method)
    return len(files)


def _verify_zip(target: Path, expected: int | None = None) -> None:
    with zipfile.ZipFile(target) as zf:
        bad = zf.testzip()
        if bad:
            raise RuntimeError(tr("Beschädigter Eintrag im Ergebnis: {name}", name=bad))
        if expected is not None and len(zf.namelist()) != expected:
            raise RuntimeError(tr("{n} Einträge, erwartet {expected}", n=len(zf.namelist()), expected=expected))


@dataclass
class CbrToCbz(ConvertOperation):
    """CBR (RAR) zu CBZ (ZIP) ohne Neukomprimierung der Seiten."""

    name: ClassVar[str] = "cbr2cbz"
    output_dir: str = ""
    copy_cbz: bool = False
    copy_pdf: bool = False

    def transform(self, item: FileItem, index: int) -> str | None:
        ext = item.suffix.lower()
        if ext == ".cbr":
            return item.path.stem + ".cbz"
        copy_wanted = (ext == ".cbz" and self.copy_cbz) or (ext == ".pdf" and self.copy_pdf)
        if copy_wanted and self.output_dir.strip():
            return item.name  # unverändert in den Zielordner kopieren
        return None

    def check(self, item: FileItem) -> str | None:
        if item.suffix.lower() == ".cbr" and (shutil.which("unar") is None
                                              or shutil.which("lsar") is None):
            return tr("unar fehlt (brew install unar)")
        return None

    def convert(self, src: Path, dst: Path) -> str | None:
        dst.parent.mkdir(parents=True, exist_ok=True)
        part = _atomic_name(dst)
        try:
            if src.suffix.lower() != ".cbr":
                shutil.copyfile(src, part)
                os.replace(part, dst)
                return tr("kopiert")
            kind = sniff(src)
            if kind == "zip":  # .cbr, das in Wahrheit ein ZIP ist
                shutil.copyfile(src, part)
                _verify_zip(part)
                os.replace(part, dst)
                return tr("war ein ZIP, nur umbenannt")
            if kind != "rar":
                raise RuntimeError(tr("Weder RAR noch ZIP"))
            # Arbeitsordner neben dem Ziel: unar kann auf manchen externen Laufwerken nicht lesen,
            # und das Ziel hat sicher genug Platz.
            with tempfile.TemporaryDirectory(dir=dst.parent, prefix=".pc-work-") as td:
                work = Path(td)
                local = work / "source.rar"
                shutil.copyfile(src, local)
                expected = _list_rar(local)
                pages = work / "pages"
                pages.mkdir()
                _extract_rar(local, pages)
                local.unlink()
                count = _build_cbz(pages, part)
            if count != expected:
                raise RuntimeError(tr("{count} Dateien entpackt, Archiv nennt {expected}", count=count, expected=expected))
            _verify_zip(part, count)
            os.replace(part, dst)
            return tr("konvertiert ({count} Seiten)", count=count)
        finally:
            part.unlink(missing_ok=True)


# --- Bilder ------------------------------------------------------------------

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".tif", ".tiff", ".bmp"}
_PIL_FORMAT = {"jpg": "JPEG", "png": "PNG", "webp": "WEBP"}


def _register_heif() -> None:
    try:  # HEIC/HEIF, falls pillow-heif installiert ist
        import pillow_heif

        pillow_heif.register_heif_opener()
    except ImportError:
        pass


@dataclass
class ConvertImages(ConvertOperation):
    """Bilder in JPG, PNG oder WebP umwandeln, optional verkleinern."""

    name: ClassVar[str] = "images"
    output_dir: str = ""
    format: Literal["jpg", "png", "webp"] = "jpg"
    quality: int = 85
    max_edge: int = 0  # längste Seite in Pixeln, 0 = Originalgrösse

    def transform(self, item: FileItem, index: int) -> str | None:
        ext = item.suffix.lower()
        if ext not in IMAGE_EXTS:
            return None
        same = ext.lstrip(".").replace("jpeg", "jpg") == self.format
        if same:
            if self.max_edge <= 0 or not self._too_big(item.path):
                return None  # nichts zu tun, nicht unnötig neu komprimieren
        return f"{item.path.stem}.{self.format}"

    def _too_big(self, path: Path) -> bool:
        from PIL import Image

        _register_heif()
        try:
            with Image.open(path) as im:  # liest nur den Kopf
                return max(im.size) > self.max_edge
        except Exception:
            return True  # unlesbar: Fehler erst beim Konvertieren melden

    def convert(self, src: Path, dst: Path) -> str | None:
        from PIL import Image, ImageOps

        _register_heif()

        dst.parent.mkdir(parents=True, exist_ok=True)
        part = _atomic_name(dst)
        try:
            with Image.open(src) as opened:
                img = ImageOps.exif_transpose(opened)
                before = img.size
                if self.max_edge > 0 and max(img.size) > self.max_edge:
                    img.thumbnail((self.max_edge, self.max_edge), Image.Resampling.LANCZOS)
                if self.format == "jpg" and img.mode not in ("RGB", "L"):
                    if "A" in img.getbands():  # Transparenz auf Weiss
                        base = Image.new("RGB", img.size, (255, 255, 255))
                        base.paste(img.convert("RGBA"), mask=img.convert("RGBA").getchannel("A"))
                        img = base
                    else:
                        img = img.convert("RGB")
                options: dict[str, object] = {}
                if self.format in ("jpg", "webp"):
                    options["quality"] = max(1, min(100, self.quality))
                    options["exif"] = img.getexif()
                img.save(part, format=_PIL_FORMAT[self.format], **options)
                after = img.size
            os.replace(part, dst)
            return f"{before[0]}x{before[1]} → {after[0]}x{after[1]}"
        finally:
            part.unlink(missing_ok=True)
