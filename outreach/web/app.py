"""The chat (section 6: a simple web chat, usable on a phone, no install) plus Microsoft sign-in.

One owner, one password (APP_PASSWORD), a signed cookie. Conversation state (pending questions)
lives in memory per cookie — enough for v1 with a single user.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

from ..config import Settings
from .. import __version__
from ..llm import LLM
from ..agent.context import Context, build_context
from ..agent.loop import AgentLoop
from ..agent.models import Session
from ..agent.pipeline import Pipeline

STATIC = Path(__file__).parent / "static"


class Login(BaseModel):
    password: str


class Chat(BaseModel):
    message: str


def _sign(secret: str, value: str) -> str:
    return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()[:32]


def create_app(settings: Settings | None = None, ctx: Context | None = None, demo: bool = False) -> FastAPI:
    s = settings or Settings()
    context = ctx or build_context(s, demo=demo)
    llm = LLM(api_key=s.ANTHROPIC_API_KEY, model=s.LLM_MODEL)
    pipeline = Pipeline(context, llm=llm if llm.available else None)
    agent = AgentLoop(context, llm) if (s.AGENT_MODE == "agent" and llm.available) else None
    sessions: dict[str, Session] = {}
    app = FastAPI(title="Outlook Outreach Draft Agent", version=__version__, docs_url=None, redoc_url=None)
    app.state.ctx, app.state.pipeline, app.state.sessions = context, pipeline, sessions

    # --- auth ----------------------------------------------------------------------------
    def current_session(request: Request) -> Session:
        if s.APP_PASSWORD:
            cookie = request.cookies.get("ooda_session", "")
            sid, _, sig = cookie.partition(".")
            if not sid or not hmac.compare_digest(sig, _sign(s.SECRET_KEY, sid)):
                raise HTTPException(401, "Sign in first.")
        else:
            sid = request.cookies.get("ooda_session", "").partition(".")[0] or "local"
        return sessions.setdefault(sid, Session())

    @app.post("/api/login")
    def login(body: Login, response: Response):
        if s.APP_PASSWORD and not hmac.compare_digest(body.password, s.APP_PASSWORD):
            time.sleep(0.5)
            raise HTTPException(401, "Wrong password.")
        sid = secrets.token_urlsafe(16)
        response.set_cookie("ooda_session", f"{sid}.{_sign(s.SECRET_KEY, sid)}", httponly=True, samesite="lax",
                            secure=s.PUBLIC_URL.startswith("https"), max_age=30 * 86400)
        sessions[sid] = Session()
        return {"ok": True}

    @app.post("/api/logout")
    def logout(response: Response):
        response.delete_cookie("ooda_session")
        return {"ok": True}

    # --- pages ------------------------------------------------------------------------------
    @app.get("/", response_class=HTMLResponse)
    def index():
        return (STATIC / "index.html").read_text(encoding="utf-8")

    @app.get("/api/status")
    def status(request: Request):
        try:
            current_session(request)
            signed_in = True
        except HTTPException:
            signed_in = False
        g = context.graph
        return {"version": __version__, "signed_in": signed_in, "needs_password": bool(s.APP_PASSWORD),
                "outlook_connected": bool(g is not None and g.connected()), "outlook_account": g.account() if g is not None and g.connected() else "",
                "microsoft_configured": s.microsoft_configured() or demo, "demo": demo,
                "file_source": context.files.source, "agency_root": s.AGENCY_ROOT,
                "templates": context.templates.available(), "llm": llm.available, "model": s.LLM_MODEL,
                "mode": "agent" if agent else "pipeline"}

    @app.post("/api/chat")
    def chat(body: Chat, session: Session = Depends(current_session)):
        text = body.message.strip()
        if not text:
            return {"reply": "Write a request, for example: Preview email for Boulangerie Martin, Lyon"}
        try:
            reply = agent.handle(text, session) if agent else pipeline.handle(text, session)
        except Exception as exc:
            reply = f"Something failed: {type(exc).__name__}: {exc}. Nothing was created unless the report above says so."
        return {"reply": reply, "pending": [q.text for q in session.pending]}

    @app.get("/api/log")
    def log(session: Session = Depends(current_session), limit: int = 100):
        return {"actions": [a.__dict__ for a in context.registry.actions(limit)]}

    @app.get("/api/registry")
    def registry(session: Session = Depends(current_session)):
        return {"companies": [c.to_dict() for c in context.registry.all_companies()]}

    @app.post("/api/registry/export")
    def export(session: Session = Depends(current_session)):
        comp, acts = context.registry.export_csv()
        return {"registry_csv": str(comp), "actions_csv": str(acts)}

    # --- Microsoft sign-in -------------------------------------------------------------------
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
            return HTMLResponse(f"<p>Microsoft refused: {error}: {error_description}</p><a href='/'>Back</a>", 400)
        if not g.auth.check_state(state):
            return HTMLResponse("<p>Sign-in link expired or invalid. Start again.</p><a href='/'>Back</a>", 400)
        try:
            token = g.complete_sign_in(code)
        except Exception as exc:
            return HTMLResponse(f"<p>{exc}</p><a href='/'>Back</a>", 400)
        context.registry.log(company="-", result="outlook_connected", detail=token.account)
        return RedirectResponse("/?connected=1", status_code=303)

    @app.post("/auth/microsoft/disconnect")
    def auth_disconnect(session: Session = Depends(current_session)):
        g = context.graph
        if g is not None and hasattr(g, "store"):
            g.store.clear()
            g._token = None
        return {"ok": True}

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)

    return app


def main() -> None:  # pragma: no cover
    import os
    import uvicorn
    demo = os.getenv("DEMO", "") in ("1", "true", "yes")
    uvicorn.run(create_app(demo=demo), host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "8080")))


if __name__ == "__main__":  # pragma: no cover
    main()
