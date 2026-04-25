"""Handler for x.com and Twitter URLs."""

import re
from typing import Any, Callable
from urllib.parse import urlparse

import requests
import structlog

from src.models import ExtractedContent
from src.url_handlers.base import URLHandler

logger = structlog.get_logger(__name__)

_github_pattern = re.compile(
    r"https?://(?:www\.)?github\.com/[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+(?:/[a-zA-Z0-9_-]+)*"
)


class TwitterHandler(URLHandler):
    """Handler for x.com and twitter.com URLs."""

    DOMAINS = {"x.com", "twitter.com", "www.x.com", "www.twitter.com"}
    API_BASE = "https://api.fxtwitter.com/2/thread/"

    def __init__(self, github_urls_cb: Callable[[list[str]], None] | None = None):
        super().__init__()
        self._github_urls_cb = github_urls_cb

    def can_handle(self, url: str) -> bool:
        """Check if URL is from x.com or twitter.com."""
        domain = self._get_domain(url)
        return domain in self.DOMAINS

    def _extract_tweet_id(self, url: str) -> str:
        """Extract the tweet ID from a Twitter/X URL.

        The tweet ID is the numeric segment after '/status/' in the URL path.
        """
        parsed = urlparse(url)
        parts = parsed.path.strip("/").split("/")
        for i, part in enumerate(parts):
            if part == "status" and i + 1 < len(parts):
                return parts[i + 1]
        raise ValueError(f"Could not extract tweet ID from URL: {url}")

    def _build_api_url(self, tweet_id: str) -> str:
        """Build the API URL for fetching tweet data."""
        return f"{self.API_BASE}{tweet_id}"

    def _extract_content_from_json(
        self, data: dict[str, Any]
    ) -> tuple[str, str | None, list[str]]:
        """Extract tweet content, author and GitHub URLs from API JSON response.

        Returns tuple of (combined_content, author_name, github_urls).
        """
        status = data.get("status", {})
        tweet_text = status.get("text", "")
        author_name = status.get("author", {}).get("name")

        # Add thread tweets if present (skip first element - it's a copy of status)
        thread = data.get("thread", [])
        thread_texts = []
        if len(thread) > 1:
            thread_texts = [t.get("text", "") for t in thread[1:] if t.get("text")]
            combined_text = f"{tweet_text}\n\n--- Thread ---\n" + "\n\n".join(
                thread_texts
            )
        else:
            combined_text = tweet_text

        # Extract all GitHub URLs from tweet and thread content
        github_urls = []
        full_text = f"{tweet_text}\n\n{'\n\n'.join(thread_texts)}"
        found = _github_pattern.findall(full_text)
        seen = set()
        for url in found:
            normalized = url.rstrip("/")
            if normalized not in seen:
                seen.add(normalized)
                github_urls.append(url)

        if self._github_urls_cb and github_urls:
            self._github_urls_cb(github_urls)
            self.logger.info(
                "twitter_github_urls_found",
                count=len(github_urls),
                urls=github_urls,
            )

        return combined_text, author_name, github_urls

    def handle(self, url: str) -> ExtractedContent:
        """Extract content from x.com or twitter.com URL.

        Fetches tweet content via the fxtwitter JSON API using the tweet ID.
        """
        tweet_id = self._extract_tweet_id(url)
        api_url = self._build_api_url(tweet_id)
        domain = "x.com" if "x.com" in self._get_domain(url) else "twitter.com"

        self.logger.info(
            "handling_twitter_url", original_url=url, api_url=api_url, tweet_id=tweet_id
        )

        try:
            response = requests.get(api_url, timeout=10)
            response.raise_for_status()
            data = response.json()

            tweet_content, author_name, github_urls = self._extract_content_from_json(
                data
            )

            self.logger.info(
                "twitter_fetched_via_api",
                original_url=url,
                tweet_id=tweet_id,
                content_length=len(tweet_content),
            )

            return ExtractedContent(
                url=url,
                title=f"Tweet from {domain}",
                author=author_name,
                content=tweet_content,
                domain=domain,
                extraction_method="twitter_json_api",
                orig_link=github_urls[0] if github_urls else None,
            )

        except requests.exceptions.RequestException as e:
            self.logger.error(
                "twitter_fetch_failed",
                original_url=url,
                api_url=api_url,
                error=str(e),
            )

            return ExtractedContent(
                url=url,
                title=f"Tweet from {domain}",
                author=None,
                content=f"Could not fetch tweet content: {url}",
                domain=domain,
                extraction_method="twitter_json_api_error",
            )
