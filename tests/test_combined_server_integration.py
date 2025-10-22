"""Combined Server Integration Tests - FastMCP Idiomatic Testing."""

import tempfile
from pathlib import Path

import pytest
from fastmcp import Client

from inkscape_mcp.combined import _init_config, app
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
<svg width="200" height="200" xmlns="http://www.w3.org/2000/svg">
    <circle cx="50" cy="50" r="40" fill="blue" stroke="black" stroke-width="2"/>
    <rect x="100" y="100" width="80" height="60" fill="red" opacity="0.7"/>
    <text x="100" y="50" font-family="Arial" font-size="16">Hello World</text>
</svg>"""


@pytest.fixture
def test_config(temp_workspace):
    """Test configuration for combined server testing."""
    config = InkscapeConfig(
        workspace=temp_workspace,
        max_file_size=2048,  # 2KB for testing
        timeout_default=10,
        max_concurrent=2,
    )
    _init_config(config)
    return config


class TestCombinedServerMCPIntegration:
    """Test combined server MCP protocol integration - both CLI and DOM tools."""

    @pytest.mark.asyncio
    async def test_server_connectivity(self, test_config):
        """Test: Combined MCP server is reachable and responds to ping."""
        async with Client(app) as client:
            # Basic connectivity test
            await client.ping()
            assert client.is_connected()

    @pytest.mark.asyncio
    async def test_list_all_available_tools(self, test_config):
        """Test: Combined server exposes both CLI and DOM tools."""
        async with Client(app) as client:
            tools = await client.list_tools()

            # Should have both CLI and DOM tools
            tool_names = [tool.name for tool in tools]

            # CLI tools
            assert "action_list" in tool_names
            assert "action_run" in tool_names

            # DOM tools
            assert "dom_validate" in tool_names
            assert "dom_set" in tool_names
            assert "dom_clean" in tool_names

    @pytest.mark.asyncio
    async def test_cli_tools_work_in_combined_server(
        self, test_config, test_svg_content
    ):
        """Test: CLI tools work properly in combined server."""
        async with Client(app) as client:
            # Create test SVG file
            svg_file = test_config.workspace / "cli_test.svg"
            with open(svg_file, "w") as f:
                f.write(test_svg_content)

            # Test CLI functionality
            try:
                result = await client.call_tool(
                    "action_run",
                    {
                        "doc_type": "file",
                        "doc_path": "cli_test.svg",
                        "actions": ["select-all"],
                    },
                )
                # If Inkscape available, should work
                assert isinstance(result.data, dict)
            except Exception as e:
                # Expected if Inkscape not installed or times out
                expected_errors = ["inkscape", "not found", "timeout"]
                assert any(err in str(e).lower() for err in expected_errors)

    @pytest.mark.asyncio
    async def test_dom_tools_work_in_combined_server(
        self, test_config, test_svg_content
    ):
        """Test: DOM tools work properly in combined server."""
        async with Client(app) as client:
            # Test DOM validation
            result = await client.call_tool(
                "dom_validate", {"doc_type": "inline", "doc_svg": test_svg_content}
            )

            # Should successfully validate
            assert isinstance(result.data, dict)
            assert result.data.get("ok") is True

    @pytest.mark.asyncio
    async def test_shared_configuration_across_tools(self, test_config):
        """Test: Configuration is shared between CLI and DOM tools."""
        async with Client(app) as client:
            # Test file size limits apply to both tool types
            large_svg = "<svg>" + "x" * 4096 + "</svg>"  # Exceeds 2KB limit

            # DOM tools should respect size limit
            with pytest.raises(Exception) as exc_info:
                await client.call_tool(
                    "dom_validate", {"doc_type": "inline", "doc_svg": large_svg}
                )
            error_msg = str(exc_info.value).lower()
            assert any(word in error_msg for word in ["large", "size", "limit"])

            # CLI tools should also respect size limit
            with pytest.raises(Exception) as exc_info:
                await client.call_tool(
                    "action_run",
                    {
                        "doc_type": "inline",
                        "doc_svg": large_svg,
                        "actions": ["select-all"],
                    },
                )
            error_msg = str(exc_info.value).lower()
            assert any(word in error_msg for word in ["large", "size", "limit"])

    @pytest.mark.asyncio
    async def test_workspace_isolation_across_tools(self, test_config):
        """Test: Workspace isolation works for both CLI and DOM tools."""
        async with Client(app) as client:
            # Both tool types should reject path traversal

            # Test CLI path traversal rejection
            with pytest.raises(Exception) as exc_info:
                await client.call_tool(
                    "action_run",
                    {
                        "doc_type": "file",
                        "doc_path": "../outside.svg",
                        "actions": ["select-all"],
                    },
                )
            error_msg = str(exc_info.value).lower()
            assert any(word in error_msg for word in ["workspace", "path", "escape"])

            # Test DOM path traversal rejection
            with pytest.raises(Exception) as exc_info:
                await client.call_tool(
                    "dom_set",
                    {
                        "doc_type": "file",
                        "doc_path": "../outside.svg",
                        "ops_json": (
                            '[{"selector": {"type": "css", "value": "circle"}, '
                            '"set": {"@fill": "red"}}]'
                        ),
                        "save_as": "output.svg",
                    },
                )
            error_msg = str(exc_info.value).lower()
            assert any(word in error_msg for word in ["workspace", "path", "escape"])


class TestCombinedServerWorkflows:
    """Test complete workflows using combined server - real-world usage via MCP."""

    @pytest.mark.asyncio
    async def test_complete_svg_processing_workflow(
        self, test_config, test_svg_content
    ):
        """Test: Complete SVG processing from validation to export via MCP."""
        async with Client(app) as client:
            # Create initial SVG file
            svg_file = test_config.workspace / "workflow.svg"
            with open(svg_file, "w") as f:
                f.write(test_svg_content)

            # Step 1: Validate the SVG structure using DOM tools
            validation_result = await client.call_tool(
                "dom_validate", {"doc_type": "file", "doc_path": "workflow.svg"}
            )
            assert validation_result.data.get("ok") is True

            # Step 2: Modify elements using DOM operations
            modify_result = await client.call_tool(
                "dom_set",
                {
                    "doc_type": "file",
                    "doc_path": "workflow.svg",
                    "ops_json": (
                        '[{"selector": {"type": "css", "value": "circle"}, '
                        '"set": {"style.fill": "#ff6600"}}, '
                        '{"selector": {"type": "css", "value": "rect"}, '
                        '"set": {"@opacity": "0.5"}}]'
                    ),
                    "save_as": "workflow_modified.svg",
                },
            )

            assert modify_result.data.get("ok") is True
            assert modify_result.data.get("changed") == 2

            # Step 3: Export modified SVG to PNG using CLI operations
            try:
                export_result = await client.call_tool(
                    "action_run",
                    {
                        "doc_type": "file",
                        "doc_path": "workflow_modified.svg",
                        "export_type": "png",
                        "export_out": "workflow_output.png",
                        "export_dpi": 300,
                    },
                )
                # If successful, should have output info
                assert isinstance(export_result.data, dict)
            except Exception as e:
                # Expected if Inkscape not available or times out
                expected_errors = ["inkscape", "not found", "timeout"]
                assert any(err in str(e).lower() for err in expected_errors)

    @pytest.mark.asyncio
    async def test_inline_svg_to_cleaned_file_workflow(self, test_config):
        """Test: Process inline SVG and output cleaned file via MCP."""
        async with Client(app) as client:
            # Messy inline SVG with metadata
            messy_svg = """<?xml version="1.0" encoding="UTF-8"?>
<svg width="100" height="100" xmlns="http://www.w3.org/2000/svg">
    <metadata>
        <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
            <rdf:Description>Created with Inkscape</rdf:Description>
        </rdf:RDF>
    </metadata>
    <defs>
        <linearGradient id="unused-gradient">
            <stop offset="0%" stop-color="red"/>
        </linearGradient>
    </defs>
    <circle cx="50" cy="50" r="30" fill="#3366cc"/>
    <rect x="20" y="20" width="60" height="20" fill="#cc6633"/>
</svg>"""

            # Step 1: Validate inline SVG using DOM tools
            validation_result = await client.call_tool(
                "dom_validate", {"doc_type": "inline", "doc_svg": messy_svg}
            )
            assert validation_result.data.get("ok") is True

            # Step 2: Clean the SVG (removes metadata, optimizes)
            clean_result = await client.call_tool(
                "dom_clean",
                {
                    "doc_type": "inline",
                    "doc_svg": messy_svg,
                    "save_as": "cleaned_output.svg",
                },
            )
            assert clean_result.data.get("ok") is True

            # Step 3: Verify cleaned file exists
            cleaned_file = test_config.workspace / "cleaned_output.svg"
            assert cleaned_file.exists()

            # Step 4: Further modify the cleaned file using DOM tools
            modify_result = await client.call_tool(
                "dom_set",
                {
                    "doc_type": "file",
                    "doc_path": "cleaned_output.svg",
                    "ops_json": (
                        '[{"selector": {"type": "css", "value": "circle"}, '
                        '"set": {"style.stroke": "#000000", '
                        '"style.stroke-width": "2"}}]'
                    ),
                    "save_as": "final_output.svg",
                },
            )

            assert modify_result.data.get("ok") is True

    @pytest.mark.asyncio
    async def test_batch_processing_workflow(self, test_config):
        """Test: Process multiple SVG files in batch via MCP."""
        async with Client(app) as client:
            # Create multiple test SVG files
            svg_files = []
            for i in range(3):
                svg_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg width="100" height="100" xmlns="http://www.w3.org/2000/svg">
    <circle cx="50" cy="50" r="{20 + i * 5}" fill="blue" id="circle-{i}"/>
    <text x="50" y="80" text-anchor="middle">File {i}</text>
</svg>'''
                svg_file = test_config.workspace / f"batch_{i}.svg"
                with open(svg_file, "w") as f:
                    f.write(svg_content)
                svg_files.append(f"batch_{i}.svg")

            # Process each file through the complete pipeline
            for i, svg_file in enumerate(svg_files):
                # Step 1: Validate using DOM tools
                validation_result = await client.call_tool(
                    "dom_validate", {"doc_type": "file", "doc_path": svg_file}
                )
                assert validation_result.data.get("ok") is True

                # Step 2: Modify using DOM tools (change color based on index)
                colors = ["#ff0000", "#00ff00", "#0000ff"]
                modify_result = await client.call_tool(
                    "dom_set",
                    {
                        "doc_type": "file",
                        "doc_path": svg_file,
                        "ops_json": (
                            f'[{{"selector": {{"type": "css", "value": "circle"}}, '
                            f'"set": {{"style.fill": "{colors[i]}"}}}}]'
                        ),
                        "save_as": f"batch_modified_{i}.svg",
                    },
                )

                assert modify_result.data.get("ok") is True

                # Step 3: Export to PNG using CLI tools
                try:
                    export_result = await client.call_tool(
                        "action_run",
                        {
                            "doc_type": "file",
                            "doc_path": f"batch_modified_{i}.svg",
                            "export_type": "png",
                            "export_out": f"batch_output_{i}.png",
                            "export_dpi": 150,
                        },
                    )
                    assert isinstance(export_result.data, dict)
                except Exception as e:
                    # Expected if Inkscape not available
                    assert "inkscape" in str(e).lower() or "not found" in str(e).lower()

    @pytest.mark.asyncio
    async def test_error_handling_consistency_across_tools(self, test_config):
        """Test: Error handling works consistently across CLI and DOM tools via MCP."""
        async with Client(app) as client:
            # Test CLI error handling - missing required fields
            with pytest.raises(Exception) as exc_info:
                await client.call_tool(
                    "action_run",
                    {"doc_type": "file", "doc_path": None, "actions": ["select-all"]},
                )
            assert exc_info.value is not None

            # Test DOM error handling - missing required fields
            with pytest.raises(Exception) as exc_info:
                await client.call_tool(
                    "dom_validate", {"doc_type": "inline", "doc_svg": None}
                )
            assert exc_info.value is not None

    @pytest.mark.asyncio
    async def test_tool_interoperability_via_mcp(self, test_config, test_svg_content):
        """Test: CLI and DOM tools can work together on same files via MCP."""
        async with Client(app) as client:
            # Create base SVG file
            svg_file = test_config.workspace / "interop.svg"
            with open(svg_file, "w") as f:
                f.write(test_svg_content)

            # Step 1: Use DOM tools to validate and modify
            validate_result = await client.call_tool(
                "dom_validate", {"doc_type": "file", "doc_path": "interop.svg"}
            )
            assert validate_result.data.get("ok") is True

            modify_result = await client.call_tool(
                "dom_set",
                {
                    "doc_type": "file",
                    "doc_path": "interop.svg",
                    "ops_json": (
                        '[{"selector": {"type": "css", "value": "circle"}, '
                        '"set": {"style.fill": "#ff6600"}}]'
                    ),
                    "save_as": "interop_modified.svg",
                },
            )
            assert modify_result.data.get("ok") is True

            # Step 2: Use CLI tools to process the DOM-modified file
            try:
                cli_result = await client.call_tool(
                    "action_run",
                    {
                        "doc_type": "file",
                        "doc_path": "interop_modified.svg",
                        "actions": ["select-all", "object-to-path"],
                    },
                )
                assert isinstance(cli_result.data, dict)
            except Exception as e:
                # Expected if Inkscape not available or times out
                expected_errors = ["inkscape", "not found", "timeout"]
                assert any(err in str(e).lower() for err in expected_errors)

    @pytest.mark.asyncio
    async def test_concurrent_tool_usage_via_mcp(self, test_config, test_svg_content):
        """Test: Both tool types respect concurrency limits via MCP."""
        async with Client(app) as client:
            # Create test files
            for i in range(2):
                svg_file = test_config.workspace / f"concurrent_{i}.svg"
                with open(svg_file, "w") as f:
                    f.write(test_svg_content)

            # Test that both DOM and CLI tools can run concurrently
            # within the configured limits (max_concurrent=2)

            # This is more of a smoke test - actual concurrency testing
            # would require more sophisticated coordination

            dom_result = await client.call_tool(
                "dom_validate", {"doc_type": "file", "doc_path": "concurrent_0.svg"}
            )
            assert dom_result.data.get("ok") is True

            # CLI tool should also work (sequentially in this test)
            try:
                cli_result = await client.call_tool(
                    "action_run",
                    {
                        "doc_type": "file",
                        "doc_path": "concurrent_1.svg",
                        "actions": ["select-all"],
                    },
                )
                assert isinstance(cli_result.data, dict)
            except Exception as e:
                # Expected if Inkscape not available or times out
                expected_errors = ["inkscape", "not found", "timeout"]
                assert any(err in str(e).lower() for err in expected_errors)
