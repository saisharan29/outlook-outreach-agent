import json
from types import SimpleNamespace

from outreach.agent.loop import AgentLoop
from outreach.agent.models import Session
from outreach.config import Settings
from outreach.llm import make_llm
from outreach.llm_openai import OpenAILLM, _schema_for_openai


def _msg(content=None, tool_calls=None):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=tool_calls, refusal=None))])


def test_factory_picks_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai"); monkeypatch.setenv("OPENAI_API_KEY", "")
    assert make_llm(Settings()).provider == "openai" and not make_llm(Settings()).available
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    assert make_llm(Settings()).provider == "anthropic"
    monkeypatch.setenv("OPENAI_API_KEY", "k"); monkeypatch.setenv("LLM_PROVIDER", "openai")
    assert Settings().llm_key_present and Settings().llm_model == "gpt-5"


def test_schema_made_strict():
    s = _schema_for_openai({"type": "object", "properties": {"a": {"type": "string"}, "b": {"type": "array", "items": {
        "type": "object", "properties": {"c": {"type": "string"}}, "required": []}}}, "required": ["a"]})
    assert s["required"] == ["a", "b"] and s["additionalProperties"] is False
    assert s["properties"]["b"]["items"]["required"] == ["c"]


def test_structured_uses_json_schema():
    seen = {}
    def create(**kw):
        seen.update(kw)
        return _msg(content=json.dumps({"kind": "draft"}))
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    llm = OpenAILLM(client=client)
    out = llm.structured(system="s", user="u", schema={"type": "object", "properties": {"kind": {"type": "string"}}, "required": ["kind"]})
    assert out == {"kind": "draft"} and seen["response_format"]["json_schema"]["strict"] is True


def test_openai_tool_loop_drives_the_same_tools(ctx):
    turn = {"n": 0}
    def create(**kw):
        turn["n"] += 1
        assert all(t["type"] == "function" and t["function"]["strict"] for t in kw["tools"])
        if turn["n"] == 1:
            call = SimpleNamespace(id="c1", function=SimpleNamespace(name="find_file", arguments=json.dumps(
                {"company": "Garage Dupont", "type": "quote", "city": "Villeurbanne"})))
            return _msg(content=None, tool_calls=[call])
        last = kw["messages"][-1]
        assert last["role"] == "tool" and "GarageDupont_Villeurbanne_quote" in last["content"]
        return _msg(content="Found the quote file.")
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    reply = AgentLoop(ctx, OpenAILLM(client=client)).handle("find the quote for Garage Dupont", Session())
    assert "Found the quote file." in reply


def test_research_falls_back_without_web_search():
    def create(**kw):
        return _msg(content=json.dumps({"urls": []}))
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
                             responses=SimpleNamespace(create=lambda **kw: (_ for _ in ()).throw(RuntimeError("no web search"))))
    out = OpenAILLM(client=client).research(system="s", user="u", schema={"type": "object", "properties": {"urls": {"type": "array", "items": {"type": "string"}}}, "required": ["urls"]})
    assert out == {"urls": []}


def test_gemini_uses_openai_compatible_endpoint(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini"); monkeypatch.setenv("GEMINI_API_KEY", "g")
    s = Settings()
    llm = make_llm(s)
    assert llm.provider == "gemini" and llm.available and s.llm_model == "gemini-2.5-flash" and s.llm_key_present
    assert "generativelanguage.googleapis.com" in str(llm._client.base_url)


def test_gemini_research_skips_openai_web_search():
    calls = []
    def create(**kw):
        calls.append(kw)
        return _msg(content=json.dumps({"urls": ["https://x"]}))
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
                             responses=SimpleNamespace(create=lambda **kw: (_ for _ in ()).throw(AssertionError("must not be called"))))
    out = OpenAILLM(client=client, provider="gemini").research(system="s", user="u", schema={"type": "object", "properties": {"urls": {"type": "array", "items": {"type": "string"}}}, "required": ["urls"]})
    assert out == {"urls": ["https://x"]} and len(calls) == 1
