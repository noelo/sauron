"""Custom exceptions for the content aggregator."""


class ContentAggregatorError(Exception):
    """Base exception for all content aggregator errors."""

    pass


class StorageError(ContentAggregatorError):
    """Raised when storage operations fail."""

    pass


class ExtractionError(ContentAggregatorError):
    """Raised when content extraction fails."""

    pass


class SummarizationError(ContentAggregatorError):
    """Raised when summarization fails."""

    pass


class TelegramError(ContentAggregatorError):
    """Raised when Telegram operations fail."""

    pass
