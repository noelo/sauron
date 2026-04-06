# Content Aggregator

AI-powered content aggregator that receives URLs from a Telegram channel, processes them through an AI pipeline (fetch, parse, summarize), and stores the results in local JSON files.

## Features

- 🤖 **Telegram Integration**: Monitors a configured Telegram channel for new URLs
- 🔍 **Content Extraction**: Extracts article content using trafilatura (with newspaper3k fallback)
- 🧠 **AI Summarization**: Generates summaries using OpenAI API or compatible endpoints
- 💾 **JSON Storage**: Stores articles and processing logs in organized JSON files
- 🔄 **Retry Logic**: Automatic retry with exponential backoff for failed URLs
- 🚀 **Extensible Design**: Built for easy migration to queue-based architecture

## Quick Start

### Prerequisites

- Python 3.11+
- Telegram Bot Token (from [@BotFather](https://t.me/botfather))
- OpenAI API Key (or compatible endpoint)

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd content-aggregator
```

2. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your settings
```

### Configuration

Edit `.env` file with your settings:

```bash
# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHANNEL_ID=@your_channel_username

# LLM (OpenAI or compatible)
LLM_PROVIDER=openai
LLM_API_KEY=sk-your-api-key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-3.5-turbo

# Storage
DATA_DIR=./data
```

### Running

```bash
python main.py
```

The bot will:
1. Connect to Telegram
2. Monitor the configured channel for URLs
3. Process each URL through the pipeline
4. Store results in `data/articles/`

### Commands

- `/start` - Show welcome message
- `/status` - Show processing statistics

## Project Structure

```
content-aggregator/
├── config/
│   └── settings.py          # Configuration management
├── src/
│   ├── telegram_listener.py # Telegram bot integration
│   ├── url_processor.py     # Pipeline orchestration
│   ├── content_extractor.py # Web scraping
│   ├── summarizer.py        # LLM integration
│   ├── storage.py           # File I/O
│   └── exceptions.py        # Custom exceptions
├── data/                    # Storage directory (gitignored)
│   ├── articles/            # Article JSONs organized by date
│   └── processing_log.json  # Processing statistics
├── tests/                   # Test suite
├── main.py                  # Application entry point
├── requirements.txt
└── README.md
```

## Storage Format

Articles are stored as JSON files organized by date:

```json
{
  "id": "uuid-v4",
  "url": "https://example.com/article",
  "message_id": 12345,
  "received_at": "2026-04-04T10:30:00Z",
  "processed_at": "2026-04-04T10:31:15Z",
  "extraction": {
    "title": "Article Title",
    "author": "Author Name",
    "content": "Full article text...",
    "domain": "example.com",
    "word_count": 1500
  },
  "summary": {
    "text": "AI-generated summary...",
    "model": "gpt-3.5-turbo"
  }
}
```

## Testing

Run tests:
```bash
pytest tests/ -v
```

## Architecture

The application is built with modularity in mind for easy future expansion:

1. **Storage Backend**: Abstract base class allows swapping JSON for database
2. **Content Extractor**: Multiple extractors with automatic fallback
3. **Summarizer**: Supports any OpenAI API-compatible endpoint
4. **URL Processor**: Job abstraction designed for queue-based migration

## Future Enhancements

- Queue-based architecture (Redis/RabbitMQ)
- Web UI for browsing articles
- Search functionality
- Support for PDFs and videos
- REST API for manual URL submission

## License

MIT
