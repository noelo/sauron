"""Telegram bot integration for receiving URLs."""

import asyncio
import re
from typing import Callable, List, Optional

import structlog
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config.settings import Settings
from src.url_processor import ProcessingJob, URLProcessor

logger = structlog.get_logger(__name__)

# Regex pattern for matching URLs
URL_PATTERN = re.compile(
    r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"
)


class TelegramListener:
    """
    Telegram bot listener for URL aggregation.

    Connects to Telegram API, monitors configured channel for messages containing URLs,
    and passes them to the URL processor.
    """

    def __init__(
        self,
        settings: Settings,
        processor: URLProcessor,
        on_url_received: Optional[Callable[[List[str], int], None]] = None,
    ):
        self.settings = settings
        self.processor = processor
        self.on_url_received = on_url_received
        self.application: Optional[Application] = None
        self.logger = structlog.get_logger(__name__)

        # Track processed message IDs to avoid duplicates
        self._processed_message_ids: set = set()

        # Shutdown event for graceful stop
        self._shutdown_event = asyncio.Event()

    def _extract_urls(self, text: str) -> List[str]:
        """Extract URLs from message text."""
        if not text:
            return []

        urls = URL_PATTERN.findall(text)
        # Clean up URLs (remove trailing punctuation)
        cleaned_urls = []
        for url in urls:
            # Remove trailing punctuation that's not part of URL
            while url and url[-1] in ".,;:!?)'\">":
                url = url[:-1]
            if url:
                cleaned_urls.append(url)

        return cleaned_urls

    async def _handle_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle incoming messages."""
        if not update.message or not update.message.text:
            return

        message_id = update.message.message_id
        chat_id = update.message.chat_id
        text = update.message.text

        self.logger.info(
            "message_received",
            message_id=message_id,
            chat_id=chat_id,
            text_preview=text[:100] if text else "",
        )
        print(f"📨 Message received (ID: {message_id}): {text[:80]}...")

        # Check if we've already processed this message
        if message_id in self._processed_message_ids:
            self.logger.debug("message_already_processed", message_id=message_id)
            return

        # Extract URLs
        urls = self._extract_urls(text)

        if not urls:
            self.logger.debug("no_urls_found", message_id=message_id)
            return

        self.logger.info(
            "urls_extracted", message_id=message_id, url_count=len(urls), urls=urls
        )

        # Process each URL
        for url in urls:
            try:
                job = ProcessingJob(url=url, message_id=message_id)
                result = self.processor.process_with_retry(job)

                if result.status.value == "completed":
                    self.logger.info(
                        "url_processed",
                        url=url,
                        message_id=message_id,
                        article_id=result.id,
                    )
                else:
                    self.logger.error(
                        "url_processing_failed",
                        url=url,
                        message_id=message_id,
                        error=result.error,
                    )

                # Mark message as processed
                self._processed_message_ids.add(message_id)

            except Exception as e:
                self.logger.exception(
                    "unexpected_error_processing_url",
                    url=url,
                    message_id=message_id,
                    error=str(e),
                )

    async def _start_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /start command."""
        await update.message.reply_text(
            "👋 Hello! I'm a content aggregator bot.\n\n"
            "I'll monitor this channel for URLs and process them:\n"
            "• Extract article content\n"
            "• Generate AI summaries\n"
            "• Store results in JSON files\n\n"
            "Send me a message with URLs to get started!"
        )

    async def _status_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /status command."""
        log = self.processor.storage.get_log()

        status_text = (
            f"📊 Status:\n"
            f"URLs received: {log.get('total_urls_received', 0)}\n"
            f"Processed: {log.get('total_processed', 0)}\n"
            f"Failed: {log.get('total_failed', 0)}\n"
            f"Last message ID: {log.get('last_processed_message_id', 0)}"
        )

        await update.message.reply_text(status_text)

    def setup(self) -> Application:
        """Set up the Telegram application."""
        self.logger.info("setting_up_telegram_listener")

        self.application = (
            Application.builder().token(self.settings.telegram_bot_token).build()
        )

        # Add handlers
        self.application.add_handler(CommandHandler("start", self._start_command))
        self.application.add_handler(CommandHandler("status", self._status_command))
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message)
        )

        return self.application

    async def run(self) -> None:
        """Run the Telegram listener."""
        if not self.application:
            self.setup()

        self.logger.info(
            "starting_telegram_listener", channel=self.settings.telegram_channel_id
        )

        # Start the bot
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling(drop_pending_updates=True)

        self.logger.info("telegram_listener_running")
        print("✅ Connected to Telegram and listening for messages...")

        # Keep running until stopped
        try:
            while not self._shutdown_event.is_set():
                try:
                    await asyncio.wait_for(self._shutdown_event.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            self.logger.info("telegram_listener_cancelled")
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Stop the Telegram listener."""
        self.logger.info("stopping_telegram_listener")

        # Signal the run loop to exit
        self._shutdown_event.set()

        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()

        self.logger.info("telegram_listener_stopped")
