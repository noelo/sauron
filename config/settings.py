"""Configuration management using Pydantic Settings."""

from pathlib import Path
from typing import Literal, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Telegram Configuration
    telegram_bot_token: str = Field(
        ..., description="Telegram bot token from @BotFather"
    )
    telegram_channel_id: str = Field(
        ..., description="Channel ID or username to monitor"
    )

    # LLM Configuration
    llm_api_key: str = Field(
        ..., alias="TMM_MAAS_API_KEY", description="API key for the LLM endpoint"
    )
    llm_base_url: str = Field(
        ..., alias="TMM_MAAS_QWEN_URL", description="Base URL for LLM API"
    )
    llm_max_tokens: int = Field(
        default=500, ge=50, le=4000, description="Max tokens for summary"
    )
    llm_temperature: float = Field(
        default=0.3, ge=0.0, le=2.0, description="Temperature for generation"
    )
    llm_model: str = Field(
        default="gpt-3.5-turbo", description="Model name for LLM API"
    )

    # Storage Configuration
    data_dir: Path = Field(default=Path("./data"), description="Path to data directory")
    articles_subdir: str = Field(
        default="articles", description="Subdirectory for article JSONs"
    )
    log_file: str = Field(
        default="processing_log.json", description="Processing log filename"
    )

    # Application Configuration
    log_level: str = Field(default="INFO", description="Logging level")
    processing_interval: int = Field(
        default=5, ge=1, description="Seconds between Telegram polls"
    )

    @field_validator("data_dir", "articles_subdir", "log_file")
    def validate_not_empty(cls, v):
        if isinstance(v, str) and not v.strip():
            raise ValueError("Cannot be empty")
        return v

    @property
    def articles_dir(self) -> Path:
        """Get the full path to articles directory."""
        return self.data_dir / self.articles_subdir

    @property
    def log_path(self) -> Path:
        """Get the full path to processing log."""
        return self.data_dir / self.log_file

    def setup_directories(self) -> None:
        """Create necessary directories if they don't exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.articles_dir.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    """Get application settings instance."""
    return Settings()
