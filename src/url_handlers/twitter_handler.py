"""Handler for x.com and Twitter URLs."""

from urllib.parse import urlparse

import structlog

from src.models import ExtractedContent
from src.url_handlers.base import URLHandler

logger = structlog.get_logger(__name__)


class TwitterHandler(URLHandler):
    """Handler for x.com and twitter.com URLs."""

    DOMAINS = {"x.com", "twitter.com", "www.x.com", "www.twitter.com"}

    def can_handle(self, url: str) -> bool:
        """Check if URL is from x.com or twitter.com."""
        domain = self._get_domain(url)
        return domain in self.DOMAINS

    def handle(self, url: str) -> ExtractedContent:
        """Extract content from x.com or twitter.com URL.

        Note: Twitter/X requires special handling due to JavaScript rendering
        and anti-scraping measures. This is a basic implementation that may
        need enhancement with proper API access or browser automation.
        """
        self.logger.info("handling_twitter_url", url=url)

        # Parse URL to extract tweet ID
        parsed = urlparse(url)
        path_parts = parsed.path.strip("/").split("/")

        # Extract tweet ID if present
        tweet_id = None
        if len(path_parts) >= 3 and path_parts[1] == "status":
            tweet_id = path_parts[2]
        elif len(path_parts) >= 1 and path_parts[0] == "i" and len(path_parts) >= 2:
            # Handle /i/web/status/... URLs
            tweet_id = path_parts[-1]

        # Try to extract content - for now, we'll use the standard extractors
        # In production, you might want to use Twitter API or specialized scraping
        try:
            # For tweets, we might not be able to extract content due to anti-scraping
            # Return a placeholder indicating the tweet URL was processed
            return ExtractedContent(
                url=url,
                title=f"Tweet from x.com",
                author=None,
                content=f"Twitter/X post: {url}",
                domain="x.com" if "x.com" in self._get_domain(url) else "twitter.com",
                word_count=0,
                extraction_method="twitter_handler",
            )
        except Exception as e:
            self.logger.error("twitter_extraction_failed", url=url, error=str(e))
            # Return basic info even if extraction fails
            return ExtractedContent(
                url=url,
                title=f"Twitter/X URL",
                content=url,
                domain="x.com" if "x.com" in self._get_domain(url) else "twitter.com",
                word_count=0,
                extraction_method="twitter_handler_fallback",
            )
