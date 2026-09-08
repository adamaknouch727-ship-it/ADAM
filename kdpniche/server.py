"""Zero-dependency web server: JSON API + the single-page UI."""

from __future__ import annotations

import json
import mimetypes
import os
import threading
import traceback
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import export
from .analyzer import NicheFinder
from .config import MARKETPLACES, Settings
from .storage import Storage

WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")

JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


def _settings_from(payload: dict, base: Settings) -> Settings:
    settings = Settings(**{**base.__dict__})
    settings.marketplace = payload.get("marketplace", base.marketplace)
    if settings.marketplace not in MARKETPLACES:
        settings.marketplace = "us"
    settings.store = payload.get("store", base.store)
    settings.deep = bool(payload.get("deep", base.deep))
    settings.offline = bool(payload.get("offline", base.offline))
    settings.request_delay = float(payload.get("delay", base.request_delay))
    settings.workers = max(1, min(8, int(payload.get("workers", base.workers))))
    settings.products_per_keyword = max(
        5, min(50, int(payload.get("products", base.products_per_keyword))))
    return settings


def _run_job(job_id: str, payload: dict, base: Settings, storage: Storage) -> None:
    settings = _settings_from(payload, base)
    finder = NicheFinder(settings)

    def progress(stage: str, done: int, total: int, label: str) -> None:
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            if job is not None:
                job["stage"] = stage
                job["done"] = done
                job["total"] = total
                job["current"] = label

    try:
        run = finder.find_niches(
            payload.get("seed", "").strip(),
            breadth=payload.get("breadth", "normal"),
            limit=max(1, min(120, int(payload.get("limit", 25)))),
            on_progress=progress,
        )
        data = run.to_dict(include_books=True)
        run_id = storage.save_run(run.to_dict(include_books=False))
        data["run_id"] = run_id
        with JOBS_LOCK:
            JOBS[job_id].update(status="done", run=data, done=len(run.niches),
                                total=len(run.niches))
    except Exception as exc:  # surface the failure to the UI instead of hanging
        with JOBS_LOCK:
            JOBS[job_id].update(status="error", error=f"{exc}",
                                trace=traceback.format_exc()[-1200:])


class Handler(BaseHTTPRequestHandler):
    server_version = "KDPNicheFinder/1.0"
    settings: Settings
    storage: Storage

    # ------------------------------------------------------------- plumbing
    def log_message(self, fmt: str, *args) -> None:  # quieter console
        if os.environ.get("KDPNICHE_VERBOSE"):
            super().log_message(fmt, *args)

    def _send(self, code: int, body: bytes, content_type: str = "application/json",
              extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, data, code: int = 200) -> None:
        self._send(code, json.dumps(data, ensure_ascii=False).encode(), "application/json")

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode() or "{}")
        except json.JSONDecodeError:
            return {}

    def _static(self, path: str) -> None:
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        full = os.path.normpath(os.path.join(WEB_DIR, rel))
        if not full.startswith(WEB_DIR) or not os.path.isfile(full):
            self._send(404, b"Not found", "text/plain")
            return
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        with open(full, "rb") as handle:
            self._send(200, handle.read(), ctype)

    # ----------------------------------------------------------------- GET
    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        try:
            if route == "/api/health":
                self._json({"ok": True, "version": "1.0.0",
                            "offline": self.settings.offline,
                            "data_dir": self.settings.data_dir})
            elif route == "/api/markets":
                self._json({
                    "markets": [
                        {"code": m.code, "name": m.name, "domain": m.domain,
                         "currency": m.currency, "symbol": m.symbol}
                        for m in MARKETPLACES.values()
                    ],
                    "stores": [{"code": "print", "name": "Paperback / Print"},
                               {"code": "kindle", "name": "Kindle eBooks"}],
                })
            elif route.startswith("/api/job/"):
                job_id = route.rsplit("/", 1)[-1]
                with JOBS_LOCK:
                    job = JOBS.get(job_id)
                if not job:
                    self._json({"error": "unknown job"}, 404)
                else:
                    self._json({k: v for k, v in job.items() if k != "trace"})
            elif route == "/api/saved":
                self._json({"niches": self.storage.list_niches()})
            elif route == "/api/runs":
                self._json({"runs": self.storage.list_runs()})
            elif route.startswith("/api/runs/"):
                run = self.storage.get_run(route.rsplit("/", 1)[-1])
                self._json(run or {"error": "not found"}, 200 if run else 404)
            elif route == "/api/export":
                self._export(query)
            else:
                self._static(route)
        except Exception as exc:
            self._json({"error": str(exc), "trace": traceback.format_exc()[-800:]}, 500)

    # ---------------------------------------------------------------- POST
    def do_POST(self) -> None:  # noqa: N802
        route = urllib.parse.urlparse(self.path).path
        payload = self._body()
        try:
            if route == "/api/search":
                seed = (payload.get("seed") or "").strip()
                if not seed:
                    self._json({"error": "seed keyword is required"}, 400)
                    return
                job_id = uuid.uuid4().hex[:12]
                with JOBS_LOCK:
                    JOBS[job_id] = {"id": job_id, "status": "running", "stage": "keywords",
                                    "done": 0, "total": 0, "current": seed, "seed": seed}
                threading.Thread(target=_run_job,
                                 args=(job_id, payload, self.settings, self.storage),
                                 daemon=True).start()
                self._json({"job": job_id})
            elif route == "/api/keyword":
                settings = _settings_from(payload, self.settings)
                finder = NicheFinder(settings)
                report = finder.analyse_keyword((payload.get("keyword") or "").strip())
                self._json(report.to_dict(include_books=True))
            elif route == "/api/saved":
                niche = payload.get("niche") or {}
                self._json(self.storage.save_niche(niche, payload.get("note", "")))
            elif route == "/api/saved/delete":
                ok = self.storage.delete_niche(payload.get("keyword", ""),
                                               payload.get("marketplace", "us"),
                                               payload.get("store", "print"))
                self._json({"deleted": ok})
            elif route == "/api/cache/clear":
                NicheFinder(self.settings).cache.clear()
                self._json({"cleared": True})
            else:
                self._json({"error": "unknown endpoint"}, 404)
        except Exception as exc:
            self._json({"error": str(exc), "trace": traceback.format_exc()[-800:]}, 500)

    # -------------------------------------------------------------- export
    def _export(self, query: dict) -> None:
        job_id = (query.get("job") or [""])[0]
        kind = (query.get("kind") or ["niches"])[0]
        fmt = (query.get("format") or ["csv"])[0]
        keyword = (query.get("keyword") or [""])[0]

        if job_id == "saved":
            run = {"seed": "saved", "marketplace": "", "store": "",
                   "niches": self.storage.list_niches()}
        else:
            with JOBS_LOCK:
                job = JOBS.get(job_id)
            if not job or not job.get("run"):
                self._json({"error": "no finished run for that job"}, 404)
                return
            run = job["run"]

        if kind == "books":
            niche = next((n for n in run["niches"] if n["keyword"] == keyword), None)
            if not niche:
                self._json({"error": "keyword not in run"}, 404)
                return
            body = export.books_to_csv(niche.get("books", []))
            name = f"books-{keyword.replace(' ', '-')}.csv"
            ctype = "text/csv"
        elif fmt == "json":
            body, name, ctype = export.run_to_json(run), "niches.json", "application/json"
        elif fmt == "md":
            body, name, ctype = export.run_to_markdown(run), "niches.md", "text/markdown"
        else:
            body = export.niches_to_csv(run["niches"])
            name, ctype = f"niches-{run.get('seed', 'export').replace(' ', '-')}.csv", "text/csv"

        self._send(200, body.encode("utf-8-sig"), ctype,
                   {"Content-Disposition": f'attachment; filename="{name}"'})


def serve(host: str = "127.0.0.1", port: int = 8777, settings: Settings | None = None):
    settings = settings or Settings.from_env()
    os.makedirs(settings.data_dir, exist_ok=True)
    Handler.settings = settings
    Handler.storage = Storage(os.path.join(settings.data_dir, "kdpniche.sqlite"))
    httpd = ThreadingHTTPServer((host, port), Handler)
    return httpd
