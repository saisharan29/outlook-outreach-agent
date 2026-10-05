from types import SimpleNamespace

from outreach.agent.loop import AgentLoop
from outreach.agent.models import Session
from outreach.llm import LLM


class FakeMessages:
    """Scripted Claude: first asks for identify_company, then find_file, create_draft, then ends."""

    def __init__(self):
        self.turn = 0
        self.received = []

    def create(self, **kw):
        self.received.append(kw)
        assert all(t.get("strict") for t in kw["tools"]) and not any(t["name"] == "send_email" for t in kw["tools"])
        script = [
            [SimpleNamespace(type="tool_use", id="t1", name="identify_company", input={"name": "Garage Dupont", "city": "", "website": ""})],
            [SimpleNamespace(type="tool_use", id="t2", name="find_contacts", input={"company": {"name": "Garage Dupont", "city": "Villeurbanne", "website": "", "country": "FR"}, "force_refresh": False})],
            [SimpleNamespace(type="tool_use", id="t3", name="find_file", input={"company": "Garage Dupont", "type": "quote", "city": "Villeurbanne"})],
            [SimpleNamespace(type="tool_use", id="t4", name="create_draft", input={"recipient": "info@garage-dupont.example", "template": "quote",
                             "variables": {"company_name": "Garage Dupont", "contact_name": "", "city": "Villeurbanne", "country": "FR", "language": ""},
                             "attachment": "GarageDupont_Villeurbanne_quote_2026-10-03.pdf", "confirm_duplicate": False})],
            [SimpleNamespace(type="text", text="Draft created for Garage Dupont.\n\nNeeds your attention\n- nothing")],
        ]
        content = script[self.turn]
        self.turn += 1
        return SimpleNamespace(content=content, stop_reason="tool_use" if content[0].type == "tool_use" else "end_turn")


def test_agent_mode_drives_the_same_tools(ctx):
    fake = FakeMessages()
    client = SimpleNamespace(beta=SimpleNamespace(messages=fake), messages=fake)
    llm = LLM(client=client, use_fallbacks=False)
    reply = AgentLoop(ctx, llm).handle("Quote email for Garage Dupont", Session())
    assert "Draft created" in reply and "Tool log: draft created for info@garage-dupont.example" in reply
    assert ctx.graph.drafts[0]["to"] == "info@garage-dupont.example"
    assert fake.received[-1]["messages"][-2]["content"][0]["type"] == "tool_result"


def test_agent_mode_tool_refusal_is_returned_as_data(ctx):
    class Script:
        def __init__(self):
            self.turn = 0
        def create(self, **kw):
            self.turn += 1
            if self.turn == 1:
                return SimpleNamespace(stop_reason="tool_use", content=[SimpleNamespace(
                    type="tool_use", id="x", name="create_draft", input={"recipient": "guess@nowhere.fr", "template": "quote",
                    "variables": {"company_name": "Garage Dupont", "contact_name": "", "city": "", "country": "", "language": ""},
                    "attachment": "GarageDupont_Villeurbanne_quote_2026-10-03.pdf", "confirm_duplicate": False})])
            msgs = kw["messages"]
            assert "no source" in msgs[-1]["content"][0]["content"]
            return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="Refused, as it should.")])
    s = Script()
    llm = LLM(client=SimpleNamespace(beta=SimpleNamespace(messages=s), messages=s), use_fallbacks=False)
    assert "Refused" in AgentLoop(ctx, llm).handle("x", Session()) and not ctx.graph.drafts
