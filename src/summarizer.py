"""AI-powered summarization using LLM APIs."""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import structlog
from openai import AsyncOpenAI, OpenAI

from config.settings import Settings
from src.exceptions import SummarizationError

logger = structlog.get_logger(__name__)


@dataclass
class SummaryResult:
    """Result of a summarization operation."""

    text: str
    model: str
    generated_at: str
    tokens_used: Optional[int] = None
    generation_time_seconds: float = 0.0


class Summarizer(ABC):
    """Abstract base class for summarizers."""

    @abstractmethod
    def summarize(self, title: str, content: str) -> SummaryResult:
        """Generate a summary of the content."""
        pass


class OpenAISummarizer(Summarizer):
    """Summarizer using OpenAI API or compatible endpoints."""

    SYSTEM_PROMPT = """You are a content summarizer. Your task is to create a concise, 
informative summary of the provided article. 

Your summary should include:
1. Main points and key arguments
2. Important details and data
3. Overall theme or conclusion

Guidelines:
- Be factual and objective
- Use clear, concise language
- Maximum 3-4 paragraphs
- Focus on the most important information
- Do not include opinions or commentary

Provide only the summary, no additional commentary."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = OpenAI(
            api_key=settings.llm_api_key, base_url=settings.llm_base_url
        )
        self.max_tokens = settings.llm_max_tokens
        self.temperature = settings.llm_temperature

    def _truncate_content(self, content: str, max_chars: int = 8000) -> str:
        """Truncate content to fit within token limits."""
        if len(content) <= max_chars:
            return content

        # Try to truncate at a sentence boundary
        truncated = content[:max_chars]
        last_period = truncated.rfind(".")

        if last_period > max_chars * 0.8:  # If we can find a period in the last 20%
            return truncated[: last_period + 1]

        return truncated + "..."

    def summarize(self, title: str, content: str) -> SummaryResult:
        """
        Generate a summary of the article content.

        Args:
            title: Article title
            content: Article content text

        Returns:
            SummaryResult with generated summary

        Raises:
            SummarizationError: If API call fails
        """
        logger.info("starting_summarization", title=title[:50])

        start_time = time.time()

        # Truncate content if too long
        truncated_content = self._truncate_content(content)

        user_prompt = f"""Title: {title}

Content:
{truncated_content}

Please provide a summary of this article."""

        try:
            response = self.client.chat.completions.create(
                model=self.settings.llm_model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}}
            )

            summary_text = response.choices[0].message.content.strip()
            generation_time = time.time() - start_time

            tokens_used = None
            if response.usage:
                tokens_used = response.usage.total_tokens

            logger.info(
                "summarization_complete",
                generation_time=generation_time,
                tokens_used=tokens_used,
            )

            return SummaryResult(
                text=summary_text,
                model=getattr(response, "model", ""),
                generated_at=datetime.now(timezone.utc).isoformat(),
                tokens_used=tokens_used,
                generation_time_seconds=generation_time,
            )

        except Exception as e:
            logger.error("summarization_failed", error=str(e), title=title[:50])
            raise SummarizationError(f"Failed to generate summary: {e}") from e

    async def summarize_async(self, title: str, content: str) -> SummaryResult:
        """
        Async version of summarize for concurrent processing.

        Note: Currently unused but included for future queue-based architecture.
        """
        logger.info("starting_async_summarization", title=title[:50])

        start_time = time.time()
        truncated_content = self._truncate_content(content)

        user_prompt = f"""Title: {title}

Content:
{truncated_content}

Please provide a summary of this article."""

        async_client = AsyncOpenAI(
            api_key=self.settings.llm_api_key, base_url=self.settings.llm_base_url
        )

        try:
            response = await async_client.chat.completions.create(
                model=self.settings.llm_model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                chat_template_kwargs={"enable_thinking": False},
            )

            summary_text = response.choices[0].message.content.strip()
            generation_time = time.time() - start_time

            tokens_used = None
            if response.usage:
                tokens_used = response.usage.total_tokens

            return SummaryResult(
                text=summary_text,
                model=getattr(response, "model", ""),
                generated_at=datetime.now(timezone.utc).isoformat(),
                tokens_used=tokens_used,
                generation_time_seconds=generation_time,
            )

        except Exception as e:
            logger.error("async_summarization_failed", error=str(e))
            raise SummarizationError(f"Failed to generate summary: {e}") from e


def create_summarizer(settings: Settings) -> Summarizer:
    """Factory function to create appropriate summarizer."""
    return OpenAISummarizer(settings)
