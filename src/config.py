"""Explicit settings loading: importing modules never reads credentials or calls APIs."""

from pathlib import Path

from pydantic import Field, HttpUrl, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.errors import ConfigurationError

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="forbid",
        hide_input_in_errors=True,
    )

    openai_api_key: SecretStr | None = Field(default=None, exclude=True, repr=False)
    openai_model: str | None = None
    openai_base_url: HttpUrl | None = None
    afs_request_timeout_seconds: float = Field(default=60, gt=0, le=300)
    afs_max_retries: int = Field(default=2, ge=0, le=5)
    afs_retrieval_k: int = Field(default=8, ge=1, le=50)
    afs_source_dir: Path = PROJECT_ROOT / "materials"
    afs_index_dir: Path = PROJECT_ROOT / "data/index"
    afs_embedding_model: str | None = None

    @field_validator(
        "openai_api_key",
        "openai_model",
        "openai_base_url",
        "afs_embedding_model",
        mode="before",
    )
    @classmethod
    def blank_to_none(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("afs_source_dir", "afs_index_dir", mode="after")
    @classmethod
    def resolve_project_path(cls, value: Path) -> Path:
        return value.resolve() if value.is_absolute() else (PROJECT_ROOT / value).resolve()

    @field_validator("openai_base_url")
    @classmethod
    def reject_embedded_secrets(cls, value: HttpUrl | None) -> HttpUrl | None:
        if value and (value.username or value.password or value.query or value.fragment):
            raise ValueError(
                "Base URL must not contain credentials, query parameters or fragments."
            )
        return value

    def require_llm(self) -> None:
        missing = []
        if self.openai_api_key is None:
            missing.append("OPENAI_API_KEY")
        if not self.openai_model:
            missing.append("OPENAI_MODEL")
        if missing:
            raise ConfigurationError("Missing runtime settings: " + ", ".join(missing))
