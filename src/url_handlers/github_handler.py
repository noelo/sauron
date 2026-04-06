"""Handler for github.com URLs - extracts README.md only."""

from urllib.parse import urlparse

import requests
import structlog

from src.models import ExtractedContent
from src.url_handlers.base import URLHandler

logger = structlog.get_logger(__name__)


class GitHubHandler(URLHandler):
    """Handler for github.com URLs - extracts only README.md from repositories."""

    DOMAINS = {"github.com", "www.github.com"}

    def can_handle(self, url: str) -> bool:
        """Check if URL is from github.com."""
        domain = self._get_domain(url)
        return domain in self.DOMAINS

    def handle(self, url: str) -> ExtractedContent:
        """Extract README.md content from GitHub repository URL.

        Only handles repository URLs (github.com/owner/repo).
        Returns placeholder for all other GitHub URLs.
        """
        self.logger.info("handling_github_url", url=url)

        parsed = urlparse(url)
        path_parts = parsed.path.strip("/").split("/")

        # Only process repository URLs (must have exactly owner/repo)
        if len(path_parts) != 2:
            return ExtractedContent(
                url=url,
                title="GitHub",
                author=None,
                content=f"GitHub URL: {url}",
                domain="github.com",
                word_count=3,
                extraction_method="github_handler_unsupported",
            )

        owner = path_parts[0]
        repo = path_parts[1]

        # Fetch README.md via raw.githubusercontent.com
        try:
            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/refs/heads/master/README.md"
            response = requests.get(raw_url, timeout=10)
            response.raise_for_status()

            readme_content = response.text
            content = (
                f"GitHub repository: {owner}/{repo}\n\nREADME.md:\n{readme_content}"
            )

            self.logger.info(
                "github_readme_extracted",
                url=url,
                owner=owner,
                repo=repo,
                content_length=len(readme_content),
            )

            return ExtractedContent(
                url=url,
                title=f"{owner}/{repo}",
                author=owner,
                content=content,
                domain="github.com",
                word_count=len(content.split()),
                extraction_method="github_handler_readme",
            )

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                self.logger.warning(
                    "github_readme_not_found", url=url, owner=owner, repo=repo
                )
                content = f"GitHub repository: {owner}/{repo}\n\nNo README.md found in master branch."
            else:
                self.logger.error("github_raw_fetch_error", url=url, error=str(e))
                content = f"GitHub repository: {owner}/{repo}\n\nCould not fetch README.md: {e}"
        except Exception as e:
            self.logger.error("github_readme_fetch_failed", url=url, error=str(e))
            content = (
                f"GitHub repository: {owner}/{repo}\n\nError fetching README.md: {e}"
            )

        return ExtractedContent(
            url=url,
            title=f"{owner}/{repo}",
            author=owner,
            content=content,
            domain="github.com",
            word_count=len(content.split()),
            extraction_method="github_handler",
        )
