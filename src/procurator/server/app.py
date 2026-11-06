"""FastAPI-Server: nur lokal (127.0.0.1). Die UI ruft Plan, Apply, Undo, Presets auf."""

from __future__ import annotations

import threading
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import about as aboutmod
from .. import config as cfgmod
from ..ai.learning import DecisionStore
from ..ai.probe import probe
from ..engine import apply_plan, make_plan
from ..journal import Journal
from ..model import FileItem, Plan, Status
from ..ops.base import Operation
from ..ops.registry import SPECS, ParamError, build
from ..privacy import rules_from_config
from ..scanner import scan

NO_UI_PAGE = """<!doctype html><html lang="de"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Procurator Capsularum</title>
<body style="font-family: system-ui, sans-serif; max-width: 40rem; margin: 3rem auto; padding: 0 1rem">
<h1>Die Oberfläche ist noch nicht gebaut</h1>
<p>Der Server läuft, aber es fehlt die Web-Oberfläche. Einmalig bauen (Node.js 20.19 oder neuer):</p>
<pre>cd web
npm install
npm run build</pre>
<p>Danach diese Seite neu laden. Die Schnittstelle ist unter
<a href="/api/docs">/api/docs</a> erreichbar.</p>
</body></html>"""

DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


class PlanRequest(BaseModel):
    paths: list[str] = Field(min_length=1)
    recursive: bool = False
    operation: str
    params: dict[str, Any] = {}
    force_unique: bool = False
    order: list[str] | None = None  # eigene Reihenfolge (Pfade), z. B. nach Ziehen in der UI
    confirm_cloud: bool = False  # Nutzer hat bestätigt, dass Daten an einen Cloud-Anbieter gehen


class ScanRequest(BaseModel):
    paths: list[str] = Field(min_length=1)
    recursive: bool = False


class ApplyRequest(PlanRequest):
    disabled: list[str] = []  # abgewählte Quellpfade


class ProposalEditRequest(PlanRequest):
    path: str
    target: str


class PresetRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    operation: str
    params: dict[str, Any] = {}


def _items(req: ScanRequest) -> list[FileItem]:
    paths = []
    for raw in req.paths:
        p = Path(raw).expanduser()
        if not p.is_absolute() or not p.exists():
            raise HTTPException(400, f"Pfad existiert nicht: {raw}")
        paths.append(p)
    items = scan(paths, recursive=req.recursive)
    if getattr(req, "order", None):
        rank = {Path(p): i for i, p in enumerate(req.order or [])}
        items.sort(key=lambda i: rank.get(i.path, len(rank)))
    return items


def _build_plan(req: PlanRequest) -> tuple[Operation, Plan]:
    try:
        op = build(req.operation, req.params)
    except ParamError as exc:
        raise HTTPException(422, str(exc)) from exc
    cfg, _warning = cfgmod.load()
    plan = make_plan(op, _items(req), force_unique=req.force_unique,
                     sensitive=rules_from_config(cfg))
    return op, plan


def _plan(req: PlanRequest) -> Plan:
    return _build_plan(req)[1]


def _serialize(plan: Plan) -> dict[str, Any]:
    return {
        "operation": plan.operation,
        "kind": plan.kind,
        "counts": {k.value: v for k, v in plan.counts().items()},
        "sensitiveCount": sum(1 for c in plan.changes if c.sensitive),
        "info": plan.info,
        "needsAnalysis": plan.needs_analysis,
        "changes": [
            {
                "src": str(c.src), "srcName": c.src.name,
                "dst": str(c.dst) if c.dst else None,
                "dstName": c.dst.name if c.dst else None,
                "dstFolder": str(c.dst.parent) if c.dst and c.dst.parent != c.src.parent else None,
                "folder": str(c.src.parent),
                "status": c.status.value, "reason": c.reason, "sensitive": c.sensitive,
                "editable": c.editable,
            }
            for c in plan.changes
        ],
    }


class ConfigRequest(BaseModel):
    ai: dict[str, Any] = {}
    privacy: dict[str, Any] = {}


def _config_response(cfg: cfgmod.Config, warning: str | None = None) -> dict[str, Any]:
    return {
        "config": cfg.to_dict(),
        "warning": warning,
        "isCloud": cfg.is_cloud,
        "requiresConfirmation": cfg.requires_confirmation,
        "apiKeyPresent": cfgmod.api_key_present(cfg),  # nur ja/nein, nie der Wert
        "privacyLevels": {str(k): v for k, v in cfgmod.PRIVACY_LEVELS.items()},
        "defaults": cfgmod.Config().to_dict(),
        "path": str(cfgmod.config_path()),
    }


@dataclass
class Job:
    id: str
    total: int = 0
    done: int = 0
    current: str = ""
    state: str = "running"  # running | finished | cancelled | error
    batch_id: int | None = None
    ok: int = 0
    failed: list[dict[str, str]] = field(default_factory=list)
    skipped: int = 0
    error: str = ""
    cancel: threading.Event = field(default_factory=threading.Event)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "state": self.state, "total": self.total, "done": self.done,
            "current": self.current, "batchId": self.batch_id, "ok": self.ok,
            "failed": self.failed, "skipped": self.skipped, "error": self.error,
        }


def create_app(journal: Journal | None = None, static_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title="Procurator Capsularum", docs_url="/api/docs", openapi_url="/api/openapi.json")
    # Gegen DNS-Rebinding: nur lokale Host-Header; gegen fremde Webseiten: CORS nur für Vite-Dev.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"])
    app.add_middleware(CORSMiddleware, allow_origins=DEV_ORIGINS, allow_methods=["*"],
                       allow_headers=["Content-Type"])
    db = journal or Journal()
    jobs: dict[str, Job] = {}
    jobs_lock = threading.Lock()

    @app.get("/api/operations")
    def operations() -> list[dict[str, Any]]:
        return [s.to_dict() for s in SPECS]

    @app.get("/api/browse")
    def browse(path: str = "") -> dict[str, Any]:
        p = Path(path).expanduser() if path else Path.home()
        if not p.is_absolute() or not p.is_dir():
            raise HTTPException(400, "Kein Ordner")
        try:
            entries = sorted(p.iterdir(), key=lambda e: e.name.casefold())
        except PermissionError as exc:
            raise HTTPException(403, "Keine Leserechte") from exc
        dirs = [e.name for e in entries if not e.name.startswith(".") and e.is_dir()]
        files = sum(1 for e in entries if e.is_file() and not e.name.startswith("."))
        return {
            "path": str(p),
            "parent": str(p.parent) if p.parent != p else None,
            "home": str(Path.home()),
            "dirs": dirs,
            "fileCount": files,
        }

    @app.post("/api/scan")
    def scan_files(req: ScanRequest) -> list[dict[str, str]]:
        """Dateiliste ohne Aktion, damit die UI den Ordnerinhalt sofort zeigt."""
        cfg, _warning = cfgmod.load()
        rules = rules_from_config(cfg)
        return [{"src": str(i.path), "srcName": i.name, "folder": str(i.path.parent),
                 "sensitive": rules.match(i)} for i in _items(req)]

    @app.post("/api/plan")
    def plan(req: PlanRequest) -> dict[str, Any]:
        return _serialize(_plan(req))

    @app.post("/api/apply")
    def apply(req: ApplyRequest) -> dict[str, Any]:
        """Startet einen Hintergrund-Job. Der Fortschritt kommt über /api/jobs/{id}."""
        op, plan_ = _build_plan(req)  # neu berechnen: dem Client-Zustand wird nicht vertraut
        disabled = {Path(p) for p in req.disabled}
        for c in plan_.changes:
            c.enabled = c.src not in disabled
        with jobs_lock:
            if any(j.state == "running" for j in jobs.values()):
                raise HTTPException(409, "Es läuft bereits ein Auftrag")
            job = Job(id=uuid.uuid4().hex, total=sum(1 for c in plan_.changes if c.will_run))
            job.skipped = sum(1 for c in plan_.changes if not c.will_run)
            jobs[job.id] = job

        def progress(done: int, total: int, current: str) -> None:
            job.done, job.total, job.current = done, total, current

        def run() -> None:
            try:
                result = apply_plan(plan_, db, progress, job.cancel)
                try:  # Lernen darf das Anwenden nie stören
                    rejected = [c for c in plan_.changes
                                if c.status == Status.OK and not c.enabled and c.dst is not None]
                    op.record_decisions(result.done, rejected)
                except Exception:
                    pass
                job.ok = len(result.done)
                job.batch_id = result.batch_id
                job.failed = [{"src": c.src.name, "error": msg} for c, msg in result.failed]
                job.state = "cancelled" if result.cancelled else "finished"
            except Exception as exc:
                job.error, job.state = str(exc), "error"

        threading.Thread(target=run, daemon=True).start()
        return job.to_dict()

    @app.post("/api/analyze")
    def analyze(req: PlanRequest) -> dict[str, Any]:
        """Langsamer Vorbereitungsschritt einer Aktion (zum Beispiel Dateien für die Dublettensuche
        lesen) als Hintergrund-Job. Es wird nichts verändert, nur der lokale Index aktualisiert."""
        try:
            op = build(req.operation, req.params)
        except ParamError as exc:
            raise HTTPException(422, str(exc)) from exc
        if not op.needs_analysis:
            raise HTTPException(400, "Diese Aktion braucht keine Analyse")
        cfg, _warning = cfgmod.load()
        if op.sends_data and cfg.requires_confirmation and not req.confirm_cloud:
            raise HTTPException(409, "Für einen Cloud-Anbieter fehlt die Bestätigung vor dem Senden")
        items = _items(req)
        with jobs_lock:
            if any(j.state == "running" for j in jobs.values()):
                raise HTTPException(409, "Es läuft bereits ein Auftrag")
            job = Job(id=uuid.uuid4().hex, total=len(items))
            jobs[job.id] = job

        def progress(done: int, total: int, current: str) -> None:
            job.done, job.total, job.current = done, total, current

        def run() -> None:
            try:
                op.analyze(items, progress, job.cancel, confirmed=req.confirm_cloud)
                job.state = "cancelled" if job.cancel.is_set() else "finished"
            except Exception as exc:
                job.error, job.state = str(exc), "error"

        threading.Thread(target=run, daemon=True).start()
        return job.to_dict()

    @app.post("/api/analyze/preview")
    def analyze_preview(req: PlanRequest) -> dict[str, Any]:
        """Was würde die Analyse senden? Ohne Aufruf eines Modells und ohne Schreiben."""
        try:
            op = build(req.operation, req.params)
        except ParamError as exc:
            raise HTTPException(422, str(exc)) from exc
        info = op.send_preview(_items(req)) if op.sends_data else None
        return {"needed": info is not None, **(info or {})}

    @app.post("/api/proposals/edit")
    def edit_proposal(req: ProposalEditRequest) -> dict[str, bool]:
        """Ein Ziel in der Vorschau von Hand ändern. Gleiche Sicherheitsprüfung wie beim Modell."""
        try:
            op = build(req.operation, req.params)
        except ParamError as exc:
            raise HTTPException(422, str(exc)) from exc
        path = Path(req.path)
        if not path.is_absolute() or not path.is_file():
            raise HTTPException(400, f"Datei existiert nicht: {req.path}")
        try:
            op.edit_target(path, req.target)
        except NotImplementedError as exc:
            raise HTTPException(400, "Diese Aktion kennt keine manuellen Ziele") from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"ok": True}

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str) -> dict[str, Any]:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "Auftrag unbekannt")
        return job.to_dict()

    @app.post("/api/jobs/{job_id}/cancel")
    def job_cancel(job_id: str) -> dict[str, bool]:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "Auftrag unbekannt")
        job.cancel.set()
        return {"ok": True}

    @app.get("/api/about")
    def about_info() -> dict[str, Any]:
        """Version, Autorin, Lizenz und die Lizenzen der verwendeten Bausteine."""
        return aboutmod.about()

    @app.get("/api/learning")
    def learning_info() -> dict[str, Any]:
        """Was aus deinen Entscheidungen gemerkt wurde. Liegt nur auf diesem Rechner."""
        store = DecisionStore()
        return {"stats": store.stats(),
                "recent": [asdict(d) for d in store.recent(30)]}

    @app.delete("/api/learning")
    def learning_clear() -> dict[str, int]:
        return {"deleted": DecisionStore().clear()}

    @app.get("/api/config")
    def get_config() -> dict[str, Any]:
        cfg, warning = cfgmod.load()
        return _config_response(cfg, warning)

    @app.put("/api/config")
    def put_config(req: ConfigRequest) -> dict[str, Any]:
        try:
            cfg = cfgmod.parse(req.model_dump())
        except (cfgmod.ConfigError, TypeError) as exc:
            raise HTTPException(422, str(exc)) from exc
        cfgmod.save(cfg)
        return _config_response(cfg)

    @app.post("/api/config/test")
    def test_config(req: ConfigRequest | None = None) -> dict[str, Any]:
        """Verbindung testen, mit den Werten aus dem Formular (noch ungespeichert) oder den gespeicherten."""
        try:
            cfg = cfgmod.parse(req.model_dump()) if req else cfgmod.load()[0]
        except (cfgmod.ConfigError, TypeError) as exc:
            raise HTTPException(422, str(exc)) from exc
        return probe(cfg)

    @app.get("/api/history")
    def history(limit: int = 30) -> list[dict[str, Any]]:
        return [
            {"id": b.id, "ts": b.ts, "operation": b.operation, "count": b.count,
             "undone": b.undone, "kind": b.kind}
            for b in db.batches(limit)
        ]

    @app.get("/api/history/{batch_id}")
    def history_detail(batch_id: int) -> list[dict[str, str]]:
        return [{"src": s.name, "dst": d.name, "folder": str(d.parent)} for s, d in db.moves(batch_id)]

    @app.post("/api/undo/{batch_id}")
    def undo(batch_id: int) -> dict[str, Any]:
        count, errors = db.undo(batch_id)
        return {"restored": count, "errors": errors}

    @app.get("/api/presets")
    def presets() -> list[dict[str, Any]]:
        return db.presets()

    @app.post("/api/presets")
    def save_preset(req: PresetRequest) -> dict[str, bool]:
        db.save_preset(req.name.strip(), req.operation, req.params)
        return {"ok": True}

    @app.delete("/api/presets/{name}")
    def delete_preset(name: str) -> dict[str, bool]:
        db.delete_preset(name)
        return {"ok": True}

    if static_dir and static_dir.is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="web")
    else:

        @app.get("/", response_class=HTMLResponse)
        def ui_missing() -> str:
            return NO_UI_PAGE

    return app
