"""Storage backend for article data and processing logs."""

import json
import tempfile
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import portalocker
import structlog

from config.settings import Settings
from src.exceptions import StorageError

logger = structlog.get_logger(__name__)


class StorageBackend(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    def save_article(self, article: Dict[str, Any]) -> str:
        """Save an article and return its ID."""
        pass

    @abstractmethod
    def get_article(self, article_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve an article by ID."""
        pass

    @abstractmethod
    def update_log(self, entry: Dict[str, Any]) -> None:
        """Update the processing log."""
        pass

    @abstractmethod
    def get_log(self) -> Dict[str, Any]:
        """Get the current processing log."""
        pass


class JSONStorageBackend(StorageBackend):
    """File-based storage using JSON files with atomic writes and locking."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.articles_dir = settings.articles_dir
        self.log_path = settings.log_path
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Create necessary directories if they don't exist."""
        self.articles_dir.mkdir(parents=True, exist_ok=True)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _get_article_path(
        self, article_id: str, date: Optional[datetime] = None
    ) -> Path:
        """Get the file path for an article."""
        if date is None:
            date = datetime.now(timezone.utc)

        date_dir = self.articles_dir / date.strftime("%Y-%m-%d")
        date_dir.mkdir(parents=True, exist_ok=True)
        return date_dir / f"{article_id}.json"

    def save_article(self, article: Dict[str, Any]) -> str:
        """Save an article atomically using write-then-move pattern."""
        article_id = article.get("id", str(uuid.uuid4()))
        processed_at = article.get("processed_at")

        if processed_at:
            try:
                date = datetime.fromisoformat(processed_at.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                date = datetime.now(timezone.utc)
        else:
            date = datetime.now(timezone.utc)

        article_path = self._get_article_path(article_id, date)

        try:
            # Write to temp file first, then move atomically
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, dir=article_path.parent
            ) as temp_file:
                json.dump(article, temp_file, indent=2, ensure_ascii=False)
                temp_path = Path(temp_file.name)

            # Atomic move
            temp_path.rename(article_path)

            logger.info("article_saved", article_id=article_id, path=str(article_path))

            return article_id

        except Exception as e:
            logger.error("failed_to_save_article", article_id=article_id, error=str(e))
            raise StorageError(f"Failed to save article {article_id}: {e}") from e

    def get_article(self, article_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve an article by ID."""
        # Search through date directories
        for date_dir in self.articles_dir.iterdir():
            if date_dir.is_dir():
                article_path = date_dir / f"{article_id}.json"
                if article_path.exists():
                    try:
                        with open(article_path, "r", encoding="utf-8") as f:
                            return json.load(f)
                    except Exception as e:
                        logger.error(
                            "failed_to_read_article",
                            article_id=article_id,
                            path=str(article_path),
                            error=str(e),
                        )
                        raise StorageError(
                            f"Failed to read article {article_id}: {e}"
                        ) from e

        return None

    def _load_log(self) -> Dict[str, Any]:
        """Load the processing log, creating if it doesn't exist."""
        if not self.log_path.exists():
            return {
                "last_processed_message_id": 0,
                "total_urls_received": 0,
                "total_processed": 0,
                "total_failed": 0,
                "recent_failures": [],
            }

        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                portalocker.lock(f, portalocker.LOCK_SH)
                content = f.read()
                portalocker.unlock(f)
                return json.loads(content) if content else {}
        except json.JSONDecodeError:
            logger.error("processing_log_corrupted", path=str(self.log_path))
            return {
                "last_processed_message_id": 0,
                "total_urls_received": 0,
                "total_processed": 0,
                "total_failed": 0,
                "recent_failures": [],
                "_note": "Log was reset due to corruption",
            }
        except Exception as e:
            logger.error("failed_to_load_log", path=str(self.log_path), error=str(e))
            raise StorageError(f"Failed to load processing log: {e}") from e

    def _save_log(self, log: Dict[str, Any]) -> None:
        """Save the processing log with file locking."""
        try:
            with open(self.log_path, "w", encoding="utf-8") as f:
                portalocker.lock(f, portalocker.LOCK_EX)
                json.dump(log, f, indent=2, ensure_ascii=False)
                portalocker.unlock(f)
        except Exception as e:
            logger.error("failed_to_save_log", path=str(self.log_path), error=str(e))
            raise StorageError(f"Failed to save processing log: {e}") from e

    def update_log(self, entry: Dict[str, Any]) -> None:
        """Update the processing log with a new entry."""
        log = self._load_log()

        # Update counters
        if entry.get("status") == "completed":
            log["total_processed"] = log.get("total_processed", 0) + 1
        elif entry.get("status") == "failed":
            log["total_failed"] = log.get("total_failed", 0) + 1

        log["total_urls_received"] = log.get("total_urls_received", 0) + 1

        # Update last processed message ID
        if "message_id" in entry:
            current_last = log.get("last_processed_message_id", 0)
            log["last_processed_message_id"] = max(current_last, entry["message_id"])

        # Add to recent failures if failed
        if entry.get("status") == "failed":
            failures = log.get("recent_failures", [])
            failures.append(
                {
                    "url": entry.get("url"),
                    "error": entry.get("error"),
                    "timestamp": entry.get(
                        "timestamp", datetime.now(timezone.utc).isoformat()
                    ),
                }
            )
            # Keep only last 100 failures
            log["recent_failures"] = failures[-100:]

        self._save_log(log)

        logger.info(
            "log_updated",
            total_processed=log["total_processed"],
            total_failed=log["total_failed"],
        )

    def get_log(self) -> Dict[str, Any]:
        """Get the current processing log."""
        return self._load_log()

    def list_articles(self, limit: int = 100) -> List[Dict[str, Any]]:
        """List recent articles, sorted by date descending."""
        articles = []

        # Get all date directories, sorted by name (YYYY-MM-DD)
        date_dirs = sorted(self.articles_dir.iterdir(), reverse=True)

        for date_dir in date_dirs:
            if not date_dir.is_dir():
                continue

            # Get all JSON files in this directory
            article_files = sorted(date_dir.glob("*.json"), reverse=True)

            for article_file in article_files:
                try:
                    with open(article_file, "r", encoding="utf-8") as f:
                        articles.append(json.load(f))

                    if len(articles) >= limit:
                        return articles

                except Exception as e:
                    logger.warning(
                        "failed_to_read_article_file",
                        path=str(article_file),
                        error=str(e),
                    )
                    continue

        return articles
