"""URL handlers for different domains."""

from src.url_handlers.base import URLHandler, FallbackHandler
from src.url_handlers.twitter_handler import TwitterHandler
from src.url_handlers.github_handler import GitHubHandler
from src.url_handlers.reddit_handler import RedditHandler

__all__ = [
    "URLHandler",
    "FallbackHandler",
    "TwitterHandler",
    "GitHubHandler",
    "RedditHandler",
]
