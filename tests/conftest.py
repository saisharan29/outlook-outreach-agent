import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from outreach.agent.context import Context                      # noqa: E402
from outreach.agent.demo import FakeGraph                        # noqa: E402
from outreach.config import Settings                             # noqa: E402
from outreach.demo_data import build_demo                        # noqa: E402
from outreach.files.local import LocalFileStore                  # noqa: E402
from outreach.registry import Registry                           # noqa: E402
from outreach.research.identify import Researcher                # noqa: E402
from outreach.templates import TemplateStore                     # noqa: E402


@pytest.fixture
def agency(tmp_path):
    return build_demo(tmp_path / "Agency")


@pytest.fixture
def ctx(agency, monkeypatch):
    monkeypatch.setenv("AGENCY_ROOT", str(agency))
    s = Settings()
    registry = Registry(agency / "Registry" / "registry.sqlite")
    researcher = Researcher(dns_check=False)
    c = Context(settings=s, registry=registry, files=LocalFileStore(agency), templates=TemplateStore(agency / "Templates"),
                researcher=researcher, graph=FakeGraph(agency / "Registry" / "demo_drafts.json"), agency_name="Studio Web")
    yield c
    registry.close()
