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
