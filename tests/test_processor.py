"""Tests for URL processor."""

import asyncio
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


class TestURLProcessorQueue:
    """Test suite for URLProcessor queue-based API."""

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

    @pytest.mark.asyncio
    async def test_submit_returns_job_id(self, processor, mock_storage):
        """Test submitting a job returns the job ID."""
        mock_storage.list_articles.return_value = []
        job = ProcessingJob(url="https://example.com/article", message_id=123)

        job_id = await processor.submit(job)

        assert job_id == job.id
        assert processor.get_job_status(job_id) is not None

    @pytest.mark.asyncio
    async def test_submit_adds_job_to_queue(self, processor, mock_storage):
        """Test that submit adds job to the queue."""
        mock_storage.list_articles.return_value = []
        job = ProcessingJob(url="https://example.com/article", message_id=123)

        await processor.submit(job)

        assert processor._job_queue.qsize() == 1

    @pytest.mark.asyncio
    async def test_submit_multiple_jobs(self, processor, mock_storage):
        """Test submitting multiple jobs."""
        mock_storage.list_articles.return_value = []
        jobs = [
            ProcessingJob(url=f"https://example.com/article{i}", message_id=i)
            for i in range(5)
        ]

        for job in jobs:
            await processor.submit(job)

        assert processor._job_queue.qsize() == 5

    @pytest.mark.asyncio
    async def test_start_creates_workers(self, processor):
        """Test starting creates worker tasks."""
        await processor.start()

        assert processor._running is True
        assert len(processor._workers) == 1

    @pytest.mark.asyncio
    async def test_start_idempotent(self, processor):
        """Test that starting twice does nothing."""
        await processor.start()
        initial_workers = len(processor._workers)

        await processor.start()

        assert len(processor._workers) == initial_workers

    @pytest.mark.asyncio
    async def test_stop_cancels_workers(self, processor):
        """Test stopping cancels workers."""
        await processor.start()
        await processor.stop()

        assert processor._running is False
        assert len(processor._workers) == 0

    @pytest.mark.asyncio
    async def test_get_job_status_returns_none_for_unknown(self, processor):
        """Test getting status of unknown job returns None."""
        result = processor.get_job_status("nonexistent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_job_status_returns_job_after_submit(
        self, processor, mock_storage
    ):
        """Test getting status of submitted job returns the job."""
        mock_storage.list_articles.return_value = []
        job = ProcessingJob(url="https://example.com/article", message_id=123)
        job_id = await processor.submit(job)

        result = processor.get_job_status(job_id)

        assert result is not None
        assert result.id == job.id
        assert result.url == job.url

    @pytest.mark.asyncio
    async def test_worker_processes_job(
        self, processor, mock_extractor, mock_summarizer, mock_storage, mocker
    ):
        """Test worker processes jobs from queue."""
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

        mock_storage.list_articles.return_value = []

        job = ProcessingJob(url="https://example.com/article", message_id=123)
        await processor.submit(job)
        await processor.start()

        # Wait for processing with timeout
        for _ in range(50):
            await asyncio.sleep(0.1)
            result = processor.get_job_status(job.id)
            if result and result.status in (JobStatus.COMPLETED, JobStatus.FAILED):
                break
        else:
            await processor.stop()
            assert False, "Job did not complete in time"

        await processor.stop()

        assert result.status == JobStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_worker_handles_job_failure(
        self, processor, mock_extractor, mock_storage, mocker
    ):
        """Test worker handles failed jobs gracefully."""
        mock_extractor.extract.side_effect = ExtractionError("Failed to extract")
        mock_storage.list_articles.return_value = []

        job = ProcessingJob(url="https://example.com/article", message_id=123)
        await processor.submit(job)
        await processor.start()

        # Wait for processing with timeout
        for _ in range(50):
            await asyncio.sleep(0.1)
            result = processor.get_job_status(job.id)
            if result and result.status == JobStatus.FAILED:
                break
        else:
            await processor.stop()
            assert False, "Job did not fail in time"

        await processor.stop()

        assert result.status == JobStatus.FAILED
        assert "Failed to extract" in result.error

    @pytest.mark.asyncio
    async def test_custom_workers_count(
        self, mock_settings, mock_storage, mock_extractor, mock_summarizer
    ):
        """Test creating processor with custom number of workers."""
        processor = URLProcessor(
            settings=mock_settings,
            storage=mock_storage,
            extractor=mock_extractor,
            summarizer=mock_summarizer,
            workers=3,
        )

        await processor.start()

        assert len(processor._workers) == 3
        await processor.stop()

    @pytest.mark.asyncio
    async def test_custom_queue_size(
        self, mock_settings, mock_storage, mock_extractor, mock_summarizer
    ):
        """Test creating processor with custom queue size."""
        processor = URLProcessor(
            settings=mock_settings,
            storage=mock_storage,
            extractor=mock_extractor,
            summarizer=mock_summarizer,
            max_queue_size=10,
        )

        assert processor._job_queue.maxsize == 10

    @pytest.mark.asyncio
    async def test_worker_submits_github_child_jobs(
        self, processor, mock_extractor, mock_summarizer, mock_storage, mocker
    ):
        """Test worker submits GitHub URLs found in content as child jobs."""
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

        mock_storage.list_articles.return_value = []

        job = ProcessingJob(url="https://example.com/article", message_id=123)
        await processor.submit(job)

        # Inject GitHub URLs via process_with_retry hook to simulate callback
        original_pwr = processor.process_with_retry

        def patched_pwr(job):
            processor._found_github_urls = [
                "https://github.com/owner/repo",
                "https://github.com/user/project/issues",
            ]
            return original_pwr(job)

        mocker.patch.object(processor, "process_with_retry", side_effect=patched_pwr)

        await processor.start()

        # Wait for parent job to complete
        for _ in range(50):
            await asyncio.sleep(0.1)
            result = processor.get_job_status(job.id)
            if result and result.status == JobStatus.COMPLETED:
                break
        else:
            await processor.stop()
            assert False, "Parent job did not complete in time"

        # Wait for child jobs to be submitted
        for _ in range(20):
            await asyncio.sleep(0.1)
            if processor._job_queue.qsize() >= 2:
                break
        else:
            await processor.stop()
            assert False, "Child jobs were not submitted in time"

        await processor.stop()

        # Verify child jobs were submitted
        child_jobs = [
            j for j in processor._job_results.values() if j.parent_job_id == job.id
        ]
        assert len(child_jobs) == 2
        assert "https://github.com/owner/repo" in [j.url for j in child_jobs]
        assert "https://github.com/user/project/issues" in [j.url for j in child_jobs]

    @pytest.mark.asyncio
    async def test_worker_does_not_submit_child_jobs_on_failure(
        self, processor, mock_extractor, mock_storage, mocker
    ):
        """Test worker does not submit child jobs when parent job fails."""
        mock_extractor.extract.side_effect = ExtractionError("Failed to extract")
        mock_storage.list_articles.return_value = []

        job = ProcessingJob(url="https://example.com/article", message_id=123)
        await processor.submit(job)

        processor._found_github_urls = ["https://github.com/owner/repo"]

        await processor.start()

        # Wait for processing with timeout
        for _ in range(50):
            await asyncio.sleep(0.1)
            result = processor.get_job_status(job.id)
            if result and result.status == JobStatus.FAILED:
                break
        else:
            await processor.stop()
            assert False, "Job did not fail in time"

        await asyncio.sleep(0.2)

        # Verify no child jobs were submitted
        child_jobs = [
            j for j in processor._job_results.values() if j.parent_job_id == job.id
        ]
        assert len(child_jobs) == 0

        await processor.stop()
