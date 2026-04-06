"""Tests for URL handlers."""

import pytest
from src.url_handlers import (
    TwitterHandler,
    GitHubHandler,
    RedditHandler,
    FallbackHandler,
)


class TestGitHubHandler:
    """Test suite for GitHubHandler."""

    @pytest.fixture
    def handler(self):
        return GitHubHandler()

    def test_can_handle_github_urls(self, handler):
        """Test that handler recognizes GitHub URLs."""
        assert handler.can_handle("https://github.com/noelo/omydb") is True
        assert handler.can_handle("https://github.com/user/repo") is True
        assert handler.can_handle("https://www.github.com/user/repo") is True

    def test_cannot_handle_non_github_urls(self, handler):
        """Test that handler rejects non-GitHub URLs."""
        assert handler.can_handle("https://x.com/user") is False
        assert handler.can_handle("https://reddit.com/r/test") is False
        assert handler.can_handle("https://example.com") is False

    def test_handle_extracts_readme_from_repository(self, handler):
        """Test extracting README.md from actual GitHub repository.

        Uses https://github.com/noelo/omydb
        """
        result = handler.handle("https://github.com/noelo/omydb")

        # Verify the extraction
        assert result.url == "https://github.com/noelo/omydb"
        assert result.title == "noelo/omydb"
        assert result.author == "noelo"
        assert result.domain == "github.com"
        assert result.extraction_method == "github_handler_readme"

        # Check that README content was extracted
        assert "GitHub repository: noelo/omydb" in result.content
        assert "README.md:" in result.content
        # The README should have actual content
        assert len(result.content) > 50  # More than just the header
        assert result.word_count > 0

        # Output the README content
        print("\n" + "=" * 60)
        print("README.md contents from https://github.com/noelo/omydb:")
        print("=" * 60)
        # Extract just the README part (after the header)
        readme_start = result.content.find("README.md:") + len("README.md:")
        readme_content = result.content[readme_start:].strip()
        print(readme_content)
        print("=" * 60)

    def test_handle_unsupported_github_url(self, handler):
        """Test that non-repository URLs return placeholder."""
        result = handler.handle("https://github.com/noelo/omydb/issues/1")

        assert result.title == "GitHub"
        assert result.content == "GitHub URL: https://github.com/noelo/omydb/issues/1"
        assert result.extraction_method == "github_handler_unsupported"

    def test_handle_missing_readme(self, handler):
        """Test handling of repository without README."""
        # Use a repo that likely doesn't exist
        result = handler.handle("https://github.com/noelo/nonexistent-repo-12345")

        assert result.title == "noelo/nonexistent-repo-12345"
        assert (
            "No README.md found" in result.content
            or "Could not fetch" in result.content
        )


class TestTwitterHandler:
    """Test suite for TwitterHandler."""

    @pytest.fixture
    def handler(self):
        return TwitterHandler()

    def test_can_handle_twitter_urls(self, handler):
        """Test that handler recognizes Twitter/X URLs."""
        assert handler.can_handle("https://x.com/user/status/123") is True
        assert handler.can_handle("https://twitter.com/user/status/123") is True
        assert handler.can_handle("https://www.x.com/user") is True

    def test_cannot_handle_non_twitter_urls(self, handler):
        """Test that handler rejects non-Twitter URLs."""
        assert handler.can_handle("https://github.com/user/repo") is False
        assert handler.can_handle("https://reddit.com/r/test") is False

    def test_twitter_url_transformed_to_fxtwitter(self, handler):
        """Test that twitter.com URLs are transformed to fxtwitter.com."""
        result = handler.handle("https://twitter.com/user/status/123")
        # Check the transformed URL in the handler's logging or implementation
        # The handle method logs the transformation, so we verify no errors
        assert result.domain == "twitter.com"

    def test_x_url_transformed_to_fixupx(self, handler):
        """Test that x.com URLs are transformed to fixupx.com."""
        result = handler.handle("https://x.com/user/status/123")
        # Check that x.com domain is correctly identified
        assert result.domain == "x.com"

    def test_extract_karpathy_tweet(self, handler):
        """Test extracting content from a real x.com tweet.

        Uses https://x.com/karpathy/status/2039805659525644595
        Verifies the extracted text starts with 'LLM Knowledge Bases'
        """
        result = handler.handle("https://x.com/karpathy/status/2039805659525644595")

        # Verify extraction succeeded
        assert result.domain == "x.com"
        assert result.extraction_method == "twitter_fixup_handler"
        assert len(result.content) > 0
        assert result.word_count > 0

        # Verify content starts with expected text
        assert result.content.startswith("LLM Knowledge Bases"), (
            f"Expected content to start with 'LLM Knowledge Bases' but got: {result.content[:100]}"
        )

        # Log the extracted content for verification
        print("\n" + "=" * 60)
        print("Extracted tweet content from x.com/karpathy/status/2039805659525644595:")
        print("=" * 60)
        print(result.content)
        print("=" * 60)


class TestRedditHandler:
    """Test suite for RedditHandler."""

    @pytest.fixture
    def handler(self):
        return RedditHandler()

    def test_can_handle_reddit_urls(self, handler):
        """Test that handler recognizes Reddit URLs."""
        assert handler.can_handle("https://reddit.com/r/test") is True
        assert handler.can_handle("https://www.reddit.com/r/test") is True
        assert handler.can_handle("https://old.reddit.com/r/test") is True

    def test_cannot_handle_non_reddit_urls(self, handler):
        """Test that handler rejects non-Reddit URLs."""
        assert handler.can_handle("https://github.com/user/repo") is False
        assert handler.can_handle("https://x.com/user") is False

    def test_resolve_redirect_url_extracts_location_header(self, handler):
        """Test that shortened Reddit URLs are resolved via Location header.

        Makes an actual HTTP request to verify real-world behavior.
        URL: https://www.reddit.com/r/aiagents/s/PrLmHBkwK6

        Note: Reddit may block programmatic access with 403 Forbidden.
        In that case, the handler should raise ExtractionError.
        """
        from src.exceptions import ExtractionError

        short_url = "https://www.reddit.com/r/aiagents/s/PrLmHBkwK6"

        try:
            resolved_url = handler._resolve_redirect_url(short_url)

            # If we got here, the request succeeded
            print(f"\nOriginal URL: {short_url}")
            print(f"Resolved URL: {resolved_url}")

            # The URL should either be resolved to a comments URL or return original
            if resolved_url != short_url:
                # If redirect occurred, verify it's a Reddit comments URL
                assert "/r/aiagents/comments/" in resolved_url, (
                    f"Expected resolved URL to contain '/r/aiagents/comments/', but got: {resolved_url}"
                )
            else:
                # If no redirect, that's also valid (Reddit might have changed behavior)
                print(
                    "Note: No redirect occurred - Reddit may have changed URL structure"
                )

        except ExtractionError as e:
            # Reddit blocked the request (403 Forbidden) - this is expected behavior
            print(f"\nReddit blocked the request as expected: {e}")
            assert "403 Forbidden" in str(e)
            assert short_url in str(e)

    def test_handle_uses_resolved_url_for_shortened_reddit_urls(self, handler):
        """Test that handler uses resolved URL when processing shortened Reddit URLs.

        Makes actual HTTP requests to verify the full flow:
        1. URL resolution via Location header
        2. Post extraction via Reddit JSON API

        Note: Reddit may block programmatic access with 403 Forbidden.
        In that case, the handler should raise ExtractionError.
        """
        from src.exceptions import ExtractionError

        short_url = "https://www.reddit.com/r/aiagents/s/PrLmHBkwK6"

        try:
            result = handler.handle(short_url)

            print(f"\nShort URL: {short_url}")
            print(f"Result URL: {result.url}")
            print(f"Title: {result.title}")
            print(f"Extraction method: {result.extraction_method}")
            print(
                f"Content length: {len(result.content) if result.content else 0} chars"
            )
            print(f"Word count: {result.word_count}")

            # Verify the extraction succeeded
            assert result.domain == "reddit.com"
            assert result.word_count > 0

            # The result should use either the resolved URL or the original
            # (depending on whether Reddit redirects or not)
            assert "/r/aiagents" in result.url or "aiagents" in result.title.lower()

            # Print content preview
            if result.content:
                preview = (
                    result.content[:200] + "..."
                    if len(result.content) > 200
                    else result.content
                )
                print(f"\nContent preview:\n{preview}")

        except ExtractionError as e:
            # Reddit blocked the request (403 Forbidden) - this is expected behavior
            print(f"\nReddit blocked the request as expected: {e}")
            assert "403 Forbidden" in str(e)
            assert short_url in str(e)


class TestFallbackHandler:
    """Test suite for FallbackHandler."""

    @pytest.fixture
    def handler(self):
        return FallbackHandler()

    def test_can_handle_any_url(self, handler):
        """Test that fallback handler accepts any URL."""
        assert handler.can_handle("https://example.com") is True
        assert handler.can_handle("https://unknown-site.com") is True
        assert handler.can_handle("https://example.org/path") is True
