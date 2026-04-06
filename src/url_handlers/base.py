"""Base URL handler and fallback implementation."""

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
            return content
        except Exception as e:
            self.logger.warning("fallback_primary_failed", url=url, error=str(e))

        # Try fallback extractor
        try:
            content = fallback_extractor.extract(url)
            self.logger.info(
                "fallback_extraction_successful", url=url, method="newspaper3k"
            )
            return content
        except Exception as e:
            self.logger.error("fallback_extraction_failed", url=url, error=str(e))
            raise
