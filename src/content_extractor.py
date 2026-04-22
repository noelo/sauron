"""Content extraction from web articles."""

import json
import re
from abc import ABC, abstractmethod
from typing import List, Optional
from urllib.parse import urlparse

import requests
import structlog
import trafilatura
from newspaper import Article as NewspaperArticle

from src.exceptions import ExtractionError
from src.models import ExtractedContent

logger = structlog.get_logger(__name__)


def _extract_github_url(text: str) -> Optional[str]:
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

            data = json.loads(extracted)

            content = ExtractedContent(
                url=url,
                title=data.get("title"),
                author=data.get("author"),
                publish_date=data.get("date"),
                content=data.get("text", ""),
                extraction_method="trafilatura",
            )

            # Check for GitHub URL in extracted content
            github_url = _extract_github_url(content.content)
            if github_url:
                content.orig_link = github_url
                logger.info(
                    "found_github_url_in_content", url=url, github_url=github_url
                )

            return content

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

            content = ExtractedContent(
                url=url,
                title=article.title,
                author=", ".join(article.authors) if article.authors else None,
                publish_date=publish_date,
                content=article.text,
                extraction_method="newspaper3k",
            )

            # Check for GitHub URL in extracted content
            github_url = _extract_github_url(content.content)
            if github_url:
                content.orig_link = github_url
                logger.info(
                    "found_github_url_in_content", url=url, github_url=github_url
                )

            return content

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
                    # Console output: Print first 100 chars of extracted text
                    text_preview = content.content[:100] if content.content else ""
                    if len(content.content) > 100:
                        text_preview += "..."
                    print(
                        f"📄 Extracted text preview ({len(content.content)} chars): {text_preview}"
                    )
                    logger.info(
                        "extraction_successful",
                        url=url,
                        handler=handler_name,
                        method=content.extraction_method,
                        content_length=len(content.content) if content.content else 0,
                    )
                    return content
                except Exception as e:
                    # Console logging: Print retrieval error
                    print(f"❌ Extraction failed for {url}: {str(e)}")
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
