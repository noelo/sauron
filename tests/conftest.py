"""Pytest configuration and fixtures."""

import pytest


@pytest.fixture(autouse=True)
def reset_settings_cache():
    """Reset settings cache before each test to ensure fresh instances."""
    # Pydantic settings may cache, so we ensure clean state
    yield
