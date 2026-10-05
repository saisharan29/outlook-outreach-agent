"""The one place that talks to Claude.

Three uses: (1) understanding a free-text request (FR-01), (2) web research with Claude's own
web search when no search API key is configured, (3) the tool-calling agent loop (AGENT_MODE=agent).

Every call is optional: without ANTHROPIC_API_KEY the rest of the product still works with the
regex parser and the deterministic crawler. Text found on web pages is passed to the model as
data inside tagged blocks and never as instructions (section 8).
"""
from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:  # pragma: no cover
    from .llm_openai import OpenAILLM

DEFAULT_MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"

WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search", "max_uses": 6}
WEB_FETCH_TOOL = {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 6, "max_content_tokens": 20000}

_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.S)


def _extract_json(text: str) -> Any:
    m = _JSON_BLOCK.search(text)
    candidates = [m.group(1)] if m else []
    # Also try the outermost braces.
    first, last = text.find("{"), text.rfind("}")
    if first != -1 and last > first:
        candidates.append(text[first:last + 1])
    for c in candidates:
        try:
            return json.loads(c)
        except ValueError:
            continue
    raise ValueError("no JSON in model answer")


def make_llm(settings) -> "LLM | OpenAILLM":
    """The configured provider: LLM_PROVIDER=anthropic (default) or openai. Unavailable when no key."""
    if settings.LLM_PROVIDER.lower() == "openai":
        from .llm_openai import OpenAILLM
        return OpenAILLM(api_key=settings.OPENAI_API_KEY, model=settings.OPENAI_MODEL)
    return LLM(api_key=settings.ANTHROPIC_API_KEY, model=settings.LLM_MODEL)


class LLM:
    provider = "anthropic"

    def __init__(self, api_key: str = "", model: str = DEFAULT_MODEL, client: Any = None, use_fallbacks: bool = True):
        self.model = model or DEFAULT_MODEL
        self.use_fallbacks = use_fallbacks
        self._client = client
        if client is None and api_key:
            import anthropic
            self._client = anthropic.Anthropic(api_key=api_key)

    @property
    def available(self) -> bool:
        return self._client is not None

    # --- low level -----------------------------------------------------------
    def _create(self, **kw) -> Any:
        """messages.create with the server-side refusal fallback; retried without it when the
        platform rejects the parameter (older proxies, other platforms)."""
        if not self._client:
            raise RuntimeError("No Anthropic API key configured.")
        if self.use_fallbacks:
            try:
                return self._client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **kw)
            except Exception as exc:  # BadRequestError on platforms without the beta
                if "fallback" not in str(exc).lower() and "beta" not in str(exc).lower():
                    raise
        return self._client.messages.create(**kw)

    @staticmethod
    def text_of(response: Any) -> str:
        return "".join(getattr(b, "text", "") for b in response.content if getattr(b, "type", "") == "text")

    # --- structured answer ----------------------------------------------------
    def structured(self, *, system: str, user: str, schema: dict, effort: str = "medium",
                   max_tokens: int = 4000) -> dict:
        response = self._create(
            model=self.model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}})
        if response.stop_reason == "refusal":
            raise RuntimeError("The model declined this request.")
        return json.loads(self.text_of(response))

    # --- research with Claude's own web search -----------------------------------
    def research(self, *, system: str, user: str, schema: dict, effort: str = "high",
                 max_tokens: int = 16000, allowed_domains: list[str] | None = None) -> dict:
        """Runs web search + fetch server-side, then converts the final answer to `schema`."""
        tools = [dict(WEB_SEARCH_TOOL), dict(WEB_FETCH_TOOL)]
        if allowed_domains:
            tools[1]["allowed_domains"] = allowed_domains
        messages: list[dict] = [{"role": "user", "content": user}]
        response = None
        for _ in range(6):
            response = self._create(model=self.model, max_tokens=max_tokens, system=system,
                                    tools=tools, messages=messages, output_config={"effort": effort})
            if response.stop_reason == "pause_turn":
                messages.append({"role": "assistant", "content": response.content})
                continue
            break
        if response is None or response.stop_reason == "refusal":
            raise RuntimeError("The model declined this research request.")
        text = self.text_of(response)
        try:
            data = _extract_json(text)
            if isinstance(data, dict):
                return data
        except ValueError:
            pass
        # Second pass: a plain conversion of the prose into the schema.
        return self.structured(system="Convert the research notes into the requested JSON. Do not add facts.",
                               user=text, schema=schema, effort="low")

    # --- tool-calling loop (AGENT_MODE=agent) -------------------------------------
    def run_tools(self, *, system: str, messages: list[dict], tools: list[dict],
                  execute: Callable[[str, dict], str], max_turns: int = 30, effort: str = "high",
                  max_tokens: int = 16000) -> tuple[str, list[dict]]:
        """Manual agentic loop: the caller owns `messages` (history) and `execute` (strict tools)."""
        history = list(messages)
        final_text = ""
        for _ in range(max_turns):
            response = self._create(model=self.model, max_tokens=max_tokens, system=system,
                                    tools=tools, messages=history, output_config={"effort": effort})
            history.append({"role": "assistant", "content": response.content})
            if response.stop_reason == "refusal":
                final_text = "The model declined to continue this request."
                break
            if response.stop_reason == "pause_turn":
                continue
            calls = [b for b in response.content if getattr(b, "type", "") == "tool_use"]
            if response.stop_reason != "tool_use" or not calls:
                final_text = self.text_of(response)
                break
            results = []
            for call in calls:
                try:
                    out = execute(call.name, dict(call.input))
                    results.append({"type": "tool_result", "tool_use_id": call.id, "content": out})
                except Exception as exc:
                    results.append({"type": "tool_result", "tool_use_id": call.id,
                                    "content": f"error: {exc}", "is_error": True})
            history.append({"role": "user", "content": results})
        else:
            final_text = "Stopped: too many steps for one request."
        return final_text, history
