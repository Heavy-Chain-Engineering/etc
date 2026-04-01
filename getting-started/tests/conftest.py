"""Shared test fixtures for the SDLC Dashboard test suite."""

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def valid_state_path() -> Path:
    """Path to a valid state.json fixture."""
    return FIXTURES_DIR / "valid_state.json"


@pytest.fixture()
def valid_tasks_path() -> Path:
    """Path to a valid tasks.json fixture."""
    return FIXTURES_DIR / "valid_tasks.json"


@pytest.fixture()
def malformed_json_path() -> Path:
    """Path to a malformed JSON fixture."""
    return FIXTURES_DIR / "malformed.json"


@pytest.fixture()
def missing_file_path() -> Path:
    """Path to a non-existent file."""
    return FIXTURES_DIR / "does_not_exist.json"


@pytest.fixture()
def minimal_state_path() -> Path:
    """Path to a minimal state.json with only Bootstrap phase."""
    return FIXTURES_DIR / "minimal_state.json"


@pytest.fixture()
def empty_tasks_path() -> Path:
    """Path to a tasks.json with no tasks."""
    return FIXTURES_DIR / "empty_tasks.json"
