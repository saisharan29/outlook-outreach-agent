import os

from outreach.config import Settings, load_dotenv


def test_dotenv_is_read_without_overriding_real_env(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text('APP_PASSWORD=secret   # the chat password\nSECRET_KEY="quoted"\nMS_TENANT=from-file\n# comment\n', encoding="utf-8")
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("MS_TENANT", "from-env")
    load_dotenv(tmp_path / ".env")
    s = Settings()
    assert s.APP_PASSWORD == "secret" and s.SECRET_KEY == "quoted" and s.MS_TENANT == "from-env"
