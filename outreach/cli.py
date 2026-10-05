"""Command line: run a request, see the status, prepare the demo, export the registry, verify the
agent cannot send.

    python -m outreach.cli "Preview email for Boulangerie Martin, Lyon"
    python -m outreach.cli status
    python -m outreach.cli demo            # builds ./Agency with sample files and runs offline
    python -m outreach.cli export          # registry.csv + actions.csv in the Registry folder
    python -m outreach.cli verify-cannot-send
    python -m outreach.cli serve           # the web chat on http://localhost:8080
"""
from __future__ import annotations

import os
import sys

from .config import Settings


def _ctx(demo: bool):
    from .agent.context import build_context
    return build_context(Settings(), demo=demo)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    demo = os.getenv("DEMO", "") in ("1", "true", "yes")
    if args and args[0] == "--demo":
        demo, args = True, args[1:]
    if not args:
        print(__doc__)
        return 1
    cmd = args[0]
    if cmd == "demo":
        from .demo_data import build_demo
        root = build_demo(Settings().agency_root)
        print(f"Demo agency written to {root}. Now run:\n  DEMO=1 python -m outreach.cli "
              f"\"Preview email for Boulangerie Martin, Lyon\"\n  DEMO=1 python -m outreach.cli serve")
        return 0
    if cmd == "serve":
        from .web.app import create_app
        import uvicorn
        uvicorn.run(create_app(demo=demo), host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "8080")))
        return 0
    ctx = _ctx(demo)
    from .agent.models import Session
    from .agent.pipeline import Pipeline
    from .llm import make_llm
    llm = make_llm(ctx.settings)
    pipeline = Pipeline(ctx, llm=llm if llm.available else None)
    if cmd == "status":
        print(pipeline.status_text())
        return 0
    if cmd == "export":
        comp, acts = ctx.registry.export_csv()
        print(f"Written {comp} and {acts}")
        return 0
    if cmd == "verify-cannot-send":
        if ctx.graph is None:
            print("Outlook is not configured.")
            return 2
        ok, detail = ctx.graph.probe_cannot_send()
        print(("PASS: " if ok else "FAIL: ") + detail)
        return 0 if ok else 3
    # Anything else is a chat message; a pending question can be answered with a second argument.
    session = Session()
    print(pipeline.handle(" ".join(args), session))
    while session.pending:
        try:
            answer = input("> ")
        except EOFError:
            break
        print(pipeline.handle(answer, session))
    return 0


if __name__ == "__main__":
    sys.exit(main())
