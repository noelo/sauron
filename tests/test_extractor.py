"""Tests for content extractor."""

import pytest
from datetime import datetime

from src.content_extractor import (
    ExtractedContent,
    TrafilaturaExtractor,
    NewspaperExtractor,
    WebContentExtractor,
)
from src.exceptions import ExtractionError


class TestExtractedContent:
    """Test suite for ExtractedContent dataclass."""

    def test_basic_creation(self):
        """Test creating an ExtractedContent object."""
        content = ExtractedContent(
            url="https://example.com/article",
            title="Test Title",
            content="This is the article content.",
        )

        assert content.url == "https://example.com/article"
        assert content.title == "Test Title"
        assert content.word_count == 5
        assert content.domain == "example.com"
        assert content.extraction_timestamp  # Should be auto-set

    def test_word_count_calculation(self):
        """Test that word count is calculated correctly."""
        content = ExtractedContent(
            url="https://example.com/article",
            content="One two three four five six seven eight nine ten",
        )

        assert content.word_count == 10

    def test_domain_extraction(self):
        """Test that domain is extracted from URL."""
        content = ExtractedContent(url="https://subdomain.example.com/path")

        assert content.domain == "subdomain.example.com"

    def test_custom_timestamp(self):
        """Test that custom timestamp can be set."""
        custom_time = "2026-01-01T10:00:00"
        content = ExtractedContent(
            url="https://example.com/article", extraction_timestamp=custom_time
        )

        assert content.extraction_timestamp == custom_time


class TestWebContentExtractor:
    """Test suite for WebContentExtractor."""

    @pytest.fixture
    def extractor(self):
        return WebContentExtractor()

    def test_extract_valid_url(self, extractor, mocker):
        """Test extracting content from a valid URL."""
        # Mock the trafilatura extraction
        mock_result = mocker.patch("src.content_extractor.trafilatura.fetch_url")
        mock_extract = mocker.patch("src.content_extractor.trafilatura.extract")

        mock_result.return_value = "<html>Content</html>"
        mock_extract.return_value = (
            '{"title": "Test Article", "text": "Article content here."}'
        )

        result = extractor.extract("https://example.com/article")

        assert result.title == "Test Article"
        assert result.content == "Article content here."
        assert result.extraction_method == "trafilatura"

    def test_extract_uses_fallback_on_failure(self, extractor, mocker):
        """Test that fallback extractor is used when primary fails."""
        # Mock trafilatura to fail
        mock_fetch = mocker.patch("src.content_extractor.trafilatura.fetch_url")
        mock_fetch.return_value = None  # This will cause failure

        # Mock newspaper to succeed
        mock_article = mocker.MagicMock()
        mock_article.title = "Fallback Title"
        mock_article.text = "Fallback content"
        mock_article.authors = ["Author Name"]
        mock_article.publish_date = datetime(2026, 1, 1)

        mock_newspaper = mocker.patch("src.content_extractor.NewspaperArticle")
        mock_newspaper.return_value = mock_article

        result = extractor.extract("https://example.com/article")

        assert result.title == "Fallback Title"
        assert result.extraction_method == "newspaper3k"

    def test_extract_invalid_url_raises_error(self, extractor):
        """Test that invalid URLs raise ExtractionError."""
        with pytest.raises(ExtractionError) as exc_info:
            extractor.extract("not-a-valid-url")

        assert "Invalid URL" in str(exc_info.value)

    def test_extract_unsupported_protocol(self, extractor):
        """Test that unsupported protocols raise ExtractionError."""
        with pytest.raises(ExtractionError) as exc_info:
            extractor.extract("ftp://example.com/file")

        assert "Unsupported protocol" in str(exc_info.value)

    def test_extract_both_extractors_fail(self, extractor, mocker):
        """Test error when both extractors fail."""
        # Mock both to fail
        mocker.patch("src.content_extractor.trafilatura.fetch_url", return_value=None)
        mocker.patch(
            "src.content_extractor.NewspaperArticle",
            side_effect=Exception("Network error"),
        )

        with pytest.raises(ExtractionError) as exc_info:
            extractor.extract("https://example.com/article")

        assert "FallbackHandler" in str(exc_info.value)
