"""Base URL handler and fallback implementation."""

import re
from abc import ABC, abstractmethod
from typing import Optional
from urllib.parse import urlparse

import structlog

from src.models import ExtractedContent

logger = structlog.get_logger(__name__)


class URLHandler(ABC):
    """Abstract base class for domain-specific URL handlers."""

    def __init__(self):
        self.logger = structlog.get_logger(__name__)

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Check if this handler can process the given URL."""
        pass

    @abstractmethod
    def handle(self, url: str) -> ExtractedContent:
        """Process the URL and return extracted content."""
        pass

    def _get_domain(self, url: str) -> str:
        """Extract domain from URL."""
        return urlparse(url).netloc.lower()

    def _extract_github_url(self, text: str) -> Optional[str]:
        """Extract github.com URL from text content.

        Looks for URLs matching github.com/owner/repo patterns.
        Returns the first match found, or None if no GitHub URL is found.
        """
        if not text:
            return None

        # Pattern to match github.com URLs with owner/repo format
        github_pattern = r"https?://(?:www\.)?github\.com/[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+(?:/[a-zA-Z0-9_-]+)*"

        match = re.search(github_pattern, text)
        if match:
            return match.group(0)

        return None


class FallbackHandler(URLHandler):
    """Default handler for URLs that don't match any specific domain handler."""

    def __init__(self):
        super().__init__()
        self._primary_extractor = None
        self._fallback_extractor = None

    def _get_extractors(self):
        """Lazy load extractors to avoid circular imports."""
        if self._primary_extractor is None:
            from src.content_extractor import TrafilaturaExtractor, NewspaperExtractor

            self._primary_extractor = TrafilaturaExtractor()
            self._fallback_extractor = NewspaperExtractor()
        return self._primary_extractor, self._fallback_extractor

    def can_handle(self, url: str) -> bool:
        """Fallback handler can handle any URL."""
        return True

    def handle(self, url: str) -> ExtractedContent:
        """Extract content using standard extraction pipeline."""
        self.logger.info("using_fallback_handler", url=url)

        primary_extractor, fallback_extractor = self._get_extractors()

        # Try primary extractor first
        try:
            content = primary_extractor.extract(url)
            self.logger.info(
                "fallback_extraction_successful", url=url, method="trafilatura"
            )
            # Check for GitHub URL in extracted content
            github_url = self._extract_github_url(content.content)
            if github_url:
                content.orig_link = github_url
                self.logger.info(
                    "found_github_url_in_content", url=url, github_url=github_url
                )
            return content
        except Exception as e:
            self.logger.warning("fallback_primary_failed", url=url, error=str(e))

        # Try fallback extractor
        try:
            content = fallback_extractor.extract(url)
            self.logger.info(
                "fallback_extraction_successful", url=url, method="newspaper3k"
            )
            # Check for GitHub URL in extracted content
            github_url = self._extract_github_url(content.content)
            if github_url:
                content.orig_link = github_url
                self.logger.info(
                    "found_github_url_in_content", url=url, github_url=github_url
                )
            return content
        except Exception as e:
            self.logger.error("fallback_extraction_failed", url=url, error=str(e))
            raise
