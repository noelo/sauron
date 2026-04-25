#!/usr/bin/env python3
"""
Content Aggregator - Main Entry Point

AI-powered content aggregator that receives URLs from Telegram,
extracts and summarizes content, and stores results in JSON files.
"""

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

    def __init__(self):
        self.settings = get_settings()
        self.storage: JSONStorageBackend = None
        self.processor: URLProcessor = None
        self.listener: TelegramListener = None
        self._shutdown_event = asyncio.Event()

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
            # Run the Telegram listener
            await self.listener.run()
        except Exception as e:
            logger.exception("error_running_aggregator", error=str(e))
            raise

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

        logger.info("shutdown_complete")


def main():
    """Main entry point."""
    print("=" * 60)
    print("Content Aggregator")
    print("=" * 60)
    print()

    app = ContentAggregator()

    try:
        app.initialize()
        asyncio.run(app.run())
    except KeyboardInterrupt:
        print("\n\nShutdown requested...")
    except Exception as e:
        logger.exception("fatal_error", error=str(e))
        print(f"\nFatal error: {e}")
        sys.exit(1)
    finally:
        print("Goodbye!")


if __name__ == "__main__":
    main()
