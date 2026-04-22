"""Data models for content extraction."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse


@dataclass
class ExtractedContent:
    """Data class for extracted article content."""

    url: str
    title: Optional[str] = None
    author: Optional[str] = None
    publish_date: Optional[str] = None
    content: Optional[str] = None
    domain: Optional[str] = None
    word_count: int = 0
    extraction_method: str = ""
    extraction_timestamp: str = ""
    is_paywalled: bool = False
    orig_link: Optional[str] = None

    def __post_init__(self):
        if not self.extraction_timestamp:
            self.extraction_timestamp = datetime.now(timezone.utc).isoformat()
        if not self.domain and self.url:
            self.domain = urlparse(self.url).netloc
        if self.content:
            self.word_count = len(self.content.split())
