import time

import pytest
from fastapi.testclient import TestClient

from procurator.journal import Journal
from procurator.server import create_app


@pytest.fixture
def client(journal: Journal) -> TestClient:
    return TestClient(create_app(journal))


def run_apply(client, payload) -> dict:
    """Auftrag starten und auf das Ende warten."""
    r = client.post("/api/apply", json=payload)
    assert r.status_code == 200, r.text
    job_id = r.json()["id"]
    for _ in range(200):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["state"] != "running":
            return job
        time.sleep(0.05)
    raise AssertionError("Auftrag endet nicht")


def body(folder, **kw):
    return {"paths": [str(folder)], "operation": "replace",
            "params": {"find": " ", "replace": "_"}, **kw}


def test_operations_schema(client):
    ops = client.get("/api/operations").json()
    assert {o["name"] for o in ops} >= {"replace", "regex", "sequence", "date"}
    assert all("fields" in o for o in ops)


def test_plan_apply_undo(client, make, folder):
    make("a b.txt", "c d.txt")
    r = client.post("/api/plan", json=body(folder))
    assert r.status_code == 200
    data = r.json()
    assert data["counts"]["ok"] == 2
    assert (folder / "a b.txt").exists()  # Vorschau ändert nichts

    job = run_apply(client, body(folder, disabled=[str(folder / "c d.txt")]))
    assert job["state"] == "finished" and job["ok"] == 1
    assert (folder / "a_b.txt").exists() and (folder / "c d.txt").exists()

    batch = job["batchId"]
    assert client.get("/api/history").json()[0]["id"] == batch
    assert client.get(f"/api/history/{batch}").json()[0]["dst"] == "a_b.txt"
    assert client.post(f"/api/undo/{batch}").json() == {"restored": 1, "errors": []}
    assert (folder / "a b.txt").exists()


def test_custom_order_for_sequence(client, make, folder):
    make("a.txt", "b.txt")
    req = {"paths": [str(folder)], "operation": "sequence",
           "params": {"sort": "custom", "position": "replace", "label": "n"},
           "order": [str(folder / "b.txt"), str(folder / "a.txt")]}
    names = {c["srcName"]: c["dstName"] for c in client.post("/api/plan", json=req).json()["changes"]}
    assert names == {"b.txt": "n-001.txt", "a.txt": "n-002.txt"}


def test_validation_errors(client, folder, tmp_path):
    assert client.post("/api/plan", json={**body(folder), "operation": "nope"}).status_code == 422
    assert client.post("/api/plan", json={**body(folder), "params": {"find": ""}}).status_code == 422
    missing = {**body(folder), "paths": [str(tmp_path / "gibt-es-nicht")]}
    assert client.post("/api/plan", json=missing).status_code == 400
    rel = {**body(folder), "paths": ["relativ"]}
    assert client.post("/api/plan", json=rel).status_code == 400


def test_apply_recomputes_plan_server_side(client, make, folder):
    """Der Client schickt nie fertige Zielnamen, nur Parameter."""
    make("a b.txt")
    job = run_apply(client, {**body(folder), "disabled": []})
    assert job["ok"] == 1


def test_foreign_host_header_rejected(journal):
    c = TestClient(create_app(journal), base_url="http://evil.example")
    assert c.get("/api/operations").status_code == 400


def test_foreign_origin_gets_no_cors(client):
    r = client.get("/api/operations", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in r.headers


def test_presets(client):
    client.post("/api/presets", json={"name": "Leerzeichen", "operation": "replace",
                                      "params": {"find": " ", "replace": "_"}})
    assert client.get("/api/presets").json()[0]["name"] == "Leerzeichen"
    client.delete("/api/presets/Leerzeichen")
    assert client.get("/api/presets").json() == []


def test_browse(client, folder, make):
    make("x.txt")
    (folder / "sub").mkdir()
    d = client.get("/api/browse", params={"path": str(folder)}).json()
    assert d["dirs"] == ["sub"] and d["fileCount"] == 1
    assert client.get("/api/browse", params={"path": str(folder / "x.txt")}).status_code == 400


def test_scan_lists_files_without_operation(client, make, folder):
    make("b.txt", "a.txt")
    r = client.post("/api/scan", json={"paths": [str(folder)]})
    assert [f["srcName"] for f in r.json()] == ["a.txt", "b.txt"]
    assert client.post("/api/scan", json={"paths": ["relativ"]}).status_code == 400


def test_move_over_api_shows_target_folder_and_undoes(client, make, folder, tmp_path):
    make("a.txt")
    out = tmp_path / "ziel"
    req = {"paths": [str(folder)], "operation": "move", "params": {"target_dir": str(out)}}
    change = client.post("/api/plan", json=req).json()["changes"][0]
    assert change["dstFolder"] == str(out) and change["status"] == "ok"
    job = run_apply(client, {**req, "disabled": []})
    assert job["ok"] == 1 and (out / "a.txt").exists()
    client.post(f"/api/undo/{job['batchId']}")
    assert (folder / "a.txt").exists() and not out.exists()


def test_move_requires_target(client, folder):
    req = {"paths": [str(folder)], "operation": "move", "params": {"target_dir": ""}}
    assert client.post("/api/plan", json=req).status_code == 422


def test_root_explains_how_to_build_the_ui_when_it_is_missing(journal, tmp_path):
    c = TestClient(create_app(journal, static_dir=tmp_path / "gibt-es-nicht"))
    r = c.get("/")
    assert r.status_code == 200 and "npm run build" in r.text
    assert c.get("/api/operations").status_code == 200  # die Schnittstelle läuft trotzdem


def test_root_serves_the_ui_when_it_exists(journal, tmp_path):
    (tmp_path / "index.html").write_text("<h1>UI</h1>")
    c = TestClient(create_app(journal, static_dir=tmp_path))
    assert "<h1>UI</h1>" in c.get("/").text


def wait_job(client, job_id: str) -> dict:
    for _ in range(200):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["state"] != "running":
            return job
        time.sleep(0.05)
    raise AssertionError("Auftrag endet nicht")


def test_duplicates_flow_plan_analyze_plan_apply_undo(client, folder):
    for name, mt in (("a/x.bin", 1000), ("b/x.bin", 2000)):
        p = folder / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"gleich" * 100)
        import os

        os.utime(p, ns=(mt * 10**9, mt * 10**9))
    (folder / "c.bin").write_bytes(b"anders")
    req = {"paths": [str(folder)], "recursive": True, "operation": "duplicates", "params": {}}

    plan = client.post("/api/plan", json=req).json()  # noch nicht analysiert
    assert plan["needsAnalysis"] is True and plan["info"]["pendingFiles"] == 2
    assert plan["counts"]["ok"] == 0

    job = wait_job(client, client.post("/api/analyze", json=req).json()["id"])
    assert job["state"] == "finished"

    plan = client.post("/api/plan", json=req).json()
    assert plan["info"] == {"groups": 1, "duplicates": 1, "bytes": 600, "pendingFiles": 0,
                            "pendingBytes": 0, "keep": "oldest"}
    ok = [c for c in plan["changes"] if c["status"] == "ok"]
    assert len(ok) == 1 and ok[0]["reason"] == "Dublette von a/x.bin"

    job = run_apply(client, {**req, "disabled": []})
    assert job["ok"] == 1 and (folder / "_Dubletten" / "b" / "x.bin").exists()
    client.post(f"/api/undo/{job['batchId']}")
    assert (folder / "b" / "x.bin").exists() and not (folder / "_Dubletten").exists()


def test_analyze_rejected_for_operations_without_analysis(client, folder):
    req = {"paths": [str(folder)], "operation": "replace", "params": {"find": "a"}}
    assert client.post("/api/analyze", json=req).status_code == 400
    assert client.post("/api/analyze", json={**req, "operation": "nope"}).status_code == 422


def test_analysis_can_be_cancelled_and_resumed(client, folder):
    for i in range(3):
        (folder / f"d{i}.bin").write_bytes(b"x" * 1000)
    req = {"paths": [str(folder)], "operation": "duplicates", "params": {}}
    job_id = client.post("/api/analyze", json=req).json()["id"]
    client.post(f"/api/jobs/{job_id}/cancel")
    assert wait_job(client, job_id)["state"] in ("cancelled", "finished")
    job = wait_job(client, client.post("/api/analyze", json=req).json()["id"])  # danach geht es weiter
    assert job["state"] == "finished"


def make_image(path, size=(400, 200), mode="RGB", color=(200, 30, 30), fmt=None):
    from PIL import Image

    Image.new(mode, size, color).save(path, fmt)
    return path


def test_thumb_returns_small_jpeg(client, folder):
    import io

    from PIL import Image

    img = make_image(folder / "foto.png", (400, 200))
    r = client.get("/api/thumb", params={"path": str(img), "size": 100})
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    with Image.open(io.BytesIO(r.content)) as out:
        assert out.format == "JPEG" and max(out.size) == 100 and out.size == (100, 50)


def test_thumb_etag_gives_304(client, folder):
    img = make_image(folder / "foto.png")
    first = client.get("/api/thumb", params={"path": str(img)})
    again = client.get("/api/thumb", params={"path": str(img)}, headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304


def test_thumb_transparency_goes_to_white(client, folder):
    import io

    from PIL import Image

    img = make_image(folder / "klar.png", (50, 50), "RGBA", (0, 0, 0, 0))
    r = client.get("/api/thumb", params={"path": str(img), "size": 50})
    with Image.open(io.BytesIO(r.content)) as out:
        assert out.getpixel((25, 25))[0] > 240


def test_thumb_size_is_clamped(client, folder):
    import io

    from PIL import Image

    img = make_image(folder / "foto.png", (3000, 3000))
    r = client.get("/api/thumb", params={"path": str(img), "size": 99999})
    with Image.open(io.BytesIO(r.content)) as out:
        assert max(out.size) == 1600


def test_thumb_refuses_non_images_relative_paths_and_missing(client, folder):
    (folder / "text.txt").write_text("hallo")
    assert client.get("/api/thumb", params={"path": str(folder / "text.txt")}).status_code == 404
    assert client.get("/api/thumb", params={"path": "foto.png"}).status_code == 404
    assert client.get("/api/thumb", params={"path": str(folder / "weg.png")}).status_code == 404


def test_thumb_of_a_fake_image_is_415(client, folder):
    fake = folder / "kaputt.jpg"
    fake.write_text("kein Bild")
    assert client.get("/api/thumb", params={"path": str(fake)}).status_code == 415


def test_thumb_refuses_sensitive_files(client, folder):
    img = make_image(folder / "Pass Scan.png")
    assert client.get("/api/thumb", params={"path": str(img)}).status_code == 403


def test_thumb_refuses_cross_site_requests(client, folder):
    img = make_image(folder / "foto.png")
    r = client.get("/api/thumb", params={"path": str(img)}, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    ok = client.get("/api/thumb", params={"path": str(img)}, headers={"Sec-Fetch-Site": "same-origin"})
    assert ok.status_code == 200


def test_thumb_respects_exif_orientation(client, folder):
    import io

    from PIL import Image

    img = Image.new("RGB", (200, 100), "blue")
    exif = Image.Exif()
    exif[0x0112] = 6  # um 90 Grad gedreht gespeichert
    path = folder / "hoch.jpg"
    img.save(path, exif=exif)
    r = client.get("/api/thumb", params={"path": str(path), "size": 100})
    with Image.open(io.BytesIO(r.content)) as out:
        assert out.size[1] > out.size[0]


def test_reveal_runs_the_file_manager_command(client, folder, monkeypatch):
    from procurator import reveal as revealmod

    seen = []
    monkeypatch.setattr(revealmod.subprocess, "Popen", lambda cmd, **kw: seen.append(cmd))
    (folder / "datei.txt").write_text("x")
    r = client.post("/api/reveal", json={"path": str(folder / "datei.txt")})
    assert r.status_code == 200 and seen
    assert str(folder) in " ".join(seen[0])  # macOS/Windows zeigen die Datei, Linux (xdg-open) ihren Ordner


def test_reveal_refuses_relative_missing_and_cross_site(client, folder, monkeypatch):
    from procurator import reveal as revealmod

    seen = []
    monkeypatch.setattr(revealmod.subprocess, "Popen", lambda cmd, **kw: seen.append(cmd))
    assert client.post("/api/reveal", json={"path": "datei.txt"}).status_code == 400
    assert client.post("/api/reveal", json={"path": str(folder / "weg" / "x.txt")}).status_code == 404
    (folder / "datei.txt").write_text("x")
    r = client.post("/api/reveal", json={"path": str(folder / "datei.txt")},
                    headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403 and not seen


def test_reveal_opens_the_folder_when_the_file_is_gone(folder):
    from procurator import reveal as revealmod

    gone = folder / "weg.txt"
    assert revealmod.command_for(gone, "darwin") == ["open", str(folder)]
    (folder / "da.txt").write_text("x")
    assert revealmod.command_for(folder / "da.txt", "darwin") == ["open", "-R", str(folder / "da.txt")]
    assert revealmod.command_for(folder / "da.txt", "win32")[0] == "explorer"
    assert revealmod.command_for(folder / "da.txt", "linux") == ["xdg-open", str(folder)]


def test_prefs_default_save_and_survive_a_settings_save(client):
    assert client.get("/api/prefs").json() == {"language": "auto", "theme": "auto", "thumbs": True}
    r = client.put("/api/prefs", json={"theme": "dark", "language": "en"})
    assert r.json() == {"language": "en", "theme": "dark", "thumbs": True}
    cfg = client.get("/api/config").json()
    client.put("/api/config", json={"ai": cfg["config"]["ai"], "privacy": cfg["config"]["privacy"]})
    assert client.get("/api/prefs").json()["theme"] == "dark"  # Einstellungen speichern lässt die Darstellung


def test_prefs_reject_unknown_values(client):
    assert client.put("/api/prefs", json={"theme": "pink"}).status_code == 422
    assert client.put("/api/prefs", json={"language": "fr"}).status_code == 422
    assert client.get("/api/prefs").json()["theme"] == "auto"
