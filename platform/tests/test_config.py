"""Tests for workspace configuration fields."""

from etc_platform.config import EtcConfig, load_config


class TestWorkspaceConfig:
    def test_default_workspace_fields(self):
        config = EtcConfig()
        assert config.workspace_root == ""
        assert config.artifact_dir == "artifacts"
        assert config.domain_briefing_path == ""
        assert config.anti_pattern_catalog_path == ""

    def test_workspace_fields_settable(self):
        config = EtcConfig(
            workspace_root="/tmp/project",
            artifact_dir="output",
            domain_briefing_path="/tmp/briefing.md",
            anti_pattern_catalog_path="/tmp/anti-patterns.md",
        )
        assert config.workspace_root == "/tmp/project"
        assert config.artifact_dir == "output"
        assert config.domain_briefing_path == "/tmp/briefing.md"
        assert config.anti_pattern_catalog_path == "/tmp/anti-patterns.md"

    def test_load_config_default_workspace(self):
        # load_config() should work without any TOML file and have default workspace fields
        config = load_config()
        assert hasattr(config, "workspace_root")
        assert hasattr(config, "artifact_dir")
        assert config.artifact_dir == "artifacts"

    def test_load_config_workspace_from_toml(self, tmp_path, monkeypatch):
        """Verify workspace fields are loaded from [workspace] TOML section."""
        toml_file = tmp_path / "etc.toml"
        toml_file.write_text(
            '[workspace]\n'
            'workspace_root = "/tmp/sandbox"\n'
            'artifact_dir = "build-output"\n'
            'domain_briefing_path = "briefing.md"\n'
            'anti_pattern_catalog_path = "anti-patterns.md"\n'
        )
        monkeypatch.chdir(tmp_path)
        config = load_config()
        assert config.workspace_root == "/tmp/sandbox"
        assert config.artifact_dir == "build-output"
        assert config.domain_briefing_path == "briefing.md"
        assert config.anti_pattern_catalog_path == "anti-patterns.md"

    def test_load_config_partial_workspace_from_toml(self, tmp_path, monkeypatch):
        """Only specified workspace fields should override defaults."""
        toml_file = tmp_path / "etc.toml"
        toml_file.write_text(
            '[workspace]\n'
            'workspace_root = "/opt/project"\n'
        )
        monkeypatch.chdir(tmp_path)
        config = load_config()
        assert config.workspace_root == "/opt/project"
        assert config.artifact_dir == "artifacts"  # default preserved
        assert config.domain_briefing_path == ""    # default preserved
        assert config.anti_pattern_catalog_path == ""  # default preserved
