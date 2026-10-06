"""The web application: the chat (section 6, usable on a phone), Microsoft sign-in, and the pages
around it (companies, activity log, templates, status).

One owner, one password (APP_PASSWORD), a signed cookie. Conversation state lives in memory per
cookie, enough for v1 with a single user; the registry and the log are on disk.
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import logging
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel
from urllib.parse import urlparse

from .. import __version__
from ..agent.context import Context, build_context
from ..agent.loop import AgentLoop
from ..agent.models import Session
from ..agent.pipeline import Pipeline
from ..agent.report import question_to_dict, report_to_dict
from ..config import Settings
from ..llm import make_llm
from ..logging_setup import setup_logging
from ..naming import parse_filename
from ..templates import PLACEHOLDER, TemplateError, parse_template

STATIC = Path(__file__).parent / "static"
SESSION_IDLE_SECONDS = 12 * 3600          # signed out after 12 h without activity
SESSION_MAX_SECONDS = 30 * 86400          # and in any case after 30 days
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cache-Control": "no-store",
    "Content-Security-Policy": ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' "
                                "https://fonts.googleapis.com; font-src https://fonts.gstatic.com; img-src 'self' data:; "
                                "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self' "
                                "https://login.microsoftonline.com"),
}
TEMPLATE_FILES = ("preview_fr.txt", "preview_en.txt", "quote_fr.txt", "quote_en.txt",
                  "signature_fr.txt", "signature_en.txt", "signature.txt", "agency.txt")
KNOWN_PLACEHOLDERS = {"company_name", "contact_name", "greeting", "city", "preview_link", "signature", "agency_name"}


class Login(BaseModel):
    password: str


class Chat(BaseModel):
    message: str


class TemplateBody(BaseModel):
    content: str


class DoNotContact(BaseModel):
    name: str
    city: str = ""
    value: bool
    reason: str = "the owner asked"


def _sign(secret: str, value: str) -> str:
    return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()[:32]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def create_app(settings: Settings | None = None, ctx: Context | None = None, demo: bool = False) -> FastAPI:
    s = settings or Settings()
    context = ctx or build_context(s, demo=demo)
    log_ = setup_logging(s.registry_dir)
    log_.info("app start version=%s mode=%s demo=%s files=%s", __version__, s.AGENT_MODE, demo, s.FILE_SOURCE)
    failed_logins: dict[str, list[float]] = {}
    llm = make_llm(s)
    pipeline = Pipeline(context, llm=llm if llm.available else None)
    agent = AgentLoop(context, llm) if (s.AGENT_MODE == "agent" and llm.available) else None
    sessions: dict[str, Session] = {}
    session_times: dict[str, tuple[float, float]] = {}      # sid -> (created, last_seen)
    app = FastAPI(title="Outlook Outreach Draft Agent", version=__version__, docs_url=None, redoc_url=None)
    app.state.ctx, app.state.pipeline, app.state.sessions = context, pipeline, sessions
    app.state.session_times = session_times
    https = s.PUBLIC_URL.startswith("https")

    @app.middleware("http")
    async def harden(request: Request, call_next):
        # Cross-site request forgery: a browser sends Origin / Sec-Fetch-Site on state-changing requests;
        # anything that is not same-origin is refused before it reaches a handler.
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            origin = request.headers.get("origin")
            fetch_site = request.headers.get("sec-fetch-site")
            if origin and urlparse(origin).netloc.lower() != request.headers.get("host", "").lower():
                return JSONResponse({"error": "Cross-site request refused."}, status_code=403)
            if fetch_site and fetch_site not in ("same-origin", "none"):
                return JSONResponse({"error": "Cross-site request refused."}, status_code=403)
        response = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        if https:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    # --- auth -------------------------------------------------------------------------------
    def current_session(request: Request) -> Session:
        cookie = request.cookies.get("ooda_session", "")
        sid, _, sig = cookie.partition(".")
        if s.APP_PASSWORD:
            if not sid or not hmac.compare_digest(sig, _sign(s.SECRET_KEY, sid)):
                raise HTTPException(401, "Sign in first.")
            created, last = session_times.get(sid, (0.0, 0.0))
            now = time.time()
            if sid not in sessions or now - last > SESSION_IDLE_SECONDS or now - created > SESSION_MAX_SECONDS:
                sessions.pop(sid, None)
                session_times.pop(sid, None)
                raise HTTPException(401, "Session expired. Sign in again.")
            session_times[sid] = (created, now)
        else:
            sid = sid or "local"
        return sessions.setdefault(sid, Session())

    @app.post("/api/login")
    def login(body: Login, request: Request, response: Response):
        ip = request.client.host if request.client else "?"
        recent = [t for t in failed_logins.get(ip, []) if time.time() - t < 60]
        if len(recent) >= 5:
            raise HTTPException(429, "Too many attempts. Wait a minute.")
        if s.APP_PASSWORD and not hmac.compare_digest(body.password, s.APP_PASSWORD):
            failed_logins[ip] = recent + [time.time()]
            log_.warning("failed login from %s", ip)
            time.sleep(0.5)
            raise HTTPException(401, "Wrong password.")
        failed_logins.pop(ip, None)
        sid = secrets.token_urlsafe(24)
        response.set_cookie("ooda_session", f"{sid}.{_sign(s.SECRET_KEY, sid)}", httponly=True, samesite="strict",
                            secure=https, max_age=SESSION_MAX_SECONDS, path="/")
        sessions[sid] = Session()
        session_times[sid] = (time.time(), time.time())
        log_.info("login from %s", ip)
        return {"ok": True}

    @app.post("/api/logout")
    def logout(request: Request, response: Response):
        sid = request.cookies.get("ooda_session", "").partition(".")[0]
        sessions.pop(sid, None)
        session_times.pop(sid, None)
        response.delete_cookie("ooda_session", path="/")
        return {"ok": True}

    # --- pages and status ---------------------------------------------------------------------
    @app.get("/", response_class=HTMLResponse)
    def index():
        return (STATIC / "index.html").read_text(encoding="utf-8")

    @app.get("/healthz")
    def healthz():
        g = context.graph
        return {"ok": True, "version": __version__, "outlook": bool(g is not None and g.connected()),
                "templates_ok": all(context.templates.available().values())}

    @app.get("/api/status")
    def status(request: Request):
        try:
            current_session(request)
            signed_in = True
        except HTTPException:
            signed_in = False
        g = context.graph
        connected = bool(g is not None and g.connected())
        videos = [f for f in context.files.list_files(s.VIDEOS_FOLDER) if parse_filename(f.name)]
        quotes = [f for f in context.files.list_files(s.QUOTES_FOLDER) if parse_filename(f.name)]
        actions = context.registry.actions(500)
        today = datetime.now(timezone.utc).date().isoformat()
        return {"version": __version__, "signed_in": signed_in, "needs_password": bool(s.APP_PASSWORD),
                "outlook_connected": connected, "outlook_account": g.account() if connected else "",
                "microsoft_configured": s.microsoft_configured() or demo, "demo": demo,
                "file_source": context.files.source, "agency_root": s.AGENCY_ROOT,
                "videos": len(videos), "quotes": len(quotes), "templates": context.templates.available(),
                "signature": bool(context.templates.signature("fr") or context.templates.signature("en")),
                "llm": llm.available, "model": s.llm_model, "provider": s.LLM_PROVIDER, "mode": "agent" if agent else "pipeline",
                "search": s.SEARCH_PROVIDER if llm.available or s.SEARCH_PROVIDER in ("brave", "serpapi") else "none",
                "places": bool(s.GOOGLE_PLACES_API_KEY), "whatsapp": "validator" if s.WHATSAPP_VALIDATOR_URL else "link",
                "max_attachment_mb": s.MAX_ATTACHMENT_MB, "registry_max_age_days": s.REGISTRY_MAX_AGE_DAYS,
                "companies": len(context.registry.all_companies()),
                "drafts_today": sum(1 for a in actions if a.result == "draft_created" and a.at.startswith(today)),
                "drafts_total": sum(1 for a in actions if a.result == "draft_created"),
                "last_action": actions[0].__dict__ if actions else None}

    # --- chat ---------------------------------------------------------------------------------
    @app.post("/api/chat")
    def chat(body: Chat, session: Session = Depends(current_session)):
        text = body.message.strip()
        if not text:
            raise HTTPException(400, "Write a request first.")
        session.messages.append({"role": "owner", "text": text, "at": _now()})
        log_.info("request: %s", text[:200])
        t0 = time.time()
        try:
            reply = agent.handle(text, session) if agent else pipeline.handle(text, session)
            reports = [report_to_dict(r) for r in session.reports]
            log_.info("done in %.1fs: %s", time.time() - t0, ", ".join(f"{r['company_label']}={r['status']}" for r in reports) or "no report")
        except Exception as exc:
            log_.exception("request failed")
            reply = f"Something failed: {type(exc).__name__}: {exc}. Nothing was created unless a report says so."
            reports = []
        entry = {"role": "agent", "text": reply, "reports": reports, "at": _now(),
                 "pending": [question_to_dict(q) for q in session.pending]}
        session.messages.append(entry)
        session.messages = session.messages[-200:]
        return entry

    @app.get("/api/history")
    def history(session: Session = Depends(current_session)):
        return {"messages": session.messages, "pending": [question_to_dict(q) for q in session.pending]}

    @app.post("/api/history/clear")
    def clear_history(session: Session = Depends(current_session)):
        session.messages.clear()
        session.history.clear()
        return {"ok": True}

    # --- registry, log, templates -------------------------------------------------------------
    @app.get("/api/log")
    def log(session: Session = Depends(current_session), limit: int = 200):
        return {"actions": [a.__dict__ for a in context.registry.actions(limit)]}

    @app.get("/api/registry")
    def registry(session: Session = Depends(current_session)):
        return {"companies": [c.to_dict() for c in context.registry.all_companies()]}

    @app.post("/api/registry/do_not_contact")
    def do_not_contact(body: DoNotContact, session: Session = Depends(current_session)):
        row = context.registry.get(body.name, body.city)
        if not row:
            raise HTTPException(404, "Company not in the registry.")
        row.do_not_contact = body.value
        row.do_not_contact_reason = body.reason if body.value else ""
        context.registry.upsert(row)
        context.registry.log(company=row.name, result="registry_updated",
                             detail=f"do_not_contact={body.value} ({body.reason})" if body.value else "do_not_contact=False")
        return {"ok": True, "company": row.to_dict()}

    @app.post("/api/registry/export")
    def export(session: Session = Depends(current_session)):
        comp, acts = context.registry.export_csv()
        return {"registry_csv": str(comp), "actions_csv": str(acts)}

    @app.get("/api/export/{which}.csv")
    def export_download(which: str, session: Session = Depends(current_session)):
        buf = io.StringIO()
        w = csv.writer(buf)
        if which == "registry":
            rows = [c.to_dict() for c in context.registry.all_companies()]
            cols = list(rows[0].keys()) if rows else ["name"]
            w.writerow(cols)
            for r in rows:
                r["aliases"] = "; ".join(r["aliases"])
                w.writerow([r.get(c, "") for c in cols])
        elif which == "actions":
            w.writerow(["date", "company", "email_type", "recipient", "file", "result", "detail"])
            for a in reversed(context.registry.actions(100000)):
                w.writerow([a.at, a.company, a.email_type, a.recipient, a.file, a.result, a.detail])
        else:
            raise HTTPException(404, "Unknown export.")
        buf.seek(0)
        stamp = datetime.now().strftime("%Y-%m-%d")
        return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                                 headers={"Content-Disposition": f'attachment; filename="{which}-{stamp}.csv"'})

    @app.get("/api/templates")
    def templates(session: Session = Depends(current_session)):
        out = []
        for name in TEMPLATE_FILES:
            p = context.templates.folder / name
            out.append({"name": name, "exists": p.exists(),
                        "content": p.read_text(encoding="utf-8") if p.exists() else ""})
        return {"folder": str(context.templates.folder), "files": out, "placeholders": sorted(KNOWN_PLACEHOLDERS)}

    @app.put("/api/templates/{name}")
    def save_template(name: str, body: TemplateBody, session: Session = Depends(current_session)):
        if name not in TEMPLATE_FILES:
            raise HTTPException(400, "Unknown template file.")
        content = body.content.replace("\r\n", "\n")
        if name.startswith(("preview_", "quote_")):
            try:
                t = parse_template(content, name.split("_")[0], name.split("_")[1][:2])
            except TemplateError as exc:
                raise HTTPException(400, str(exc))
            unknown = sorted(t.placeholders - KNOWN_PLACEHOLDERS)
            if unknown:
                raise HTTPException(400, "Unknown placeholder(s): " + ", ".join("{{%s}}" % u for u in unknown))
        context.templates.folder.mkdir(parents=True, exist_ok=True)
        (context.templates.folder / name).write_text(content, encoding="utf-8")
        context.registry.log(company="-", result="template_saved", detail=name)
        return {"ok": True}

    # --- Microsoft sign-in --------------------------------------------------------------------
    @app.get("/auth/microsoft")
    def auth_start(session: Session = Depends(current_session)):
        g = context.graph
        if g is None or not hasattr(g, "auth"):
            raise HTTPException(400, "Microsoft sign-in is not configured (MS_CLIENT_ID / MS_CLIENT_SECRET).")
        return RedirectResponse(g.auth.authorization_url())

    @app.get("/auth/microsoft/callback")
    def auth_callback(request: Request, code: str = "", state: str = "", error: str = "", error_description: str = ""):
        g = context.graph
        if g is None or not hasattr(g, "auth"):
            raise HTTPException(400, "Microsoft sign-in is not configured.")
        if error:
            return RedirectResponse(f"/?auth_error={error}", status_code=303)
        if not g.auth.check_state(state):
            return RedirectResponse("/?auth_error=state", status_code=303)
        try:
            token = g.complete_sign_in(code)
        except Exception as exc:
            return RedirectResponse(f"/?auth_error={str(exc)[:300]}", status_code=303)
        context.registry.log(company="-", result="outlook_connected", detail=token.account)
        return RedirectResponse("/?connected=1", status_code=303)

    @app.post("/auth/microsoft/disconnect")
    def auth_disconnect(session: Session = Depends(current_session)):
        g = context.graph
        if g is not None and hasattr(g, "store"):
            g.store.clear()
            g._token = None
            context.registry.log(company="-", result="outlook_disconnected")
        return {"ok": True}

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)

    return app


def main() -> None:  # pragma: no cover
    import os
    import uvicorn
    demo = os.getenv("DEMO", "") in ("1", "true", "yes")
    uvicorn.run(create_app(demo=demo), host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8080")),
                server_header=False, proxy_headers=True)


if __name__ == "__main__":  # pragma: no cover
    main()
