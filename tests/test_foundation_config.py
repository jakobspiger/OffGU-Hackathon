from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config import PROJECT_ROOT, Settings
from src.errors import ConfigurationError


@pytest.fixture(autouse=True)
def isolate_env(monkeypatch):
    import os

    for name in list(os.environ):
        if name.upper().startswith(("OPENAI_", "AFS_")):
            monkeypatch.delenv(name)


def test_offline_settings_do_not_require_key():
    settings = Settings(_env_file=None)
    with pytest.raises(ConfigurationError, match="OPENAI_API_KEY.*OPENAI_MODEL"):
        settings.require_llm()


def test_example_env_is_valid_and_offline():
    settings = Settings(_env_file=PROJECT_ROOT / ".env.example")
    assert settings.openai_api_key is None
    assert settings.openai_base_url is None


def test_env_overrides_dotenv_and_secret_is_not_serialized(tmp_path, monkeypatch):
    dotenv = tmp_path / ".env"
    dotenv.write_text("OPENAI_MODEL=file-model\nOPENAI_API_KEY=synthetic-secret\n")
    monkeypatch.setenv("OPENAI_MODEL", "environment-model")
    settings = Settings(_env_file=dotenv)
    settings.require_llm()
    assert settings.openai_model == "environment-model"
    assert "synthetic-secret" not in repr(settings)
    assert "synthetic-secret" not in settings.model_dump_json()


@pytest.mark.parametrize("value", ["0", "-1", "301"])
def test_timeout_bounds(monkeypatch, value):
    monkeypatch.setenv("AFS_REQUEST_TIMEOUT_SECONDS", value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_paths_are_independent_of_terminal_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(_env_file=None, afs_source_dir=Path("materials"))
    assert settings.afs_source_dir == PROJECT_ROOT / "materials"


def test_base_url_rejects_embedded_credentials_without_leaking_them(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://user:synthetic-secret@example.com/v1")
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None)
    assert "synthetic-secret" not in str(error.value)


def test_unknown_dotenv_key_fails_loudly(tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text("OPENAI_MODLE=typo\n")
    with pytest.raises(ValidationError):
        Settings(_env_file=dotenv)
