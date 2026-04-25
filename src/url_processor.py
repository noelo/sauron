"""URL processing pipeline with Job abstraction."""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

import structlog

from config.settings import Settings
from src.content_extractor import ExtractedContent, WebContentExtractor
from src.exceptions import ExtractionError, StorageError, SummarizationError
from src.storage import JSONStorageBackend
from src.summarizer import OpenAISummarizer, create_summarizer

logger = structlog.get_logger(__name__)


class JobStatus(Enum):
    """Status of a processing job."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ProcessingJob:
    """
    Abstraction for a URL processing job.

    This dataclass represents a single URL to be processed through the pipeline.
    Designed to be queue-compatible for future migration.
    """

    url: str
    message_id: int
    received_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: JobStatus = field(default=JobStatus.PENDING)
    attempts: int = 0
    max_attempts: int = 3
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    parent_job_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert job to dictionary for serialization."""
        return {
            "id": self.id,
            "url": self.url,
            "message_id": self.message_id,
            "received_at": self.received_at.isoformat() if self.received_at else None,
            "status": self.status.value,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
        }


class URLProcessor:
    """
    Orchestrates the content processing pipeline.

    Processes URLs sequentially (one at a time) with retry logic.
    Designed to be replaceable with a queue-based processor in the future.
    """

    def __init__(
        self,
        settings: Settings,
        storage: JSONStorageBackend,
        extractor: Optional[WebContentExtractor] = None,
        summarizer: Optional[OpenAISummarizer] = None,
        max_queue_size: int = 100,
        workers: int = 1,
    ):
        self.settings = settings
        self.storage = storage
        self._found_github_urls: list[str] = []
        self._current_job_id: str = ""
        self.extractor = extractor or WebContentExtractor(
            github_urls_cb=self._on_github_urls_found
        )
        self.summarizer = summarizer or create_summarizer(settings)
        self.logger = structlog.get_logger(__name__)
        self._job_queue = asyncio.Queue(maxsize=max_queue_size)
        self._workers = []
        self._running = False
        self._num_workers = workers
        self._job_results: Dict[str, ProcessingJob] = {}

    def _on_github_urls_found(self, urls: list[str]) -> None:
        """Callback from TwitterHandler when GitHub URLs are found in tweet content."""
        self._found_github_urls.extend(urls)

    def process_single(self, job: ProcessingJob) -> ProcessingJob:
        """Process a single URL through the complete pipeline."""
        self.logger.info(
            "starting_job_processing",
            job_id=job.id,
            url=job.url,
            message_id=job.message_id,
        )

        job.status = JobStatus.PROCESSING
        job.started_at = datetime.now(timezone.utc)
        job.attempts += 1

        try:
            # Step 1: Validate
            print(f"🔍 [{job.id[:8]}] Step 1/4: Validating URL: {job.url}")
            logger.info(
                "processing_step_validate",
                job_id=job.id,
                url=job.url,
                step=1,
                total_steps=4,
            )
            if not self._validate_url(job.url):
                raise ValueError(f"Invalid or duplicate URL: {job.url}")

            # Step 2: Extract content
            print(f"📥 [{job.id[:8]}] Step 2/4: Extracting content from: {job.url}")
            logger.info(
                "processing_step_extract",
                job_id=job.id,
                url=job.url,
                step=2,
                total_steps=4,
            )
            self.logger.info("extracting_content", job_id=job.id, url=job.url)
            extracted = self.extractor.extract(job.url)

            # Step 3: Generate summary
            print(
                f"🤖 [{job.id[:8]}] Step 3/4: Generating summary for: {extracted.title or 'Untitled'}"
            )
            logger.info(
                "processing_step_summarize",
                job_id=job.id,
                url=job.url,
                step=3,
                total_steps=4,
                title=extracted.title,
            )
            self.logger.info("generating_summary", job_id=job.id, title=extracted.title)
            summary = self.summarizer.summarize(
                title=extracted.title or "Untitled", content=extracted.content or ""
            )

            # Step 4: Store results
            print(
                f"💾 [{job.id[:8]}] Step 4/4: Storing results for article: {extracted.title or 'Untitled'}"
            )
            logger.info(
                "processing_step_store",
                job_id=job.id,
                url=job.url,
                step=4,
                total_steps=4,
            )
            article_data = self._build_article_data(job, extracted, summary)
            self.storage.save_article(article_data)

            # Update job
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.now(timezone.utc)
            job.result = article_data

            # Update processing log
            self.storage.update_log(
                {
                    "url": job.url,
                    "message_id": job.message_id,
                    "status": "completed",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

            self.logger.info(
                "job_completed",
                job_id=job.id,
                url=job.url,
                duration_seconds=(job.completed_at - job.started_at).total_seconds(),
            )

        except Exception as e:
            self.logger.error(
                "job_failed",
                job_id=job.id,
                url=job.url,
                error=str(e),
                attempt=job.attempts,
            )

            job.status = JobStatus.FAILED
            job.error = str(e)
            job.completed_at = datetime.now(timezone.utc)

            # Update processing log
            self.storage.update_log(
                {
                    "url": job.url,
                    "message_id": job.message_id,
                    "status": "failed",
                    "error": str(e),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

        return job

    def _validate_url(self, url: str) -> bool:
        """Validate URL and check for duplicates."""
        if not url or not url.startswith(("http://", "https://")):
            return False

        recent_articles = self.storage.list_articles(limit=100)
        for article in recent_articles:
            if article.get("url") == url:
                self.logger.warning("duplicate_url_detected", url=url)
                return False

        return True

    def _build_article_data(
        self, job: ProcessingJob, extracted: ExtractedContent, summary
    ) -> Dict[str, Any]:
        """Build the final article data structure."""
        processing_duration = 0.0
        if job.started_at and job.completed_at:
            processing_duration = (job.completed_at - job.started_at).total_seconds()

        return {
            "id": job.id,
            "url": job.url,
            "source_channel": self.settings.telegram_channel_id,
            "message_id": job.message_id,
            "received_at": job.received_at.isoformat(),
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "status": "completed",
            "extraction": {
                "title": extracted.title,
                "author": extracted.author,
                "publish_date": extracted.publish_date,
                "content": extracted.content,
                "domain": extracted.domain,
                "word_count": extracted.word_count,
            },
            "summary": {
                "text": summary.text,
                "model": summary.model,
                "generated_at": summary.generated_at,
                "tokens_used": summary.tokens_used,
                "generation_time_seconds": summary.generation_time_seconds,
            },
            "metadata": {
                "extraction_library": extracted.extraction_method,
                "processing_duration_seconds": processing_duration,
                "attempts": job.attempts,
            },
        }

    def process_with_retry(self, job: ProcessingJob) -> ProcessingJob:
        """Process a job with automatic retry on failure."""
        while job.attempts < job.max_attempts:
            job = self.process_single(job)

            if job.status == JobStatus.COMPLETED:
                return job

            if job.attempts < job.max_attempts:
                wait_time = 2**job.attempts
                self.logger.info(
                    "retrying_job",
                    job_id=job.id,
                    attempt=job.attempts,
                    wait_seconds=wait_time,
                )
                time.sleep(wait_time)
                job.status = JobStatus.PENDING

        return job

    async def submit(self, job: ProcessingJob) -> str:
        """Submit a job for async processing. Returns job ID."""
        await self._job_queue.put(job)
        self._job_results[job.id] = job
        self.logger.info(
            "job_submitted",
            job_id=job.id,
            url=job.url,
            queue_size=self._job_queue.qsize(),
        )
        return job.id

    async def _worker_loop(self, worker_id: int) -> None:
        """Background worker that processes jobs from the queue."""
        self.logger.info("worker_started", worker_id=worker_id)
        while self._running:
            try:
                job = await asyncio.wait_for(self._job_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            self.logger.info(
                "worker_processing_job",
                worker_id=worker_id,
                job_id=job.id,
                url=job.url,
            )

            self._current_job_id = job.id
            self._found_github_urls.clear()

            try:
                result = self.process_with_retry(job)
                self._job_results[job.id] = result

                if result.status == JobStatus.COMPLETED:
                    self.logger.info(
                        "worker_job_completed",
                        worker_id=worker_id,
                        job_id=job.id,
                        url=job.url,
                    )

                    # Submit GitHub URLs found in content as child jobs
                    for github_url in self._found_github_urls:
                        child_job = ProcessingJob(
                            url=github_url,
                            message_id=job.message_id,
                            parent_job_id=job.id,
                        )
                        await self.submit(child_job)

                else:
                    self.logger.error(
                        "worker_job_failed",
                        worker_id=worker_id,
                        job_id=job.id,
                        url=job.url,
                        error=result.error,
                    )
            except Exception as e:
                self.logger.error(
                    "worker_unexpected_error",
                    worker_id=worker_id,
                    job_id=job.id,
                    error=str(e),
                )
            finally:
                self._job_queue.task_done()

        self.logger.info("worker_stopped", worker_id=worker_id)

    async def start(self) -> None:
        """Start background worker tasks."""
        if self._running:
            return

        self._running = True
        for i in range(self._num_workers):
            task = asyncio.create_task(self._worker_loop(i))
            self._workers.append(task)

        self.logger.info("processor_started", num_workers=self._num_workers)

    async def stop(self) -> None:
        """Stop background worker tasks."""
        self._running = False

        for worker in self._workers:
            worker.cancel()

        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)

        self._workers.clear()
        self.logger.info("processor_stopped")

    def get_job_status(self, job_id: str) -> Optional[ProcessingJob]:
        """Get the current status of a submitted job by ID."""
        return self._job_results.get(job_id)
