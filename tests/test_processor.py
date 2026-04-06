"""Tests for URL processor."""

import pytest
from datetime import datetime, UTC

from src.url_processor import ProcessingJob, JobStatus, URLProcessor
from src.content_extractor import ExtractedContent
from src.summarizer import SummaryResult
from src.exceptions import ExtractionError


class TestProcessingJob:
    """Test suite for ProcessingJob dataclass."""

    def test_job_creation(self):
        """Test creating a ProcessingJob."""
        job = ProcessingJob(url="https://example.com/article", message_id=123)

        assert job.url == "https://example.com/article"
        assert job.message_id == 123
        assert job.status == JobStatus.PENDING
        assert job.attempts == 0
        assert job.max_attempts == 3
        assert job.id  # Should have auto-generated UUID

    def test_job_to_dict(self):
        """Test converting job to dictionary."""
        job = ProcessingJob(url="https://example.com/article", message_id=123)

        data = job.to_dict()

        assert data["url"] == "https://example.com/article"
        assert data["message_id"] == 123
        assert data["status"] == "pending"
        assert "received_at" in data


class TestURLProcessor:
    """Test suite for URLProcessor."""

    @pytest.fixture
    def mock_settings(self, mocker):
        """Create mock settings."""
        settings = mocker.MagicMock()
        settings.telegram_channel_id = "@testchannel"
        return settings

    @pytest.fixture
    def mock_storage(self, mocker):
        """Create mock storage backend."""
        return mocker.MagicMock()

    @pytest.fixture
    def mock_extractor(self, mocker):
        """Create mock content extractor."""
        return mocker.MagicMock()

    @pytest.fixture
    def mock_summarizer(self, mocker):
        """Create mock summarizer."""
        return mocker.MagicMock()

    @pytest.fixture
    def processor(self, mock_settings, mock_storage, mock_extractor, mock_summarizer):
        """Create URLProcessor with mocked dependencies."""
        return URLProcessor(
            settings=mock_settings,
            storage=mock_storage,
            extractor=mock_extractor,
            summarizer=mock_summarizer,
        )

    def test_process_single_success(
        self, processor, mock_extractor, mock_summarizer, mock_storage, mocker
    ):
        """Test successful URL processing."""
        # Setup mocks
        mock_extractor.extract.return_value = ExtractedContent(
            url="https://example.com/article",
            title="Test Title",
            content="Test content",
            extraction_method="trafilatura",
        )

        mock_summarizer.summarize.return_value = SummaryResult(
            text="Summary text",
            model="gpt-3.5-turbo",
            generated_at=datetime.now(UTC).isoformat(),
        )

        mock_storage.list_articles.return_value = []  # No duplicates

        # Create job
        job = ProcessingJob(url="https://example.com/article", message_id=123)

        # Process
        result = processor.process_single(job)

        # Verify
        assert result.status == JobStatus.COMPLETED
        assert result.result is not None
        assert result.error is None

        # Verify storage calls
        mock_storage.save_article.assert_called_once()
        mock_storage.update_log.assert_called()

    def test_process_single_extraction_failure(
        self, processor, mock_extractor, mock_storage, mocker
    ):
        """Test handling of extraction failure."""
        # Setup mock to fail
        mock_extractor.extract.side_effect = ExtractionError("Failed to extract")
        mock_storage.list_articles.return_value = []

        job = ProcessingJob(url="https://example.com/article", message_id=123)

        result = processor.process_single(job)

        assert result.status == JobStatus.FAILED
        assert result.error is not None
        assert "Failed to extract" in result.error

    def test_process_single_duplicate_detection(self, processor, mock_storage, mocker):
        """Test that duplicate URLs are rejected."""
        # Setup mock to return existing article with same URL
        mock_storage.list_articles.return_value = [
            {"url": "https://example.com/article"}
        ]

        job = ProcessingJob(url="https://example.com/article", message_id=123)

        result = processor.process_single(job)

        assert result.status == JobStatus.FAILED
        assert "duplicate" in result.error.lower() or "Invalid" in result.error

    def test_process_single_invalid_url(self, processor, mock_storage):
        """Test that invalid URLs are rejected."""
        mock_storage.list_articles.return_value = []

        job = ProcessingJob(url="not-a-valid-url", message_id=123)

        result = processor.process_single(job)

        assert result.status == JobStatus.FAILED
        assert "Invalid" in result.error

    def test_build_article_data_structure(self, processor):
        """Test that article data has correct structure."""
        job = ProcessingJob(url="https://example.com/article", message_id=123)
        job.started_at = datetime.now(UTC)

        extracted = ExtractedContent(
            url="https://example.com/article",
            title="Test Title",
            author="Test Author",
            content="Test content here",
            extraction_method="trafilatura",
        )

        summary = SummaryResult(
            text="Test summary",
            model="gpt-3.5-turbo",
            generated_at=datetime.now(UTC).isoformat(),
            tokens_used=150,
        )

        article_data = processor._build_article_data(job, extracted, summary)

        # Verify structure
        assert article_data["id"] == job.id
        assert article_data["url"] == job.url
        assert article_data["message_id"] == job.message_id
        assert "extraction" in article_data
        assert "summary" in article_data
        assert "metadata" in article_data

        # Verify extraction data
        assert article_data["extraction"]["title"] == "Test Title"
        assert article_data["extraction"]["author"] == "Test Author"
        assert article_data["extraction"]["word_count"] == 3

        # Verify summary data
        assert article_data["summary"]["text"] == "Test summary"
        assert article_data["summary"]["tokens_used"] == 150

    def test_process_with_retry_success_on_first_attempt(self, processor, mocker):
        """Test retry logic succeeds on first attempt."""
        mock_process = mocker.patch.object(processor, "process_single")

        job = ProcessingJob(url="https://example.com/article", message_id=123)
        job.status = JobStatus.COMPLETED
        mock_process.return_value = job

        result = processor.process_with_retry(job)

        assert result.status == JobStatus.COMPLETED
        mock_process.assert_called_once()
