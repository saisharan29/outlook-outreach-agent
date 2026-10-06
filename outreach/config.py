"""Settings, loaded from environment variables only (.env is git-ignored).

Every number the spec calls "configurable" lives here with its default:
attachment size limit, registry age, default country and language.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def load_dotenv(path: Path | str = ".env") -> None:
    """Read KEY=value lines from .env into the environment (existing variables win). No dependency."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.split("  #", 1)[0].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


load_dotenv(os.getenv("DOTENV_PATH", ".env"))


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass
class Settings:
    # --- Agent core -------------------------------------------------------
    # "anthropic" (Claude, default), "openai" (a ChatGPT API key) or "gemini" (a Google AI Studio key). One key is enough.
    LLM_PROVIDER: str = field(default_factory=lambda: _env("LLM_PROVIDER", "anthropic"))
    ANTHROPIC_API_KEY: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    LLM_MODEL: str = field(default_factory=lambda: _env("LLM_MODEL", "claude-opus-5-5"))
    OPENAI_API_KEY: str = field(default_factory=lambda: _env("OPENAI_API_KEY"))
    OPENAI_MODEL: str = field(default_factory=lambda: _env("OPENAI_MODEL", "gpt-5"))
    GEMINI_API_KEY: str = field(default_factory=lambda: _env("GEMINI_API_KEY"))
    GEMINI_MODEL: str = field(default_factory=lambda: _env("GEMINI_MODEL", "gemini-2.5-flash"))
    # "pipeline": rules run the steps in order, the model helps with language (default).
    # "agent": the model drives the tools itself (same tools, same guardrails).
    AGENT_MODE: str = field(default_factory=lambda: _env("AGENT_MODE", "pipeline"))

    # --- Microsoft (Outlook drafts + OneDrive files) ----------------------
    MS_CLIENT_ID: str = field(default_factory=lambda: _env("MS_CLIENT_ID"))
    MS_CLIENT_SECRET: str = field(default_factory=lambda: _env("MS_CLIENT_SECRET"))
    # "common" accepts both Microsoft 365 business and personal Outlook.com accounts.
    MS_TENANT: str = field(default_factory=lambda: _env("MS_TENANT", "common"))
    MS_REDIRECT_URI: str = field(default_factory=lambda: _env("MS_REDIRECT_URI"))

    # --- Files -------------------------------------------------------------
    # "local": the Agency folder is on this machine (or synced by the OneDrive client).
    # "onedrive": read through Microsoft Graph (same login as Outlook).
    FILE_SOURCE: str = field(default_factory=lambda: _env("FILE_SOURCE", "local"))
    AGENCY_ROOT: str = field(default_factory=lambda: _env("AGENCY_ROOT", "./Agency"))
    VIDEOS_FOLDER: str = field(default_factory=lambda: _env("VIDEOS_FOLDER", "Videos"))
    QUOTES_FOLDER: str = field(default_factory=lambda: _env("QUOTES_FOLDER", "Quotes"))
    TEMPLATES_FOLDER: str = field(default_factory=lambda: _env("TEMPLATES_FOLDER", "Templates"))
    REGISTRY_FOLDER: str = field(default_factory=lambda: _env("REGISTRY_FOLDER", "Registry"))
    # When FILE_SOURCE=local and the folder is synced by the OneDrive client, the same folder's path
    # inside OneDrive (e.g. "Agency") lets the agent create sharing links for large videos.
    ONEDRIVE_PATH: str = field(default_factory=lambda: _env("ONEDRIVE_PATH"))
    MAX_ATTACHMENT_MB: int = field(default_factory=lambda: _int("MAX_ATTACHMENT_MB", 20))

    # --- Registry ----------------------------------------------------------
    REGISTRY_MAX_AGE_DAYS: int = field(default_factory=lambda: _int("REGISTRY_MAX_AGE_DAYS", 90))

    # --- Research ----------------------------------------------------------
    DEFAULT_COUNTRY: str = field(default_factory=lambda: _env("DEFAULT_COUNTRY", "LU"))
    DEFAULT_LANGUAGE: str = field(default_factory=lambda: _env("DEFAULT_LANGUAGE", "fr"))
    # The languages the owner writes templates in (the owner's market: French, German, Luxembourgish).
    SUPPORTED_LANGUAGES: str = field(default_factory=lambda: _env("SUPPORTED_LANGUAGES", "fr,de,lb"))
    TIMEZONE: str = field(default_factory=lambda: _env("TIMEZONE", "Europe/Luxembourg"))
    # Always in copy of every draft (comma-separated). The owner's partners.
    CC_RECIPIENTS: str = field(default_factory=lambda: _env("CC_RECIPIENTS", ""))
    # "anthropic": Claude's own web search (no extra key). "brave" / "serpapi": a search API.
    SEARCH_PROVIDER: str = field(default_factory=lambda: _env("SEARCH_PROVIDER", "anthropic"))
    BRAVE_API_KEY: str = field(default_factory=lambda: _env("BRAVE_API_KEY"))
    SERPAPI_KEY: str = field(default_factory=lambda: _env("SERPAPI_KEY"))
    GOOGLE_PLACES_API_KEY: str = field(default_factory=lambda: _env("GOOGLE_PLACES_API_KEY"))
    FETCH_TIMEOUT: int = field(default_factory=lambda: _int("FETCH_TIMEOUT", 15))

    # --- WhatsApp (section 6, options B + C by default; A when a validator is set) --------
    WHATSAPP_VALIDATOR_URL: str = field(default_factory=lambda: _env("WHATSAPP_VALIDATOR_URL"))
    WHATSAPP_VALIDATOR_KEY: str = field(default_factory=lambda: _env("WHATSAPP_VALIDATOR_KEY"))

    # --- Web app -----------------------------------------------------------
    APP_PASSWORD: str = field(default_factory=lambda: _env("APP_PASSWORD"))
    SECRET_KEY: str = field(default_factory=lambda: _env("SECRET_KEY", "dev-only-change-me"))
    PUBLIC_URL: str = field(default_factory=lambda: _env("PUBLIC_URL", "http://localhost:8080"))
    ENVIRONMENT: str = field(default_factory=lambda: _env("ENVIRONMENT", "development"))

    # Derived paths -----------------------------------------------------------
    @property
    def agency_root(self) -> Path:
        return Path(self.AGENCY_ROOT)

    @property
    def registry_dir(self) -> Path:
        return self.agency_root / self.REGISTRY_FOLDER

    @property
    def templates_dir(self) -> Path:
        return self.agency_root / self.TEMPLATES_FOLDER

    @property
    def max_attachment_bytes(self) -> int:
        return self.MAX_ATTACHMENT_MB * 1024 * 1024

    @property
    def languages(self) -> list[str]:
        return [x.strip().lower() for x in self.SUPPORTED_LANGUAGES.split(",") if x.strip()]

    @property
    def cc_list(self) -> list[str]:
        return [x.strip() for x in self.CC_RECIPIENTS.replace(";", ",").split(",") if x.strip()]

    @property
    def llm_model(self) -> str:
        return {"openai": self.OPENAI_MODEL, "gemini": self.GEMINI_MODEL}.get(self.LLM_PROVIDER.lower(), self.LLM_MODEL)

    @property
    def llm_key_present(self) -> bool:
        return bool({"openai": self.OPENAI_API_KEY, "gemini": self.GEMINI_API_KEY}.get(self.LLM_PROVIDER.lower(),
                                                                                       self.ANTHROPIC_API_KEY))

    def microsoft_configured(self) -> bool:
        return bool(self.MS_CLIENT_ID and self.MS_CLIENT_SECRET)

    def redirect_uri(self) -> str:
        return self.MS_REDIRECT_URI or f"{self.PUBLIC_URL.rstrip('/')}/auth/microsoft/callback"

    def check_production(self) -> None:
        if self.ENVIRONMENT.lower() != "production":
            return
        if self.SECRET_KEY == "dev-only-change-me":
            raise RuntimeError("SECRET_KEY must be set in production")
        if not self.APP_PASSWORD:
            raise RuntimeError("APP_PASSWORD must be set in production")


settings = Settings()
