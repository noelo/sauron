#!/usr/bin/env python3
"""
Content Aggregator - Main Entry Point

AI-powered content aggregator that receives URLs from Telegram,
extracts and summarizes content, and stores results in JSON files.
"""

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

import structlog

from config.settings import get_settings
from src.storage import JSONStorageBackend
from src.url_processor import URLProcessor
from src.telegram_listener import TelegramListener

logging.basicConfig(level=logging.DEBUG)

# Configure structured logging
logging.getLogger().setLevel(logging.DEBUG)
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.dev.ConsoleRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


class ContentAggregator:
    """Main application class."""

    def __init__(self, batch: bool = False, batch_timeout: int = 60):
        self.settings = get_settings()
        self.storage: JSONStorageBackend = None
        self.processor: URLProcessor = None
        self.listener: TelegramListener = None
        self._shutdown_event = asyncio.Event()
        self._batch = batch
        self._batch_timeout = batch_timeout

    def initialize(self) -> None:
        """Initialize all components."""
        logger.info("initializing_content_aggregator")

        # Create directories
        self.settings.setup_directories()

        # Initialize storage
        self.storage = JSONStorageBackend(self.settings)

        # Initialize processor
        self.processor = URLProcessor(settings=self.settings, storage=self.storage)

        # Initialize Telegram listener
        self.listener = TelegramListener(
            settings=self.settings, processor=self.processor
        )

        logger.info("content_aggregator_initialized")

    async def run(self) -> None:
        """Run the application."""
        logger.info("starting_content_aggregator")

        # Setup signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._signal_handler)

        try:
            # Start processor background workers
            await self.processor.start()

            if self._batch:
                await self._run_batch()
            else:
                await self.listener.run()
        except Exception as e:
            logger.exception("error_running_aggregator", error=str(e))
            raise

    async def _run_batch(self) -> None:
        """Run in batch mode: fetch all messages, process, then exit."""
        logger.info("batch_mode_started", timeout=self._batch_timeout)
        total_fetched = await self.listener.batch_import(timeout=self._batch_timeout)
        if not total_fetched:
            logger.info("batch_no_messages_found")

        print("\n\n⏳ Waiting for pending jobs to complete...")
        await self.processor._job_queue.join()

        print("✅ All jobs complete. Shutting down...")
        await self.shutdown()

    def _signal_handler(self) -> None:
        """Handle shutdown signals."""
        logger.info("shutdown_signal_received")
        self._shutdown_event.set()

        # Create task to stop listener
        asyncio.create_task(self.listener.stop())

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        logger.info("shutting_down")

        if self.listener:
            await self.listener.stop()
        if self.processor:
            await self.processor.stop()

        logger.info("shutdown_complete")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Content Aggregator")
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Import all historical messages from Telegram, process, then exit",
    )
    parser.add_argument(
        "--batch-timeout",
        type=int,
        default=60,
        help="Seconds to spend fetching messages in batch mode (default: 60)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Content Aggregator")
    print("=" * 60)
    print()

    app = ContentAggregator(batch=args.batch, batch_timeout=args.batch_timeout)

    try:
        app.initialize()
        asyncio.run(app.run())
    except KeyboardInterrupt:
        print("\n\nShutdown requested...")
    except Exception as e:
        logger.exception("fatal_error", error=str(e))
        print(f"\nFatal error: {e}")
        sys.exit(1)
    if not args.batch:
        print("Goodbye!")


if __name__ == "__main__":
    main()
