"""Tests for content extractor."""

import pytest
from datetime import datetime

from src.content_extractor import (
    ExtractedContent,
    TrafilaturaExtractor,
    NewspaperExtractor,
    WebContentExtractor,
    _extract_github_url,
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

    def test_orig_link_field(self):
        """Test that orig_link field can be set."""
        content = ExtractedContent(
            url="https://example.com/article",
            title="Test",
            orig_link="https://github.com/user/repo",
        )
        assert content.orig_link == "https://github.com/user/repo"

    def test_orig_link_defaults_to_none(self):
        """Test that orig_link defaults to None."""
        content = ExtractedContent(url="https://example.com/article")
        assert content.orig_link is None


class TestExtractGitHubUrl:
    """Test suite for _extract_github_url helper function."""

    def test_extracts_basic_github_url(self):
        """Test extraction of basic GitHub repo URL."""
        text = "Check out https://github.com/user/repo"
        result = _extract_github_url(text)
        assert result == "https://github.com/user/repo"

    def test_extracts_github_url_with_path(self):
        """Test extraction of GitHub URL with additional path."""
        text = "See https://github.com/user/repo/issues/123"
        result = _extract_github_url(text)
        assert result == "https://github.com/user/repo/issues/123"

    def test_extracts_http_github_url(self):
        """Test extraction of HTTP (not HTTPS) GitHub URL."""
        text = "Old link: http://github.com/owner/project"
        result = _extract_github_url(text)
        assert result == "http://github.com/owner/project"

    def test_extracts_www_github_url(self):
        """Test extraction of www.github.com URL."""
        text = "Found at https://www.github.com/company/tool"
        result = _extract_github_url(text)
        assert result == "https://www.github.com/company/tool"

    def test_returns_none_for_non_github_urls(self):
        """Test that non-GitHub URLs return None."""
        text = "Check https://gitlab.com/user/repo or https://bitbucket.org"
        result = _extract_github_url(text)
        assert result is None

    def test_returns_none_for_empty_text(self):
        """Test that empty text returns None."""
        assert _extract_github_url("") is None
        assert _extract_github_url(None) is None

    def test_extracts_first_github_url(self):
        """Test that first GitHub URL is extracted when multiple exist."""
        text = "Compare https://github.com/first/repo vs https://github.com/second/repo"
        result = _extract_github_url(text)
        assert result == "https://github.com/first/repo"


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

    def test_extract_valid_url_with_github_link(self, extractor, mocker):
        """Test that orig_link is set when extracted content contains GitHub URL."""
        # Mock the trafilatura extraction with GitHub URL in content
        mock_result = mocker.patch("src.content_extractor.trafilatura.fetch_url")
        mock_extract = mocker.patch("src.content_extractor.trafilatura.extract")

        mock_result.return_value = "<html>Content</html>"
        mock_extract.return_value = '{"title": "Article about code", "text": "Check out https://github.com/author/library for details."}'

        result = extractor.extract("https://example.com/article")

        assert result.title == "Article about code"
        assert result.orig_link == "https://github.com/author/library"

    def test_extract_valid_url_without_github_link(self, extractor, mocker):
        """Test that orig_link is None when extracted content has no GitHub URL."""
        # Mock the trafilatura extraction without GitHub URL
        mock_result = mocker.patch("src.content_extractor.trafilatura.fetch_url")
        mock_extract = mocker.patch("src.content_extractor.trafilatura.extract")

        mock_result.return_value = "<html>Content</html>"
        mock_extract.return_value = '{"title": "Regular Article", "text": "Just some normal content without GitHub links."}'

        result = extractor.extract("https://example.com/article")

        assert result.title == "Regular Article"
        assert result.orig_link is None

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

    def test_extract_uses_fallback_on_failure_with_github_url(self, extractor, mocker):
        """Test that fallback extractor also sets orig_link when GitHub URL found."""
        # Mock trafilatura to fail
        mock_fetch = mocker.patch("src.content_extractor.trafilatura.fetch_url")
        mock_fetch.return_value = None  # This will cause failure

        # Mock newspaper to succeed with GitHub URL in content
        mock_article = mocker.MagicMock()
        mock_article.title = "Fallback with GitHub"
        mock_article.text = "See https://github.com/fallback/repo for more"
        mock_article.authors = ["Author"]
        mock_article.publish_date = datetime(2026, 1, 1)

        mock_newspaper = mocker.patch("src.content_extractor.NewspaperArticle")
        mock_newspaper.return_value = mock_article

        result = extractor.extract("https://example.com/article")

        assert result.title == "Fallback with GitHub"
        assert result.extraction_method == "newspaper3k"
        assert result.orig_link == "https://github.com/fallback/repo"

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
