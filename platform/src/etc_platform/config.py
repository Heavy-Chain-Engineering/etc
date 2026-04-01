"""Configuration management using TOML files."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


@dataclass
class EtcConfig:
    database_url: str = "postgresql://etc:etc_dev@localhost:5433/etc_platform"
    default_model: str = "anthropic:claude-sonnet-4-20250514"
    agents_dir: str = "~/.claude/agents"
    standards_dir: str = "~/.claude/standards"
    log_level: str = "INFO"
    max_concurrent_agents: int = 20
    agent_timeout_seconds: int = 600

    # Workspace isolation
    workspace_root: str = ""
    artifact_dir: str = "artifacts"
    domain_briefing_path: str = ""
    anti_pattern_catalog_path: str = ""

    project_overrides: dict[str, object] = field(default_factory=dict)


def _find_config_files() -> list[Path]:
    paths = []
    global_config = Path.home() / ".etc" / "config.toml"
    if global_config.exists():
        paths.append(global_config)
    local_config = Path.cwd() / "etc.toml"
    if local_config.exists():
        paths.append(local_config)
    return paths


def load_config() -> EtcConfig:
    config = EtcConfig()

    for path in _find_config_files():
        with open(path, "rb") as f:
            data = tomllib.load(f)

        platform = data.get("platform", {})
        if "database_url" in platform:
            config.database_url = platform["database_url"]
        if "default_model" in platform:
            config.default_model = platform["default_model"]
        if "agents_dir" in platform:
            config.agents_dir = platform["agents_dir"]
        if "standards_dir" in platform:
            config.standards_dir = platform["standards_dir"]
        if "log_level" in platform:
            config.log_level = platform["log_level"]
        if "max_concurrent_agents" in platform:
            config.max_concurrent_agents = platform["max_concurrent_agents"]
        if "agent_timeout_seconds" in platform:
            config.agent_timeout_seconds = platform["agent_timeout_seconds"]

        workspace = data.get("workspace", {})
        if "workspace_root" in workspace:
            config.workspace_root = workspace["workspace_root"]
        if "artifact_dir" in workspace:
            config.artifact_dir = workspace["artifact_dir"]
        if "domain_briefing_path" in workspace:
            config.domain_briefing_path = workspace["domain_briefing_path"]
        if "anti_pattern_catalog_path" in workspace:
            config.anti_pattern_catalog_path = workspace["anti_pattern_catalog_path"]

        if "project" in data:
            config.project_overrides.update(data["project"])

    env_db = os.environ.get("ETC_DATABASE_URL")
    if env_db:
        config.database_url = env_db

    return config
