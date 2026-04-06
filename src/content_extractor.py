"""Content extraction from web articles."""

import structlog
from abc import ABC, abstractmethod
from typing import List, Optional
from urllib.parse import urlparse

import requests
import trafilatura
from newspaper import Article as NewspaperArticle

from src.exceptions import ExtractionError
from src.models import ExtractedContent

logger = structlog.get_logger(__name__)


class ContentExtractor(ABC):
    """Abstract base class for content extractors."""

    @abstractmethod
    def extract(self, url: str) -> ExtractedContent:
        """Extract content from a URL."""
        pass


class TrafilaturaExtractor(ContentExtractor):
    """Content extractor using trafilatura library."""

    def extract(self, url: str) -> ExtractedContent:
        """Extract content using trafilatura."""
        logger.info("extracting_with_trafilatura", url=url)

        try:
            # Fetch and extract in one call
            result = trafilatura.fetch_url(url)

            if result is None:
                raise ExtractionError(f"Failed to fetch URL: {url}")

            # Extract metadata and content
            extracted = trafilatura.extract(
                result,
                output_format="json",
                with_metadata=True,
                include_comments=False,
                include_tables=False,
            )

            if not extracted:
                raise ExtractionError(f"No content extracted from: {url}")

            import json

            data = json.loads(extracted)

            return ExtractedContent(
                url=url,
                title=data.get("title"),
                author=data.get("author"),
                publish_date=data.get("date"),
                content=data.get("text", ""),
                extraction_method="trafilatura",
            )

        except Exception as e:
            logger.error("trafilatura_extraction_failed", url=url, error=str(e))
            raise ExtractionError(
                f"Trafilatura extraction failed for {url}: {e}"
            ) from e


class NewspaperExtractor(ContentExtractor):
    """Fallback content extractor using newspaper3k."""

    def extract(self, url: str) -> ExtractedContent:
        """Extract content using newspaper3k."""
        logger.info("extracting_with_newspaper", url=url)

        try:
            article = NewspaperArticle(url)
            article.download()
            article.parse()

            if not article.text:
                raise ExtractionError(f"No content extracted from: {url}")

            # Format publish date
            publish_date = None
            if article.publish_date:
                publish_date = article.publish_date.isoformat()

            return ExtractedContent(
                url=url,
                title=article.title,
                author=", ".join(article.authors) if article.authors else None,
                publish_date=publish_date,
                content=article.text,
                extraction_method="newspaper3k",
            )

        except Exception as e:
            logger.error("newspaper_extraction_failed", url=url, error=str(e))
            raise ExtractionError(f"Newspaper extraction failed for {url}: {e}") from e


# Import URL handlers at bottom to avoid circular imports
from src.url_handlers import (
    URLHandler,
    TwitterHandler,
    GitHubHandler,
    RedditHandler,
    FallbackHandler,
)


class WebContentExtractor:
    """Primary content extractor with domain-specific handlers and fallback."""

    def __init__(self):
        # Import handlers here to avoid circular import
        # Register handlers in order of priority
        self.handlers: List[URLHandler] = [
            TwitterHandler(),
            GitHubHandler(),
            RedditHandler(),
            FallbackHandler(),  # Always last - matches everything
        ]

    def extract(self, url: str) -> ExtractedContent:
        """
        Extract content from a URL using appropriate handler.

        Routes URLs to domain-specific handlers (x.com, github.com, reddit.com)
        or falls back to generic extraction.

        Args:
            url: The URL to extract content from

        Returns:
            ExtractedContent object with article data

        Raises:
            ExtractionError: If no handler can process the URL
        """
        logger.info("starting_extraction", url=url)

        # Validate URL
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            raise ExtractionError(f"Invalid URL format: {url}")

        if parsed.scheme not in ("http", "https"):
            raise ExtractionError(f"Unsupported protocol: {parsed.scheme}")

        # Find appropriate handler
        for handler in self.handlers:
            if handler.can_handle(url):
                handler_name = handler.__class__.__name__
                logger.info("url_handler_selected", url=url, handler=handler_name)
                try:
                    content = handler.handle(url)
                    logger.info(
                        "extraction_successful",
                        url=url,
                        handler=handler_name,
                        method=content.extraction_method,
                    )
                    return content
                except Exception as e:
                    logger.error(
                        "handler_failed",
                        url=url,
                        handler=handler_name,
                        error=str(e),
                    )
                    raise ExtractionError(
                        f"Handler {handler_name} failed for {url}: {e}"
                    ) from e

        # This should never happen since FallbackHandler matches everything
        raise ExtractionError(f"No handler found for URL: {url}")
