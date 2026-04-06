"""Tests for configuration management."""

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from config.settings import Settings, get_settings


class TestSettings:
    """Test suite for Settings class."""

    def test_settings_loads_from_env(self, monkeypatch):
        """Test that settings load correctly from environment variables."""
        # Set required environment variables
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token_123")
        monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "@testchannel")
        monkeypatch.setenv("TMM_MAAS_API_KEY", "test_api_key")
        monkeypatch.setenv("TMM_MAAS_QWEN_URL", "http://localhost:8000/v1")

        settings = get_settings()

        assert settings.telegram_bot_token == "test_token_123"
        assert settings.telegram_channel_id == "@testchannel"
        assert settings.llm_api_key == "test_api_key"
        assert settings.llm_base_url == "http://localhost:8000/v1"

    def test_settings_default_values(self, monkeypatch):
        """Test that default values are set correctly."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "@channel")
        monkeypatch.setenv("TMM_MAAS_API_KEY", "key")
        monkeypatch.setenv("TMM_MAAS_QWEN_URL", "http://localhost:8000/v1")

        settings = get_settings()

        assert settings.llm_max_tokens == 500
        assert settings.llm_temperature == 0.3
        assert settings.data_dir == Path("./data")
        assert settings.articles_subdir == "articles"
        assert settings.log_level == "INFO"
        assert settings.processing_interval == 5

    def test_settings_missing_required_raises_error(self, monkeypatch):
        """Test that missing required fields raise ValidationError."""
        # Clear all env vars that might be set
        for key in [
            "TELEGRAM_BOT_TOKEN",
            "TELEGRAM_CHANNEL_ID",
            "TMM_MAAS_API_KEY",
            "TMM_MAAS_QWEN_URL",
        ]:
            monkeypatch.delenv(key, raising=False)

        with pytest.raises(ValidationError) as exc_info:
            # Create Settings directly to avoid any caching from get_settings()
            Settings()

        error_msg = str(exc_info.value)
        assert "telegram_bot_token" in error_msg or "TELEGRAM_BOT_TOKEN" in error_msg

    def test_llm_temperature_validation(self, monkeypatch):
        """Test that temperature is validated within range."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test")
        monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "@channel")
        monkeypatch.setenv("TMM_MAAS_API_KEY", "key")
        monkeypatch.setenv("TMM_MAAS_QWEN_URL", "http://localhost:8000/v1")
        monkeypatch.setenv("LLM_TEMPERATURE", "3.0")  # Out of range

        with pytest.raises(ValidationError) as exc_info:
            get_settings()

        assert "temperature" in str(exc_info.value).lower()

    def test_llm_max_tokens_validation(self, monkeypatch):
        """Test that max_tokens is validated within range."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test")
        monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "@channel")
        monkeypatch.setenv("TMM_MAAS_API_KEY", "key")
        monkeypatch.setenv("TMM_MAAS_QWEN_URL", "http://localhost:8000/v1")
        monkeypatch.setenv("LLM_MAX_TOKENS", "10")  # Below minimum

        with pytest.raises(ValidationError) as exc_info:
            get_settings()

        assert "max_tokens" in str(exc_info.value).lower()

    def test_articles_dir_property(self, monkeypatch):
        """Test that articles_dir property returns correct path."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test")
        monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "@channel")
        monkeypatch.setenv("TMM_MAAS_API_KEY", "key")
        monkeypatch.setenv("TMM_MAAS_QWEN_URL", "http://localhost:8000/v1")

        settings = get_settings()

        assert settings.articles_dir == Path("./data/articles")

    def test_log_path_property(self, monkeypatch):
        """Test that log_path property returns correct path."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test")
        monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "@channel")
        monkeypatch.setenv("TMM_MAAS_API_KEY", "key")
        monkeypatch.setenv("TMM_MAAS_QWEN_URL", "http://localhost:8000/v1")

        settings = get_settings()

        assert settings.log_path == Path("./data/processing_log.json")
