"""Tests for storage backend."""

import json
import tempfile
from datetime import datetime, UTC
from pathlib import Path

import pytest

from config.settings import Settings
from src.exceptions import StorageError
from src.storage import JSONStorageBackend


@pytest.fixture
def temp_storage():
    """Create a temporary storage backend for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = Settings(
            telegram_bot_token="test",
            telegram_channel_id="@test",
            llm_api_key="test",
            data_dir=Path(tmpdir) / "data",
        )
        storage = JSONStorageBackend(settings)
        yield storage


class TestJSONStorageBackend:
    """Test suite for JSON storage backend."""

    def test_save_article_creates_file(self, temp_storage):
        """Test that saving an article creates a JSON file."""
        article = {
            "id": "test-123",
            "url": "https://example.com/article",
            "title": "Test Article",
            "processed_at": datetime.now(UTC).isoformat(),
        }

        article_id = temp_storage.save_article(article)

        assert article_id == "test-123"

        # Check file was created
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        expected_path = temp_storage.articles_dir / today / "test-123.json"
        assert expected_path.exists()

        # Check content
        with open(expected_path, "r") as f:
            saved = json.load(f)
        assert saved["title"] == "Test Article"

    def test_save_article_generates_id_if_missing(self, temp_storage):
        """Test that article ID is auto-generated if not provided."""
        article = {"url": "https://example.com/article", "title": "Test Article"}

        article_id = temp_storage.save_article(article)

        assert article_id  # Should be a non-empty UUID
        assert len(article_id) == 36  # UUID length

    def test_get_article_existing(self, temp_storage):
        """Test retrieving an existing article."""
        article = {
            "id": "retrieve-test",
            "url": "https://example.com/article",
            "title": "Test Article",
            "processed_at": datetime.now(UTC).isoformat(),
        }

        temp_storage.save_article(article)
        retrieved = temp_storage.get_article("retrieve-test")

        assert retrieved is not None
        assert retrieved["title"] == "Test Article"

    def test_get_article_nonexistent(self, temp_storage):
        """Test retrieving a non-existent article returns None."""
        result = temp_storage.get_article("does-not-exist")

        assert result is None

    def test_update_log_increments_counters(self, temp_storage):
        """Test that log updates increment counters correctly."""
        entry = {
            "url": "https://example.com/article",
            "message_id": 123,
            "status": "completed",
            "timestamp": datetime.now(UTC).isoformat(),
        }

        temp_storage.update_log(entry)

        log = temp_storage.get_log()
        assert log["total_urls_received"] == 1
        assert log["total_processed"] == 1
        assert log["total_failed"] == 0
        assert log["last_processed_message_id"] == 123

    def test_update_log_tracks_failures(self, temp_storage):
        """Test that failed entries are tracked in recent_failures."""
        entry = {
            "url": "https://example.com/bad",
            "message_id": 456,
            "status": "failed",
            "error": "HTTP 404",
            "timestamp": datetime.now(UTC).isoformat(),
        }

        temp_storage.update_log(entry)

        log = temp_storage.get_log()
        assert log["total_failed"] == 1
        assert len(log["recent_failures"]) == 1
        assert log["recent_failures"][0]["error"] == "HTTP 404"

    def test_update_log_limits_recent_failures(self, temp_storage):
        """Test that recent_failures is limited to 100 entries."""
        for i in range(150):
            entry = {
                "url": f"https://example.com/article{i}",
                "message_id": i,
                "status": "failed",
                "error": f"Error {i}",
                "timestamp": datetime.now(UTC).isoformat(),
            }
            temp_storage.update_log(entry)

        log = temp_storage.get_log()
        assert len(log["recent_failures"]) == 100
        # Should keep the most recent (last 100)
        assert log["recent_failures"][-1]["error"] == "Error 149"

    def test_list_articles_sorted_by_date(self, temp_storage):
        """Test that articles are listed in reverse chronological order."""
        # Create articles on different dates
        dates = ["2026-01-01", "2026-01-15", "2026-02-01"]

        for i, date_str in enumerate(dates):
            article = {
                "id": f"article-{i}",
                "url": f"https://example.com/{i}",
                "title": f"Article {i}",
                "processed_at": f"{date_str}T10:00:00",
            }
            temp_storage.save_article(article)

        articles = temp_storage.list_articles()

        # Should be sorted newest first
        assert articles[0]["id"] == "article-2"
        assert articles[1]["id"] == "article-1"
        assert articles[2]["id"] == "article-0"

    def test_list_articles_respects_limit(self, temp_storage):
        """Test that list_articles respects the limit parameter."""
        for i in range(10):
            article = {
                "id": f"article-{i}",
                "url": f"https://example.com/{i}",
                "title": f"Article {i}",
                "processed_at": datetime.now(UTC).isoformat(),
            }
            temp_storage.save_article(article)

        articles = temp_storage.list_articles(limit=5)

        assert len(articles) == 5

    def test_log_initialization(self, temp_storage):
        """Test that log is initialized with default values if it doesn't exist."""
        log = temp_storage.get_log()

        assert log["last_processed_message_id"] == 0
        assert log["total_urls_received"] == 0
        assert log["total_processed"] == 0
        assert log["total_failed"] == 0
        assert log["recent_failures"] == []
