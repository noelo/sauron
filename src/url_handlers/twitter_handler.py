"""Handler for x.com and Twitter URLs."""

from urllib.parse import urlparse, urlunparse

import requests
import structlog
from bs4 import BeautifulSoup

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

    def _transform_url(self, url: str) -> str:
        """Transform Twitter/X URL to use fixup services."""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Replace domain based on original
        if domain in ("twitter.com", "www.twitter.com"):
            new_domain = "fxtwitter.com"
        elif domain in ("x.com", "www.x.com"):
            new_domain = "fixupx.com"
        else:
            new_domain = parsed.netloc

        # Reconstruct URL with new domain
        transformed = urlunparse(parsed._replace(netloc=new_domain))
        return transformed

    def handle(self, url: str) -> ExtractedContent:
        """Extract content from x.com or twitter.com URL.

        Fetches the content via the fixup service and extracts the og:description meta tag.
        """
        # Transform URL before processing
        transformed_url = self._transform_url(url)
        self.logger.info(
            "handling_twitter_url", original_url=url, transformed_url=transformed_url
        )

        try:
            # Perform HTTP GET to fetch the tweet content
            response = requests.get(transformed_url, timeout=10)
            response.raise_for_status()

            # Parse HTML to extract og:description
            soup = BeautifulSoup(response.text, "html.parser")
            meta_tag = soup.find("meta", property="og:description")

            if meta_tag and meta_tag.get("content"):
                tweet_content = meta_tag.get("content")
                word_count = len(tweet_content.split())

                self.logger.info(
                    "twitter_fetched_via_fixup",
                    original_url=url,
                    transformed_url=transformed_url,
                    content_length=len(tweet_content),
                    word_count=word_count,
                )

                return ExtractedContent(
                    url=url,
                    title=f"Tweet from {self._get_domain(url)}",
                    author=None,
                    content=tweet_content,
                    domain="x.com"
                    if "x.com" in self._get_domain(url)
                    else "twitter.com",
                    word_count=word_count,
                    extraction_method="twitter_fixup_handler",
                    orig_link=self._extract_github_url(tweet_content),
                )
            else:
                # Fallback: use the full HTML if og:description not found
                content = response.text
                word_count = len(content.split())
                self.logger.warning(
                    "twitter_no_og_description",
                    original_url=url,
                    transformed_url=transformed_url,
                )

                return ExtractedContent(
                    url=url,
                    title=f"Tweet from {self._get_domain(url)}",
                    author=None,
                    content=content,
                    domain="x.com"
                    if "x.com" in self._get_domain(url)
                    else "twitter.com",
                    word_count=word_count,
                    extraction_method="twitter_fixup_handler_no_meta",
                    orig_link=self._extract_github_url(content),
                )

        except requests.exceptions.RequestException as e:
            self.logger.error(
                "twitter_fetch_failed",
                original_url=url,
                transformed_url=transformed_url,
                error=str(e),
            )

            # Fallback: return basic info
            return ExtractedContent(
                url=url,
                title=f"Tweet from {self._get_domain(url)}",
                author=None,
                content=f"Could not fetch tweet content: {url}",
                domain="x.com" if "x.com" in self._get_domain(url) else "twitter.com",
                word_count=0,
                extraction_method="twitter_handler_error",
            )
