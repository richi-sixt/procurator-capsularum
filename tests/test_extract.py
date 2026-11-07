"""Text-Auszug für Stufe 2: PDF und Office, mit selbst erzeugten Kleinstdateien."""

import json
import zipfile
from pathlib import Path

from procurator import config as cfgmod
from procurator.ai import extract
from procurator.ai.organizer import build_payload
from procurator.scanner import scan


def make_pdf(path: Path, text: str, pages: int = 1) -> Path:
    """Ein winziges, gültiges PDF mit Text (Seitenverweise und Verweistabelle werden mitgeschrieben)."""
    objs: list[bytes] = [b"<< /Type /Catalog /Pages 2 0 R >>"]
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(pages))
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {pages} >>".encode())
    font_id = 3 + 2 * pages
    for i in range(pages):
        content_id = 4 + 2 * i
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Contents {content_id} 0 R "
                    f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>".encode())
        stream = f"BT /F1 12 Tf 20 100 Td ({text} Seite {i + 1}) Tj ET".encode()
        objs.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for n, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (n, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    path.write_bytes(bytes(out))
    return path


def make_zip(path: Path, parts: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in parts.items():
            zf.writestr(name, content)
    return path


def test_pdf_text_is_read(tmp_path):
    pdf = make_pdf(tmp_path / "rechnung.pdf", "Rechnung Swisscom")
    assert extract.excerpt(pdf).startswith("Rechnung Swisscom Seite 1")


def test_pdf_reads_only_the_first_pages(tmp_path):
    pdf = make_pdf(tmp_path / "lang.pdf", "Text", pages=10)
    text = extract.excerpt(pdf)
    assert "Seite 3" in text and "Seite 4" not in text


def test_broken_pdf_gives_empty_excerpt(tmp_path):
    bad = tmp_path / "kaputt.pdf"
    bad.write_bytes(b"%PDF-1.4\nkein echter Inhalt")
    assert extract.excerpt(bad) == ""
    empty = tmp_path / "leer.pdf"
    empty.write_bytes(b"")
    assert extract.excerpt(empty) == ""


def test_huge_pdf_is_not_opened(tmp_path, monkeypatch):
    pdf = make_pdf(tmp_path / "gross.pdf", "Inhalt")
    monkeypatch.setattr(extract, "MAX_PDF_BYTES", 10)
    assert extract.excerpt(pdf) == ""


def test_docx_text_is_read_with_entities_and_paragraphs(tmp_path):
    xml = ('<w:document><w:body><w:p><w:r><w:t>Mietvertrag &amp; Nebenkosten</w:t></w:r></w:p>'
           '<w:p><w:r><w:t xml:space="preserve">Wohnung 3</w:t></w:r></w:p></w:body></w:document>')
    doc = make_zip(tmp_path / "vertrag.docx", {"word/document.xml": xml})
    assert extract.excerpt(doc) == "Mietvertrag & Nebenkosten Wohnung 3"


def test_xlsx_reads_shared_strings(tmp_path):
    shared = "<sst><si><t>Budget 2026</t></si><si><t>Ferien</t></si></sst>"
    sheet = '<worksheet><sheetData><row><c r="A1" t="s"><v>0</v></c></row></sheetData></worksheet>'
    xls = make_zip(tmp_path / "plan.xlsx", {"xl/worksheets/sheet1.xml": sheet, "xl/sharedStrings.xml": shared})
    assert extract.excerpt(xls).startswith("Budget 2026 Ferien")


def test_pptx_reads_slides_in_numeric_order(tmp_path):
    def slide(text):
        return f"<p:sld><a:p><a:r><a:t>{text}</a:t></a:r></a:p></p:sld>"

    ppt = make_zip(tmp_path / "vortrag.pptx", {
        "ppt/slides/slide10.xml": slide("zehn"), "ppt/slides/slide2.xml": slide("zwei"),
        "ppt/slides/slide1.xml": slide("eins")})
    assert extract.excerpt(ppt) == "eins zwei zehn"


def test_office_file_that_is_not_a_zip_gives_empty_excerpt(tmp_path):
    fake = tmp_path / "alt.docx"
    fake.write_bytes(b"\xd0\xcf\x11\xe0 altes Format")
    assert extract.excerpt(fake) == ""


def test_office_xml_is_not_parsed_as_xml(tmp_path):
    """Entitäten werden nicht aufgelöst (Schutz vor Entity-Bomben), nur Tags und Standardzeichen."""
    xml = ('<!DOCTYPE d [<!ENTITY a "AAAAAAAAAA"><!ENTITY b "&a;&a;&a;&a;">]>'
           "<w:document><w:p><w:t>Hallo &b;</w:t></w:p></w:document>")
    doc = make_zip(tmp_path / "bombe.docx", {"word/document.xml": xml})
    assert len(extract.excerpt(doc)) < 200


def test_oversized_xml_part_is_cut_not_unpacked(tmp_path, monkeypatch):
    monkeypatch.setattr(extract, "MAX_XML_BYTES", 2000)
    xml = "<w:document>" + "<w:p><w:t>wort </w:t></w:p>" * 100_000 + "</w:document>"
    doc = make_zip(tmp_path / "riesig.docx", {"word/document.xml": xml})
    text = extract.excerpt(doc)
    assert text.startswith("wort") and len(text) <= extract.MAX_EXCERPT_CHARS


def test_excerpt_is_limited_for_every_format(tmp_path):
    xml = "<w:document><w:p><w:t>" + "wort " * 5000 + "</w:t></w:p></w:document>"
    doc = make_zip(tmp_path / "lang.docx", {"word/document.xml": xml})
    assert len(extract.excerpt(doc)) <= extract.MAX_EXCERPT_CHARS


def test_unknown_extension_gives_nothing(tmp_path):
    img = tmp_path / "bild.jpg"
    img.write_bytes(b"binaer")
    assert extract.excerpt(img) == ""


def test_missing_file_gives_nothing(tmp_path):
    assert extract.excerpt(tmp_path / "gibt-es-nicht.pdf") == ""


def test_payload_has_excerpts_for_pdf_and_office_only_from_level_2(folder):
    make_pdf(folder / "rechnung.pdf", "Rechnung Swisscom")
    make_zip(folder / "vertrag.docx",
             {"word/document.xml": "<w:document><w:p><w:t>Mietvertrag</w:t></w:p></w:document>"})
    level1 = {r["name"]: r for r in build_payload(scan(folder), 1)}
    assert all("excerpt" not in r for r in level1.values())
    level2 = {r["name"]: r for r in build_payload(scan(folder), 2)}
    assert level2["rechnung.pdf"]["excerpt"].startswith("Rechnung Swisscom")
    assert level2["vertrag.docx"]["excerpt"] == "Mietvertrag"


def test_sensitive_pdf_content_never_reaches_the_model(folder):
    """Der Auszug entsteht erst nach dem Datenschutzfilter: sensible Dateien werden nicht einmal geöffnet."""
    from procurator.privacy import split_for_config

    make_pdf(folder / "Steuererklärung.pdf", "Geheim")
    cfg = cfgmod.parse({"ai": {"privacy_level": 2}})
    allowed, withheld = split_for_config(scan(folder), cfg)
    assert not allowed and len(withheld) == 1
    assert "Geheim" not in json.dumps(build_payload(allowed, 2))
