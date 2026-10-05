"""OpenAI as the model provider (LLM_PROVIDER=openai), and Gemini through Google's OpenAI-compatible
endpoint (LLM_PROVIDER=gemini): the same three capabilities as llm.LLM, so the rest of the product
does not know which provider is behind it.

- structured(): Chat Completions with a strict JSON schema.
- research():   Responses API with OpenAI's web search tool, then a structured conversion.
- run_tools():  the tool-calling loop over the agent's strict tools.

Web page text is passed as data inside tagged blocks and never as instructions (spec section 8).
"""
from __future__ import annotations

import json
from typing import Any, Callable

DEFAULT_MODEL = "gpt-5"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


def _schema_for_openai(schema: dict) -> dict:
    """OpenAI strict mode wants additionalProperties=false and every property required, at every level."""
    def fix(node: Any) -> Any:
        if isinstance(node, dict):
            node = dict(node)
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"].keys())
                node["properties"] = {k: fix(v) for k, v in node["properties"].items()}
            if "items" in node:
                node["items"] = fix(node["items"])
            return node
        return node
    return fix(schema)


class OpenAILLM:
    provider = "openai"

    def __init__(self, api_key: str = "", model: str = DEFAULT_MODEL, client: Any = None,
                 base_url: str = "", provider: str = "openai"):
        self.model = model or DEFAULT_MODEL
        self.provider = provider
        self._client = client
        if client is None and api_key:
            from openai import OpenAI
            self._client = OpenAI(api_key=api_key, base_url=base_url or None)

    @property
    def available(self) -> bool:
        return self._client is not None

    def _chat(self, **kw) -> Any:
        if not self._client:
            raise RuntimeError("No OpenAI API key configured.")
        return self._client.chat.completions.create(model=self.model, **kw)

    # --- structured answer ----------------------------------------------------
    def structured(self, *, system: str, user: str, schema: dict, effort: str = "medium",
                   max_tokens: int = 4000) -> dict:
        r = self._chat(messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                       response_format={"type": "json_schema", "json_schema": {
                           "name": "answer", "strict": True, "schema": _schema_for_openai(schema)}})
        msg = r.choices[0].message
        if getattr(msg, "refusal", None):
            raise RuntimeError("The model declined this request.")
        return json.loads(msg.content or "{}")

    # --- research with OpenAI's web search ------------------------------------
    def research(self, *, system: str, user: str, schema: dict, effort: str = "high",
                 max_tokens: int = 16000, allowed_domains: list[str] | None = None) -> dict:
        text = ""
        try:
            if self.provider != "openai":
                raise RuntimeError("web search only through OpenAI's Responses API")
            r = self._client.responses.create(model=self.model, instructions=system, input=user,
                                              tools=[{"type": "web_search"}])
            text = getattr(r, "output_text", "") or ""
        except Exception:
            text = ""
        if not text:
            # No web search available on this account/model: answer from the model alone, as data to verify.
            return self.structured(system=system, user=user, schema=schema, effort=effort)
        return self.structured(system="Convert the research notes into the requested JSON. Do not add facts.",
                               user=text, schema=schema, effort="low")

    # --- tool-calling loop -----------------------------------------------------
    @staticmethod
    def _tools(tools: list[dict]) -> list[dict]:
        return [{"type": "function", "function": {
            "name": t["name"], "description": t.get("description", ""), "strict": True,
            "parameters": _schema_for_openai(t["input_schema"])}} for t in tools]

    def run_tools(self, *, system: str, messages: list[dict], tools: list[dict],
                  execute: Callable[[str, dict], str], max_turns: int = 30, effort: str = "high",
                  max_tokens: int = 16000) -> tuple[str, list[dict]]:
        history = list(messages)
        final_text = ""
        oa_tools = self._tools(tools)
        for _ in range(max_turns):
            r = self._chat(messages=[{"role": "system", "content": system}] + history, tools=oa_tools)
            msg = r.choices[0].message
            if getattr(msg, "refusal", None):
                final_text = "The model declined to continue this request."
                break
            calls = list(msg.tool_calls or [])
            history.append({"role": "assistant", "content": msg.content or "",
                            "tool_calls": [{"id": c.id, "type": "function",
                                            "function": {"name": c.function.name, "arguments": c.function.arguments}}
                                           for c in calls]} if calls else {"role": "assistant", "content": msg.content or ""})
            if not calls:
                final_text = msg.content or ""
                break
            for c in calls:
                try:
                    args = json.loads(c.function.arguments or "{}")
                    out = execute(c.function.name, args)
                except Exception as exc:
                    out = f"error: {exc}"
                history.append({"role": "tool", "tool_call_id": c.id, "content": out})
        else:
            final_text = "Stopped: too many steps for one request."
        return final_text, history
