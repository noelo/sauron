"""Tests for summarizer."""

import pytest
from datetime import datetime

from src.summarizer import OpenAISummarizer, SummaryResult, create_summarizer
from src.exceptions import SummarizationError
from config.settings import Settings


class TestSummaryResult:
    """Test suite for SummaryResult dataclass."""

    def test_creation(self):
        """Test creating a SummaryResult."""
        result = SummaryResult(
            text="This is a summary.",
            model="gpt-3.5-turbo",
            generated_at="2026-01-01T10:00:00",
            tokens_used=150,
            generation_time_seconds=1.5,
        )

        assert result.text == "This is a summary."
        assert result.model == "gpt-3.5-turbo"
        assert result.tokens_used == 150


class TestOpenAISummarizer:
    """Test suite for OpenAISummarizer."""

    @pytest.fixture
    def settings(self):
        return Settings(
            telegram_bot_token="test",
            telegram_channel_id="@test",
            llm_api_key="test-key",
            llm_base_url="http://localhost:8000/v1",
            llm_max_tokens=500,
            llm_temperature=0.3,
        )

    @pytest.fixture
    def summarizer(self, settings):
        return OpenAISummarizer(settings)

    def test_summarize_success(self, summarizer, mocker):
        """Test successful summarization."""
        # Mock OpenAI client
        mock_response = mocker.MagicMock()
        mock_response.choices = [mocker.MagicMock()]
        mock_response.choices[0].message.content = "This is the generated summary."
        mock_response.usage = mocker.MagicMock()
        mock_response.usage.total_tokens = 200
        mock_response.model = "gpt-3.5-turbo"  # Add model to response

        mock_create = mocker.patch.object(
            summarizer.client.chat.completions, "create", return_value=mock_response
        )

        result = summarizer.summarize(
            title="Test Article", content="This is the article content." * 10
        )

        assert result.text == "This is the generated summary."
        assert result.model == "gpt-3.5-turbo"
        assert result.tokens_used == 200
        assert result.generation_time_seconds >= 0

        # Verify API was called with correct parameters
        mock_create.assert_called_once()
        call_args = mock_create.call_args
        assert call_args.kwargs["max_tokens"] == 500
        assert call_args.kwargs["temperature"] == 0.3

    def test_summarize_api_error(self, summarizer, mocker):
        """Test handling of API errors."""
        mocker.patch.object(
            summarizer.client.chat.completions,
            "create",
            side_effect=Exception("API Rate Limit Exceeded"),
        )

        with pytest.raises(SummarizationError) as exc_info:
            summarizer.summarize(title="Test Article", content="Content here")

        assert "Failed to generate summary" in str(exc_info.value)

    def test_truncate_content_short(self, summarizer):
        """Test that short content is not truncated."""
        content = "Short content"

        result = summarizer._truncate_content(content, max_chars=1000)

        assert result == content

    def test_truncate_content_long(self, summarizer):
        """Test that long content is truncated."""
        content = "This is a sentence. " * 1000  # Very long content

        result = summarizer._truncate_content(content, max_chars=100)

        assert len(result) <= 103  # 100 + "..."
        assert result.endswith("...") or result.endswith(".")

    def test_truncate_at_sentence_boundary(self, summarizer):
        """Test that truncation tries to end at sentence boundary when period is near end."""
        content = "This is a very long first sentence with many words in it. Short."

        # Truncate at a point where period is in last 20% (period at position ~54, max_chars=60)
        result = summarizer._truncate_content(content, max_chars=60)

        # Should end at the period since it's in the last 20% (position 54 > 48)
        assert result == "This is a very long first sentence with many words in it."


class TestCreateSummarizer:
    """Test suite for summarizer factory."""

    def test_create_openai_summarizer(self, monkeypatch):
        """Test creating an OpenAI summarizer."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test")
        monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "@test")
        monkeypatch.setenv("TMM_MAAS_API_KEY", "test-key")
        monkeypatch.setenv("TMM_MAAS_QWEN_URL", "http://localhost:8000/v1")

        settings = Settings()

        summarizer = create_summarizer(settings)

        assert isinstance(summarizer, OpenAISummarizer)

    def test_create_custom_endpoint_summarizer(self, monkeypatch):
        """Test creating a custom endpoint summarizer."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test")
        monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "@test")
        monkeypatch.setenv("TMM_MAAS_API_KEY", "test-key")
        monkeypatch.setenv("TMM_MAAS_QWEN_URL", "http://custom:8000/v1")

        settings = Settings()

        summarizer = create_summarizer(settings)

        assert isinstance(summarizer, OpenAISummarizer)
