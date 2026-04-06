# AI-Powered Content Aggregator - Design Document

**Date:** 2026-04-04  
**Status:** Approved for Implementation  
**Scope:** Web articles only (expandable to other formats later)

---

## Overview

A single-process Python application that receives URLs from a configured Telegram channel, processes them through an AI-powered pipeline (fetch, parse, summarize), and stores the results in local JSON files.

**Design Philosophy:** Start simple (Approach A), architect for future scalability (Approach B).

---

## Components

### 1. Config Manager (`config/settings.py`)

**Responsibilities:**
- Load configuration from environment variables and/or config file
- Provide LLM endpoint configuration (supports OpenAI API-compatible endpoints)
- Validate required settings on startup

**Configuration Schema:**
```yaml
# Telegram
TELEGRAM_BOT_TOKEN: str          # Bot token from @BotFather
TELEGRAM_CHANNEL_ID: int/str     # Channel to monitor (ID or username)

# LLM Configuration
LLM_PROVIDER: str                # "openai" or "custom"
LLM_API_KEY: str                 # API key for the endpoint
LLM_BASE_URL: str                # Base URL (e.g., "https://api.openai.com/v1" or custom)
LLM_MODEL: str                   # Model name (e.g., "gpt-4", "gpt-3.5-turbo")
LLM_MAX_TOKENS: int              # Max tokens for summary (default: 500)
LLM_TEMPERATURE: float           # Temperature for summarization (default: 0.3)

# Storage
DATA_DIR: str                    # Path to data directory (default: ./data)
ARTICLES_SUBDIR: str             # Subdir for article JSONs (default: articles)
LOG_FILE: str                    # Processing log filename

# Application
LOG_LEVEL: str                   # Logging level (default: INFO)
PROCESSING_INTERVAL: int         # Seconds between polls (default: 5)
```

**Extensibility:** Adding new LLM providers requires only updating the config schema and summarizer initialization.

---

### 2. Telegram Listener (`src/telegram_listener.py`)

**Responsibilities:**
- Connect to Telegram Bot API using python-telegram-bot library
- Filter messages from configured channel only
- Extract URLs from messages (supports multiple URLs per message)
- Pass extracted URLs to URL Processor

**Message Handling:**
- Parse messages for HTTP/HTTPS URLs using regex
- Support URL extraction from:
  - Plain text messages
  - Messages with entities (links, formatted text)
  - Forwarded messages (if from allowed channel)

**Error Handling:**
- Connection errors: Exponential backoff retry (max 5 attempts)
- Invalid messages: Log and skip
- Malformed URLs: Log warning, skip processing

---

### 3. URL Processor (`src/url_processor.py`)

**Responsibilities:**
- Orchestrate the content processing pipeline
- Handle sequential URL processing (one at a time)
- Coordinate between components
- Manage error recovery and retries

**Pipeline Steps:**
1. **Validate** URL format and check for duplicates
2. **Fetch** webpage content via HTTP request
3. **Extract** article content and metadata
4. **Summarize** using configured LLM
5. **Store** results to JSON file

**Job Abstraction (Flexibility for Queue-Based Migration):**
```python
class ProcessingJob:
    def __init__(self, url: str, message_id: int, received_at: datetime):
        self.url = url
        self.message_id = message_id
        self.received_at = received_at
        self.status = "pending"  # pending, processing, completed, failed
        self.attempts = 0
        self.result = None
        self.error = None
```

**Error Handling:**
- Retry failed steps up to 3 times with exponential backoff
- Skip to next URL if max retries exceeded
- Log all failures to processing_log.json

---

### 4. Content Extractor (`src/content_extractor.py`)

**Responsibilities:**
- Fetch webpage content via HTTP
- Extract article text, title, author, publish date
- Clean and normalize extracted content

**Libraries:**
- **Primary:** trafilatura (modern, focused on article extraction)
- **Fallback:** newspaper3k (if trafilatura fails)

**Metadata Extracted:**
- Title
- Author(s)
- Publish date
- Main article text (HTML stripped)
- Source domain
- Word count
- Extraction timestamp

**Error Handling:**
- HTTP errors (404, 500, etc.): Log and mark as failed
- Paywall detection: Attempt extraction anyway, mark if paywalled
- JavaScript-rendered sites: Document limitation (future: add headless browser support)

---

### 5. Summarizer (`src/summarizer.py`)

**Responsibilities:**
- Send extracted content to LLM endpoint
- Generate concise summary
- Handle API errors and rate limits

**Configuration-Driven:**
- Supports any OpenAI API-compatible endpoint
- Configurable model, temperature, max tokens
- Support for custom system prompts

**Prompt Template:**
```
System: You are a content summarizer. Create a concise summary of the 
following article. Include: 1) Main points, 2) Key takeaways, 3) Overall theme.
Be factual and objective. Maximum 3-4 paragraphs.

Article Title: {title}
Article Content: {content}

Provide a summary:
```

**Error Handling:**
- API rate limits: Exponential backoff retry
- Token limit exceeded: Truncate content and retry
- API errors: Log and mark as failed (article stored without summary)

---

### 6. Storage Manager (`src/storage.py`)

**Responsibilities:**
- Read/write article data to JSON files
- Maintain processing log
- Handle concurrent access (file locking)

**Storage Schema:**

**Article JSON (per article):**
```json
{
  "id": "uuid-v4",
  "url": "https://example.com/article",
  "source_channel": "@channel_name",
  "message_id": 12345,
  "received_at": "2026-04-04T10:30:00Z",
  "processed_at": "2026-04-04T10:31:15Z",
  "status": "completed",
  "extraction": {
    "title": "Article Title",
    "author": "Author Name",
    "publish_date": "2026-04-03",
    "content": "Full article text...",
    "domain": "example.com",
    "word_count": 1500
  },
  "summary": {
    "text": "AI-generated summary...",
    "model": "gpt-4",
    "generated_at": "2026-04-04T10:31:10Z"
  },
  "metadata": {
    "extraction_library": "trafilatura",
    "processing_duration_seconds": 75
  }
}
```

**Processing Log (single JSON file):**
```json
{
  "last_processed_message_id": 12345,
  "total_urls_received": 150,
  "total_processed": 145,
  "total_failed": 5,
  "recent_failures": [
    {
      "url": "...",
      "error": "HTTP 404",
      "timestamp": "..."
    }
  ]
}
```

**Storage Structure:**
```
data/
├── articles/
│   ├── 2026-04-04/
│   │   ├── article-uuid-1.json
│   │   └── article-uuid-2.json
│   └── 2026-04-03/
│       └── article-uuid-3.json
└── processing_log.json
```

**Concurrency:**
- Use file locking (portalocker or similar) for processing_log.json
- Atomic writes for article JSONs (write to temp, then move)

**Interface Pattern (for future database migration):**
```python
class StorageBackend(ABC):
    @abstractmethod
    def save_article(self, article: dict) -> str:
        pass
    
    @abstractmethod
    def get_article(self, article_id: str) -> dict:
        pass
    
    @abstractmethod
    def update_log(self, entry: dict) -> None:
        pass

class JSONStorageBackend(StorageBackend):
    # Current implementation
    pass

# Future: class DatabaseStorageBackend(StorageBackend)
```

---

## Data Flow

```
┌─────────────────┐
│ Telegram Channel│
└────────┬────────┘
         │ Message with URL(s)
         ▼
┌──────────────────────┐
│ Telegram Listener    │
│ (long-polling)       │
└────────┬─────────────┘
         │ List of URLs
         ▼
┌──────────────────────┐
│ URL Processor        │
│ (processes one at    │
│  a time sequentially)│
└────────┬─────────────┘
         │ URL
         ▼
┌──────────────────────┐
│ Content Extractor    │
│ (fetch & parse)      │
└────────┬─────────────┘
         │ Article content
         ▼
┌──────────────────────┐
│ Summarizer           │
│ (LLM API call)       │
└────────┬─────────────┘
         │ Summary
         ▼
┌──────────────────────┐
│ Storage Manager      │
│ (JSON files)         │
└──────────────────────┘
```

---

## Error Handling Strategy

### Retry Logic (per step)
- **Transient errors** (network, API rate limits): 3 retries with exponential backoff (1s, 2s, 4s)
- **Permanent errors** (404, invalid URL): Log and skip
- **Processing failures**: Mark URL as failed, continue to next

### Failure Categories
1. **Telegram connection lost:** Auto-reconnect with backoff
2. **URL fetch failed:** Log, skip, continue
3. **Content extraction failed:** Log, store URL-only record
4. **LLM API failed:** Log, store article without summary
5. **Storage write failed:** Retry, then crash (data integrity critical)

### Recovery
- On restart, resume from last processed message ID
- Failed URLs can be manually re-processed via CLI tool (future enhancement)

---

## Extensibility Points

### 1. Queue-Based Architecture (Approach B)
To migrate to queue-based:
- Replace `URLProcessor.process_single()` with queue producer
- Create separate worker processes that consume from queue
- Storage backend already abstracted
- No changes needed to: Telegram Listener (just publishes), Extractor, Summarizer

### 2. Additional Content Types
Current design supports web articles. To add PDFs:
- Add PDF extractor class (implements same interface as ContentExtractor)
- URL Processor selects extractor based on URL/file extension
- Storage schema already supports arbitrary metadata

### 3. Additional Storage Backends
To migrate to PostgreSQL:
- Implement `DatabaseStorageBackend` class
- Update config to specify backend type
- Run migration script to import existing JSON files

### 4. Different LLM Providers
To add local models via Ollama:
- Create `OllamaSummarizer` class (implements same interface)
- Update config to select provider
- No other changes needed

---

## Testing Strategy

### Unit Tests
- Config Manager: Test loading from env vars, validation
- Content Extractor: Mock HTTP responses, test extraction
- Summarizer: Mock LLM API, test prompt formatting
- Storage Manager: Test read/write, concurrent access, atomic operations

### Integration Tests
- End-to-end pipeline with mocked Telegram and LLM
- Error injection (network failures, API errors)
- Storage recovery tests

### Manual Testing
- Connect to test Telegram channel
- Process real URLs
- Verify JSON output format

---

## Security Considerations

1. **Secrets Management:** API keys stored in environment variables, never committed
2. **Input Validation:** Validate all URLs before fetching (protocol, domain whitelist optional)
3. **Rate Limiting:** Built-in delays between requests (respect target websites)
4. **Data Privacy:** Article content stored locally only (no cloud)

---

## Dependencies

```
# Core
python-telegram-bot>=20.0    # Telegram integration
trafilatura>=1.6              # Content extraction
newspaper3k>=0.2.8            # Fallback extractor

# LLM
openai>=1.0                   # OpenAI API client (works with compatible endpoints)

# Storage
portalocker>=2.7              # File locking for concurrent access

# Utilities
pydantic>=2.0                 # Config validation
python-dotenv>=1.0            # Environment variable loading
structlog>=23.0               # Structured logging

# Testing
pytest>=7.0
pytest-asyncio>=0.21
httpx>=0.25                   # For mocking HTTP in tests
respx>=0.20                   # HTTPX mocking
```

---

## Project Structure

```
content-aggregator/
├── config/
│   ├── __init__.py
│   └── settings.py           # Configuration management
├── src/
│   ├── __init__.py
│   ├── telegram_listener.py  # Telegram bot integration
│   ├── url_processor.py      # Pipeline orchestration
│   ├── content_extractor.py  # Web scraping
│   ├── summarizer.py         # LLM integration
│   └── storage.py            # File I/O
├── data/                     # Data directory (gitignored)
│   ├── articles/
│   └── processing_log.json
├── tests/
│   ├── __init__.py
│   ├── test_config.py
│   ├── test_extractor.py
│   ├── test_summarizer.py
│   └── test_storage.py
├── .env.example              # Example environment variables
├── .gitignore
├── main.py                   # Application entry point
├── requirements.txt
└── README.md                 # Setup and usage instructions
```

---

## Configuration Example (.env)

```bash
# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHANNEL_ID=@your_channel_username

# LLM (OpenAI example)
LLM_PROVIDER=openai
LLM_API_KEY=sk-your-api-key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-3.5-turbo
LLM_MAX_TOKENS=500
LLM_TEMPERATURE=0.3

# LLM (Custom endpoint example)
# LLM_PROVIDER=custom
# LLM_API_KEY=your-key
# LLM_BASE_URL=http://localhost:8000/v1
# LLM_MODEL=llama-2-7b

# Storage
DATA_DIR=./data

# App
LOG_LEVEL=INFO
PROCESSING_INTERVAL=5
```

---

## Success Criteria

- [ ] Successfully receives URLs from configured Telegram channel
- [ ] Extracts article content from 90%+ of valid URLs
- [ ] Generates summaries using configured LLM endpoint
- [ ] Stores results in JSON files with defined schema
- [ ] Handles errors gracefully (doesn't crash on bad URLs)
- [ ] Resumes from last processed message after restart
- [ ] Code is modular and ready for queue-based migration

---

## Future Enhancements (Out of Scope)

- Queue-based architecture (Approach B)
- Web UI for browsing stored articles
- Search functionality across summaries
- Duplicate detection (by content hash)
- PDF and video support
- Database storage backend
- REST API for manual URL submission
- Article tagging/categorization
- Export to other formats (Markdown, PDF)

---

**Next Step:** Implementation planning via `writing-plans` skill.
