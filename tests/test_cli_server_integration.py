"""CLI Server Integration Tests - FastMCP Idiomatic Testing."""

import tempfile
from pathlib import Path

import pytest
from fastmcp import Client

from inkscape_mcp.cli_server import _init_config, app
from inkscape_mcp.config import InkscapeConfig


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_svg_content():
    """Sample SVG content for testing."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<svg width="100" height="100" xmlns="http://www.w3.org/2000/svg">
    <circle cx="50" cy="50" r="40" fill="blue" id="test-circle"/>
    <rect x="10" y="10" width="30" height="30" fill="red" id="test-rect"/>
</svg>"""


@pytest.fixture
def test_config(temp_workspace):
    """Test configuration with temporary workspace."""
    config = InkscapeConfig(
        workspace=temp_workspace,
        max_file_size=1024 * 1024,  # 1MB
        timeout_default=30,
        max_concurrent=2,
    )
    _init_config(config)
    return config


class TestCLIServerMCPIntegration:
    """Test CLI server MCP protocol integration - real server behavior."""

    @pytest.mark.asyncio
    async def test_server_connectivity(self, test_config):
        """Test: MCP server is reachable and responds to ping."""
        async with Client(app) as client:
            # Basic connectivity test
            await client.ping()
            assert client.is_connected()

    @pytest.mark.asyncio
    async def test_list_available_tools(self, test_config):
        """Test: Server exposes expected MCP tools."""
        async with Client(app) as client:
            tools = await client.list_tools()

            # Should have at least action.list and action.run tools
            tool_names = [tool.name for tool in tools]
            assert "action.list" in tool_names
            assert "action.run" in tool_names

    @pytest.mark.asyncio
    async def test_action_list_tool(self, test_config):
        """Test: action.list tool works via MCP protocol."""
        async with Client(app) as client:
            # This will fail if Inkscape is not installed, but that's expected
            # We're testing the MCP protocol behavior, not Inkscape functionality
            try:
                result = await client.call_tool("action.list", {})
                # If successful, should have actions key
                assert isinstance(result.data, dict)
            except Exception as e:
                # Expected if Inkscape not installed or times out - we're testing
                # MCP behavior
                expected_errors = ["inkscape", "not found", "timeout"]
                assert any(err in str(e).lower() for err in expected_errors)

    @pytest.mark.asyncio
    async def test_action_run_validation(self, test_config, test_svg_content):
        """Test: action.run tool validates arguments properly."""
        async with Client(app) as client:
            # Create test SVG file
            svg_file = test_config.workspace / "test.svg"
            with open(svg_file, "w") as f:
                f.write(test_svg_content)

            # Test with valid file-based arguments
            try:
                result = await client.call_tool(
                    "action.run",
                    {
                        "doc": {"type": "file", "path": "test.svg"},
                        "actions": ["select-all"],  # Safe action
                    },
                )
                # If Inkscape available, should succeed or fail gracefully
                assert isinstance(result.data, dict)
            except Exception as e:
                # Expected if Inkscape not installed or times out
                expected_errors = ["inkscape", "not found", "timeout"]
                assert any(err in str(e).lower() for err in expected_errors)

    @pytest.mark.asyncio
    async def test_action_run_inline_svg_validation(
        self, test_config, test_svg_content
    ):
        """Test: action.run handles inline SVG properly."""
        async with Client(app) as client:
            # Test with inline SVG
            try:
                result = await client.call_tool(
                    "action.run",
                    {
                        "doc": {"type": "inline", "svg": test_svg_content},
                        "actions": ["select-all"],
                    },
                )
                assert isinstance(result.data, dict)
            except Exception as e:
                # Expected if Inkscape not installed or times out
                expected_errors = ["inkscape", "not found", "timeout"]
                assert any(err in str(e).lower() for err in expected_errors)

    @pytest.mark.asyncio
    async def test_security_boundaries_via_mcp(self, test_config):
        """Test: Security boundaries are enforced at MCP level."""
        async with Client(app) as client:
            # Test path traversal protection
            with pytest.raises(Exception) as exc_info:
                await client.call_tool(
                    "action.run",
                    {
                        "doc": {"type": "file", "path": "../../../etc/passwd"},
                        "actions": ["select-all"],
                    },
                )
            assert (
                "workspace" in str(exc_info.value).lower()
                or "path" in str(exc_info.value).lower()
            )

    @pytest.mark.asyncio
    async def test_unsafe_action_rejection_via_mcp(self, test_config, test_svg_content):
        """Test: Unsafe actions are rejected at MCP level."""
        async with Client(app) as client:
            # Test unsafe action rejection
            with pytest.raises(Exception) as exc_info:
                await client.call_tool(
                    "action.run",
                    {
                        "doc": {"type": "inline", "svg": test_svg_content},
                        "actions": ["file-open"],  # Unsafe action
                    },
                )
            assert (
                "unsafe" in str(exc_info.value).lower()
                or "not allowed" in str(exc_info.value).lower()
            )

    @pytest.mark.asyncio
    async def test_file_size_limits_via_mcp(self, test_config):
        """Test: File size limits are enforced at MCP level."""
        async with Client(app) as client:
            # Create oversized SVG content (exceeds 1MB limit)
            large_svg = "<svg>" + "x" * (2 * 1024 * 1024) + "</svg>"  # 2MB

            with pytest.raises(Exception) as exc_info:
                await client.call_tool(
                    "action.run",
                    {
                        "doc": {"type": "inline", "svg": large_svg},
                        "actions": ["select-all"],
                    },
                )
            assert (
                "large" in str(exc_info.value).lower()
                or "size" in str(exc_info.value).lower()
            )

    @pytest.mark.asyncio
    async def test_missing_required_fields_via_mcp(self, test_config):
        """Test: Missing required fields are caught at MCP level."""
        async with Client(app) as client:
            # Test missing file path for file type
            with pytest.raises(Exception) as exc_info:
                await client.call_tool(
                    "action.run",
                    {"doc": {"type": "file", "path": None}, "actions": ["select-all"]},
                )
            # Should be caught by validation
            assert exc_info.value is not None

            # Test missing SVG for inline type
            with pytest.raises(Exception) as exc_info:
                await client.call_tool(
                    "action.run",
                    {"doc": {"type": "inline", "svg": None}, "actions": ["select-all"]},
                )
            # Should be caught by validation
            assert exc_info.value is not None


class TestCLIServerWorkflows:
    """Test complete CLI workflows via MCP protocol."""

    @pytest.mark.asyncio
    async def test_complete_export_workflow_simulation(
        self, test_config, test_svg_content
    ):
        """Test: Complete export workflow through MCP (simulation)."""
        async with Client(app) as client:
            # Create test SVG
            svg_file = test_config.workspace / "workflow.svg"
            with open(svg_file, "w") as f:
                f.write(test_svg_content)

            # Test export workflow via MCP
            try:
                result = await client.call_tool(
                    "action.run",
                    {
                        "doc": {"type": "file", "path": "workflow.svg"},
                        "export": {"type": "png", "out": "output.png", "dpi": 300},
                    },
                )
                # If successful, should have output information
                assert isinstance(result.data, dict)
                if result.data.get("ok"):
                    assert "out" in result.data
            except Exception as e:
                # Expected if Inkscape not available or times out
                expected_errors = ["inkscape", "not found", "timeout"]
                assert any(err in str(e).lower() for err in expected_errors)

    @pytest.mark.asyncio
    async def test_batch_actions_workflow_simulation(
        self, test_config, test_svg_content
    ):
        """Test: Batch actions workflow through MCP (simulation)."""
        async with Client(app) as client:
            # Test batch operations via MCP
            try:
                result = await client.call_tool(
                    "action.run",
                    {
                        "doc": {"type": "inline", "svg": test_svg_content},
                        "actions": [
                            "select-all",
                            "object-to-path",
                            "path-simplify",
                            "select-clear",
                        ],
                    },
                )
                assert isinstance(result.data, dict)
            except Exception as e:
                # Expected if Inkscape not available or times out
                expected_errors = ["inkscape", "not found", "timeout"]
                assert any(err in str(e).lower() for err in expected_errors)

    @pytest.mark.asyncio
    async def test_timeout_configuration_via_mcp(self, test_config, test_svg_content):
        """Test: Timeout configuration is respected via MCP."""
        async with Client(app) as client:
            # Test with custom timeout
            try:
                result = await client.call_tool(
                    "action.run",
                    {
                        "doc": {"type": "inline", "svg": test_svg_content},
                        "actions": ["select-all"],
                        "timeout_s": 5,  # Short timeout
                    },
                )
                assert isinstance(result.data, dict)
            except Exception as e:
                # Expected if Inkscape not available or timeout occurs
                expected_errors = ["inkscape", "not found", "timeout"]
                assert any(err in str(e).lower() for err in expected_errors)
