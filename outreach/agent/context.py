"""Everything a request needs, built once from settings. Tests build it from fakes."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..config import Settings
from ..files.base import FileStore
from ..registry import Registry
from ..research.identify import Researcher
from ..templates import TemplateStore


@dataclass
class Context:
    settings: Settings
    registry: Registry
    files: FileStore
    templates: TemplateStore
    researcher: Researcher
    graph: object | None = None            # GraphClient, or a fake in demo/tests
    agency_name: str = ""
    # Recipients the owner typed in the chat this session: the phase-1 path (details entered by
    # hand) and the only way an address that research did not find can become a recipient.
    owner_supplied_recipients: set[str] = field(default_factory=set)


def build_context(settings: Settings | None = None, *, demo: bool = False) -> Context:
    from ..llm import make_llm
    from ..outlook.auth import MicrosoftAuth, TokenStore
    from ..outlook.graph import GraphClient
    from ..research.crawler import Fetcher
    from ..research.search import GooglePlaces, make_search_provider
    from ..files.local import LocalFileStore
    from ..files.onedrive import OneDriveFileStore

    s = settings or Settings()
    s.check_production()
    registry = Registry(s.registry_dir / "registry.sqlite")
    llm = make_llm(s)
    researcher = Researcher(llm=llm if llm.available else None, search=make_search_provider(s),
                            places=GooglePlaces(s.GOOGLE_PLACES_API_KEY) if s.GOOGLE_PLACES_API_KEY else None,
                            fetcher=Fetcher(timeout=s.FETCH_TIMEOUT), default_country=s.DEFAULT_COUNTRY,
                            dns_check=not demo)
    graph = None
    if demo:
        from .demo import FakeGraph
        graph = FakeGraph(s.registry_dir / "demo_drafts.json")
    elif s.microsoft_configured():
        auth = MicrosoftAuth(s.MS_CLIENT_ID, s.MS_CLIENT_SECRET, s.redirect_uri(), s.MS_TENANT, app_secret=s.SECRET_KEY)
        graph = GraphClient(auth, TokenStore(s.registry_dir / "microsoft_token.enc", s.SECRET_KEY))
    if s.FILE_SOURCE == "onedrive" and graph is not None and not demo:
        files: FileStore = OneDriveFileStore(graph, s.AGENCY_ROOT)
    else:
        files = LocalFileStore(Path(s.AGENCY_ROOT), graph=None if demo else graph, onedrive_root=s.ONEDRIVE_PATH)
    agency_name = ""
    about = s.templates_dir / "agency.txt"
    if about.exists():
        agency_name = about.read_text(encoding="utf-8").strip().splitlines()[0] if about.read_text(encoding="utf-8").strip() else ""
    return Context(settings=s, registry=registry, files=files, templates=TemplateStore(s.templates_dir, s.languages),
                   researcher=researcher, graph=graph, agency_name=agency_name)
