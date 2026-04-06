"""Handler for reddit.com URLs."""

import re
from urllib.parse import urlparse, unquote

import requests
import structlog

from src.models import ExtractedContent
from src.url_handlers.base import URLHandler

logger = structlog.get_logger(__name__)


class RedditHandler(URLHandler):
    """Handler for reddit.com URLs."""

    DOMAINS = {"reddit.com", "www.reddit.com", "old.reddit.com", "new.reddit.com"}

    def can_handle(self, url: str) -> bool:
        """Check if URL is from reddit.com."""
        domain = self._get_domain(url)
        return domain in self.DOMAINS

    def _resolve_redirect_url(self, url: str) -> str:
        """Resolve Reddit URL by extracting Location header from 301 response.

        Reddit uses auto-generated unique URLs that redirect (301) to the actual URL.
        This method performs an HTTP GET with redirect following disabled and
        extracts the Location header to get the actual URL.

        Args:
            url: The potentially shortened/redirecting Reddit URL

        Returns:
            The resolved URL (original if no redirect or Location header not found)
        """
        try:
            headers = {
                "User-Agent": "ContentAggregator/1.0 (Bot for content aggregation)"
            }
            # Perform HEAD request with redirects disabled to capture 301
            response = requests.head(
                url, headers=headers, timeout=10, allow_redirects=False
            )

            # Check if we got a redirect (301) with Location header
            if response.status_code in (301, 302, 307, 308):
                location = response.headers.get("Location")
                if location:
                    self.logger.info(
                        "reddit_url_redirect_resolved",
                        original_url=url,
                        resolved_url=location,
                        status_code=response.status_code,
                    )
                    return location

            # If no redirect, return original URL
            return url

        except Exception as e:
            self.logger.warning(
                "reddit_redirect_resolution_failed", url=url, error=str(e)
            )
            return url

    def handle(self, url: str) -> ExtractedContent:
        """Extract content from Reddit URL.

        Handles various Reddit URL types:
        - Posts/submissions
        - Comments
        - Subreddits
        - User profiles
        """
        self.logger.info("handling_reddit_url", url=url)

        # Resolve redirect if URL is a shortened/redirecting URL
        resolved_url = self._resolve_redirect_url(url)

        parsed = urlparse(resolved_url)
        path_parts = parsed.path.strip("/").split("/")

        if len(path_parts) < 2:
            return self._handle_generic_reddit(url)

        # Check URL type
        if path_parts[0] == "r" and len(path_parts) >= 3:
            return self._handle_subreddit_post(url, path_parts)
        elif path_parts[0] == "u" or path_parts[0] == "user":
            return self._handle_user_profile(url, path_parts)
        elif path_parts[0] == "r":
            return self._handle_subreddit(url, path_parts)
        else:
            return self._handle_generic_reddit(url)

    def _handle_generic_reddit(self, url: str) -> ExtractedContent:
        """Handle generic Reddit URLs."""
        return ExtractedContent(
            url=url,
            title="Reddit",
            author=None,
            content=f"Reddit URL: {url}",
            domain="reddit.com",
            word_count=3,
            extraction_method="reddit_handler",
        )

    def _handle_subreddit_post(self, url: str, path_parts: list) -> ExtractedContent:
        """Handle Reddit posts with comments."""
        subreddit = path_parts[1]
        post_id = None
        post_title_slug = None

        # Extract post ID from URL
        # Reddit URLs: /r/subreddit/comments/post_id/title_slug/
        if len(path_parts) >= 4 and path_parts[2] == "comments":
            post_id = path_parts[3]
            if len(path_parts) >= 5:
                post_title_slug = path_parts[4]

        if post_id:
            # Try to fetch via Reddit's JSON API
            return self._fetch_post_via_api(url, subreddit, post_id, post_title_slug)

        # Fallback for malformed URLs
        return ExtractedContent(
            url=url,
            title=f"r/{subreddit} Post",
            author=None,
            content=f"Reddit post in r/{subreddit}: {url}",
            domain="reddit.com",
            word_count=5,
            extraction_method="reddit_handler_post",
        )

    def _fetch_post_via_api(
        self, url: str, subreddit: str, post_id: str, title_slug: str = None
    ) -> ExtractedContent:
        """Fetch Reddit post details using Reddit's JSON API."""
        json_url = f"https://www.reddit.com/comments/{post_id}.json"

        try:
            headers = {
                "User-Agent": "ContentAggregator/1.0 (Bot for content aggregation)"
            }
            response = requests.get(json_url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()

            if not data or len(data) == 0:
                raise ValueError("Empty response from Reddit API")

            # First element is the post
            post_data = data[0]["data"]["children"][0]["data"]

            title = post_data.get("title", "Reddit Post")
            author = post_data.get("author", "unknown")
            selftext = post_data.get("selftext", "")
            url_overridden = post_data.get("url_overridden_by_dest", "")
            subreddit_name = post_data.get("subreddit", subreddit)
            score = post_data.get("score", 0)
            num_comments = post_data.get("num_comments", 0)

            # Build content
            content_parts = [f"Posted by u/{author} in r/{subreddit_name}"]
            content_parts.append(f"Score: {score} | Comments: {num_comments}")
            content_parts.append("")
            content_parts.append(title)

            if selftext:
                content_parts.append("")
                content_parts.append(selftext)
            elif url_overridden:
                content_parts.append("")
                content_parts.append(f"Linked URL: {url_overridden}")

            # Add top comments if available
            if len(data) > 1:
                comments_data = data[1]["data"]["children"][:5]  # Top 5 comments
                if comments_data:
                    content_parts.append("")
                    content_parts.append("Top Comments:")
                    for comment in comments_data:
                        if comment.get("kind") == "t1":  # t1 is comment type
                            comment_data = comment.get("data", {})
                            comment_author = comment_data.get("author", "unknown")
                            comment_body = comment_data.get("body", "")
                            if comment_body:
                                content_parts.append(
                                    f"  u/{comment_author}: {comment_body[:500]}"
                                )

            content = "\n".join(content_parts)

            return ExtractedContent(
                url=url,
                title=title,
                author=f"u/{author}",
                content=content,
                domain="reddit.com",
                word_count=len(content.split()),
                extraction_method="reddit_handler_api",
            )

        except Exception as e:
            self.logger.warning("reddit_api_fetch_failed", url=url, error=str(e))
            # Fallback to basic extraction
            return ExtractedContent(
                url=url,
                title=f"r/{subreddit} Post ({post_id})",
                author=None,
                content=f"Reddit post in r/{subreddit}: {url}",
                domain="reddit.com",
                word_count=5,
                extraction_method="reddit_handler_fallback",
            )

    def _handle_subreddit(self, url: str, path_parts: list) -> ExtractedContent:
        """Handle subreddit main pages."""
        subreddit = path_parts[1]

        return ExtractedContent(
            url=url,
            title=f"r/{subreddit}",
            author=None,
            content=f"Reddit subreddit: r/{subreddit}\n\nURL: {url}",
            domain="reddit.com",
            word_count=4,
            extraction_method="reddit_handler_subreddit",
        )

    def _handle_user_profile(self, url: str, path_parts: list) -> ExtractedContent:
        """Handle user profile URLs."""
        username = path_parts[1] if len(path_parts) > 1 else "unknown"

        return ExtractedContent(
            url=url,
            title=f"u/{username}",
            author=None,
            content=f"Reddit user profile: u/{username}\n\nURL: {url}",
            domain="reddit.com",
            word_count=5,
            extraction_method="reddit_handler_user",
        )
