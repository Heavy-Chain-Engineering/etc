"""Tests for app.py — FastAPI application and API endpoints."""

import importlib
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


def _get_app_module():
    """Import the app module from the project root."""
    project_root = Path(__file__).parent.parent
    app_path = project_root / "app.py"
    spec = importlib.util.spec_from_file_location("sdlc_app", str(app_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sdlc_app"] = mod
    spec.loader.exec_module(mod)
    return mod


class TestAPIState:
    """Tests for GET /api/state endpoint."""

    def test_should_return_sdlc_state_when_state_file_exists(
        self, valid_state_path: Path
    ) -> None:
        mod = _get_app_module()
        original = mod.SDLC_STATE_PATH
        try:
            mod.SDLC_STATE_PATH = valid_state_path
            from fastapi.testclient import TestClient
            client = TestClient(mod.app)
            response = client.get("/api/state")
        finally:
            mod.SDLC_STATE_PATH = original
        assert response.status_code == 200
        data = response.json()
        assert data["current_phase"] == "Build"
        assert data["error"] is None
        assert len(data["phases"]) == 7

    def test_should_return_error_in_body_when_state_file_missing(
        self, missing_file_path: Path
    ) -> None:
        mod = _get_app_module()
        original = mod.SDLC_STATE_PATH
        try:
            mod.SDLC_STATE_PATH = missing_file_path
            from fastapi.testclient import TestClient
            client = TestClient(mod.app)
            response = client.get("/api/state")
        finally:
            mod.SDLC_STATE_PATH = original
        assert response.status_code == 200
        data = response.json()
        assert data["error"] is not None
        assert data["current_phase"] == "Unknown"

    def test_should_include_dod_progress_when_state_valid(
        self, valid_state_path: Path
    ) -> None:
        mod = _get_app_module()
        original = mod.SDLC_STATE_PATH
        try:
            mod.SDLC_STATE_PATH = valid_state_path
            from fastapi.testclient import TestClient
            client = TestClient(mod.app)
            response = client.get("/api/state")
        finally:
            mod.SDLC_STATE_PATH = original
        data = response.json()
        assert "dod_progress" in data
        assert data["dod_progress"]["total"] == 3
        assert data["dod_progress"]["completed"] == 1


class TestAPITasks:
    """Tests for GET /api/tasks endpoint."""

    def test_should_return_task_summary_when_tasks_file_exists(
        self, valid_tasks_path: Path
    ) -> None:
        mod = _get_app_module()
        original = mod.TASKS_PATH
        try:
            mod.TASKS_PATH = valid_tasks_path
            from fastapi.testclient import TestClient
            client = TestClient(mod.app)
            response = client.get("/api/tasks")
        finally:
            mod.TASKS_PATH = original
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert data["completed"] == 2
        assert data["error"] is None

    def test_should_return_error_in_body_when_tasks_file_missing(
        self, missing_file_path: Path
    ) -> None:
        mod = _get_app_module()
        original = mod.TASKS_PATH
        try:
            mod.TASKS_PATH = missing_file_path
            from fastapi.testclient import TestClient
            client = TestClient(mod.app)
            response = client.get("/api/tasks")
        finally:
            mod.TASKS_PATH = original
        assert response.status_code == 200
        data = response.json()
        assert data["error"] is not None
        assert data["total"] == 0

    def test_should_return_zero_counts_when_no_tasks(
        self, empty_tasks_path: Path
    ) -> None:
        mod = _get_app_module()
        original = mod.TASKS_PATH
        try:
            mod.TASKS_PATH = empty_tasks_path
            from fastapi.testclient import TestClient
            client = TestClient(mod.app)
            response = client.get("/api/tasks")
        finally:
            mod.TASKS_PATH = original
        data = response.json()
        assert data["total"] == 0
        assert data["completed"] == 0


class TestRootRoute:
    """Tests for GET / root route."""

    def test_should_redirect_to_dashboard_when_accessing_root(self) -> None:
        mod = _get_app_module()
        from fastapi.testclient import TestClient
        client = TestClient(mod.app, follow_redirects=False)
        response = client.get("/")
        assert response.status_code in (301, 302, 307)
        assert "/static/index.html" in response.headers.get("location", "")
