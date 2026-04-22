# Content Aggregator - Agent Notes

## Quick Start

```bash
# Setup
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
# Copy and configure .env (see README.md for required vars)

# Run
python main.py

# Test
pytest tests/ -v
```

## Architecture

**Entry Point:** `main.py` - `ContentAggregator` class orchestrates components.

**Key Modules:**
- `src/telegram_listener.py` - Telegram bot polling
- `src/url_processor.py` - Pipeline orchestration with job queue
- `src/content_extractor.py` - Content extraction with fallback (trafilatura → newspaper3k)
- `src/summarizer.py` - LLM integration (OpenAI-compatible)
- `src/storage.py` - JSON file storage backend
- `src/url_handlers/` - Domain-specific handlers (Twitter, GitHub, Reddit, Fallback)

**Data Flow:** Telegram message → URL detection → Domain handler → Content extraction → LLM summarization → JSON storage in `data/articles/`

## Environment Configuration

Uses `pydantic-settings` loading from `.env`. Note the **aliased env vars**:
- `llm_api_key` → reads `TMM_MAAS_API_KEY`
- `llm_base_url` → reads `TMM_MAAS_QWEN_URL`

Other required vars: `telegram_bot_token`, `telegram_channel_id`

## Testing

- Framework: pytest with pytest-asyncio
- No special fixtures beyond `conftest.py` reset
- Tests use mocks (pytest-mock, respx for HTTP)
- Run single test: `pytest tests/test_processor.py -v`

## Project Conventions

- **Logging:** Structured logging via `structlog`, configured in `main.py`
- **Storage:** JSON files organized by date in `data/articles/YYYY-MM-DD/`
- **Exceptions:** Custom exception hierarchy in `src/exceptions.py`
- **Models:** Dataclasses in `src/models.py` (not Pydantic)
- **URL Handlers:** Pluggable pattern - inherit from `URLHandler` base class

## Important Notes

- **No pyproject.toml, setup.py, or CI configs** - pure pip + requirements.txt
- **Async throughout** - Telegram listener uses asyncio
- **Data directory** is gitignored - created at runtime via `settings.setup_directories()`
- **No linting/formatting config found** - use defaults or ask before adding
