"""Handler for reddit.com URLs using PRAW library."""

import re
from typing import Optional
from urllib.parse import urlparse, unquote

import praw
import praw.exceptions
import requests
import structlog

from config.settings import get_settings
from src.exceptions import ExtractionError
from src.models import ExtractedContent
from src.url_handlers.base import URLHandler

logger = structlog.get_logger(__name__)


class RedditHandler(URLHandler):
    """Handler for reddit.com URLs using PRAW library."""

    DOMAINS = {"reddit.com", "www.reddit.com", "old.reddit.com", "new.reddit.com"}

    def __init__(self):
        self.logger = logger
        self._reddit_client: Optional[praw.Reddit] = None
        self._settings = None

    @property
    def reddit_client(self) -> praw.Reddit:
        """Lazy initialization of Reddit client."""
        if self._reddit_client is None:
            self._settings = get_settings()

            if self._settings.reddit_client_id and self._settings.reddit_client_secret:
                # Use authenticated API if credentials are provided
                self._reddit_client = praw.Reddit(
                    client_id=self._settings.reddit_client_id,
                    client_secret=self._settings.reddit_client_secret,
                    user_agent=self._settings.reddit_user_agent,
                )
                print(f"🔐 Using authenticated Reddit API")
                self.logger.info("reddit_initialized_authenticated")
            else:
                # Use read-only mode (unauthenticated)
                self._reddit_client = praw.Reddit(
                    client_id="",
                    client_secret="",
                    user_agent=self._settings.reddit_user_agent,
                )
                print(f"🔓 Using read-only Reddit API")
                self.logger.info("reddit_initialized_read_only")

        return self._reddit_client

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
            # Use browser-like headers to avoid bot detection
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
            }
            # Use GET request instead of HEAD - Reddit blocks HEAD requests
            print(f"🌐 Resolving Reddit URL: {url}")
            response = requests.get(
                url, headers=headers, timeout=10, allow_redirects=False
            )

            # Check for 403 Forbidden - Reddit blocks programmatic access
            if response.status_code == 403:
                print(f"❌ Reddit blocked the request (403 Forbidden): {url}")
                self.logger.error("reddit_access_blocked", url=url, status_code=403)
                raise ExtractionError(
                    f"Reddit blocked access to URL (403 Forbidden): {url}"
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

        except ExtractionError:
            # Re-raise ExtractionError (e.g., 403 Forbidden) - don't fall back
            raise
        except Exception as e:
            # For other errors, raise ExtractionError instead of falling back
            self.logger.error(
                "reddit_redirect_resolution_failed", url=url, error=str(e)
            )
            raise ExtractionError(f"Failed to resolve Reddit URL: {url} - {e}") from e

    def _extract_post_id_from_url(self, url: str) -> Optional[str]:
        """Extract Reddit post ID from URL."""
        # Handle various Reddit URL formats
        # /r/subreddit/comments/POST_ID/...
        # /comments/POST_ID/...
        patterns = [
            r"/r/[^/]+/comments/([a-zA-Z0-9]+)",
            r"/comments/([a-zA-Z0-9]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        return None

    def handle(self, url: str) -> ExtractedContent:
        """Extract content from Reddit URL using PRAW.

        Handles various Reddit URL types:
        - Posts/submissions
        - Comments
        - Subreddits
        - User profiles
        """
        self.logger.info("handling_reddit_url", url=url)
        print(f"🔗 Processing Reddit URL: {url}")

        # Resolve redirect if URL is a shortened/redirecting URL
        resolved_url = self._resolve_redirect_url(url)

        # Console output: Show what was extracted from the initial URL
        if resolved_url != url:
            print(f"   Resolved to: {resolved_url}")
            self.logger.info(
                "reddit_url_resolved",
                original_url=url,
                resolved_url=resolved_url,
            )

        parsed = urlparse(resolved_url)
        path_parts = parsed.path.strip("/").split("/")

        if len(path_parts) < 2:
            return self._handle_generic_reddit(resolved_url)

        # Check URL type - pass resolved_url to handlers
        if path_parts[0] == "r" and len(path_parts) >= 3:
            return self._handle_subreddit_post(resolved_url, path_parts)
        elif path_parts[0] == "u" or path_parts[0] == "user":
            return self._handle_user_profile(resolved_url, path_parts)
        elif path_parts[0] == "r":
            return self._handle_subreddit(resolved_url, path_parts)
        else:
            return self._handle_generic_reddit(resolved_url)

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
        """Handle Reddit posts with comments using PRAW."""
        subreddit_name = path_parts[1]
        post_id = self._extract_post_id_from_url(url)

        if post_id:
            # Try to fetch via PRAW
            return self._fetch_post_via_praw(url, subreddit_name, post_id)

        # Fallback for malformed URLs
        return ExtractedContent(
            url=url,
            title=f"r/{subreddit_name} Post",
            author=None,
            content=f"Reddit post in r/{subreddit_name}: {url}",
            domain="reddit.com",
            word_count=5,
            extraction_method="reddit_handler_post",
        )

    def _fetch_post_via_praw(
        self, url: str, subreddit_name: str, post_id: str
    ) -> ExtractedContent:
        """Fetch Reddit post details using PRAW library."""
        try:
            print(f"   Fetching post via PRAW API...")
            self.logger.info(
                "reddit_fetching_via_praw",
                post_id=post_id,
                subreddit=subreddit_name,
            )

            # Fetch the submission using PRAW
            submission = self.reddit_client.submission(id=post_id)

            # Access attributes to force API call
            title = submission.title
            author = str(submission.author) if submission.author else "[deleted]"
            selftext = submission.selftext
            score = submission.score
            num_comments = submission.num_comments
            subreddit = str(submission.subreddit)
            created_utc = submission.created_utc

            print(f'   ✓ Fetched: "{title[:60]}{"..." if len(title) > 60 else ""}"')
            print(f"   Author: u/{author} | Score: {score} | Comments: {num_comments}")

            # Build content
            content_parts = [
                f"Posted by u/{author} in r/{subreddit}",
                f"Score: {score} | Comments: {num_comments}",
                "",
                title,
            ]

            if selftext:
                content_parts.append("")
                content_parts.append(selftext)
            elif submission.url and submission.url != url:
                content_parts.append("")
                content_parts.append(f"Linked URL: {submission.url}")

            # Try to fetch top comments
            try:
                submission.comments.replace_more(limit=0)  # Remove "load more" comments
                top_comments = list(submission.comments)[:5]  # Top 5 comments

                if top_comments:
                    content_parts.append("")
                    content_parts.append("Top Comments:")
                    for comment in top_comments:
                        if hasattr(comment, "body"):
                            comment_author = (
                                str(comment.author) if comment.author else "[deleted]"
                            )
                            comment_body = (
                                comment.body[:500]
                                if len(comment.body) > 500
                                else comment.body
                            )
                            content_parts.append(
                                f"  u/{comment_author}: {comment_body}"
                            )
            except Exception as e:
                self.logger.warning("reddit_comments_fetch_failed", error=str(e))
                print(f"   ⚠ Could not fetch comments: {e}")

            content = "\n".join(content_parts)

            self.logger.info(
                "reddit_praw_fetch_successful",
                post_id=post_id,
                title=title,
                author=author,
            )

            return ExtractedContent(
                url=url,
                title=title,
                author=f"u/{author}",
                content=content,
                domain="reddit.com",
                word_count=len(content.split()),
                extraction_method="reddit_praw",
                orig_link=self._extract_github_url(content),
            )

        except praw.exceptions.PRAWException as e:
            self.logger.error("reddit_praw_error", post_id=post_id, error=str(e))
            print(f"   ❌ PRAW error: {e}")
            raise ExtractionError(f"Reddit API error for post {post_id}: {e}") from e
        except Exception as e:
            self.logger.error("reddit_praw_fetch_failed", post_id=post_id, error=str(e))
            print(f"   ❌ Failed to fetch via PRAW: {e}")
            raise ExtractionError(f"Failed to fetch Reddit post {post_id}: {e}") from e

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
