"""Tests for configuration management."""

import os
import tempfile
from pathlib import Path, PureWindowsPath

from inkscape_mcp import cli_server, dom_server
from inkscape_mcp.config import InkscapeConfig


def test_default_config():
    """Test default configuration values."""
    config = InkscapeConfig()

    assert config.workspace.name == "inkspace"
    assert config.max_file_size == 50 * 1024 * 1024
    assert config.timeout_default == 60
    assert config.max_concurrent == 4


def test_config_from_env():
    """Test configuration from environment variables."""
    with tempfile.TemporaryDirectory() as tmpdir:
        env_vars = {
            "INKS_WORKSPACE": tmpdir,
            "INKS_MAX_FILE": "1048576",  # 1MB
            "INKS_TIMEOUT": "30",
            "INKS_MAX_CONC": "2",
        }

        # Set environment variables
        for key, value in env_vars.items():
            os.environ[key] = value

        try:
            config = InkscapeConfig.from_env()

            assert str(config.workspace) == str(Path(tmpdir).resolve())
            assert config.max_file_size == 1048576
            assert config.timeout_default == 30
            assert config.max_concurrent == 2

        finally:
            # Clean up environment variables
            for key in env_vars:
                os.environ.pop(key, None)


def test_workspace_creation():
    """Test that workspace directory is created."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir) / "test_workspace"

        config = InkscapeConfig(workspace=workspace)

        assert workspace.exists()
        assert workspace.is_dir()
        assert config.workspace.samefile(workspace)


def test_windows_style_paths_normalized(tmp_path):
    """Ensure Windows-style relative paths resolve within the workspace."""
    config = InkscapeConfig(workspace=tmp_path)
    windows_paths = ["subdir\\file.svg", "foo\\bar\\baz.svg"]

    for server in (cli_server, dom_server):
        server._init_config(config)
        try:
            for path_str in windows_paths:
                win_path = PureWindowsPath(path_str)
                normalized = Path(*win_path.parts)
                resolved = server._ensure_in_workspace(normalized)
                expected = (tmp_path / Path(*win_path.parts)).resolve()
                assert resolved == expected
        finally:
            server._init_config()
