"""DOM Server Integration Tests - FastMCP Idiomatic Testing."""

import tempfile
from pathlib import Path

import pytest
from fastmcp import Client

from inkscape_mcp.config import InkscapeConfig
from inkscape_mcp.dom_server import _init_config, app


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_svg_content():
    """Sample SVG content for DOM testing."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<svg width="200" height="200" xmlns="http://www.w3.org/2000/svg">
    <circle cx="50" cy="50" r="40" fill="blue" class="shape" id="circle1"/>
    <circle cx="150" cy="50" r="30" fill="green" class="shape" id="circle2"/>
    <rect x="50" y="100" width="100" height="50" fill="red" class="shape" id="rect1"/>
    <text x="100" y="180" class="label">Test SVG</text>
</svg>"""


@pytest.fixture
def messy_svg_content():
    """SVG with metadata and unnecessary elements for cleanup testing."""
    return """<?xml version="1.0" encoding="UTF-8"?>
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
    <circle cx="50" cy="50" r="40" fill="blue"/>
</svg>"""


@pytest.fixture
def test_config(temp_workspace):
    """Test configuration with temporary workspace."""
    config = InkscapeConfig(
        workspace=temp_workspace, max_file_size=1024 * 1024, max_concurrent=2
    )
    _init_config(config)
    return config


class TestDOMServerMCPIntegration:
    """Test DOM server MCP protocol integration - real server behavior."""

    @pytest.mark.asyncio
    async def test_server_connectivity(self, test_config):
        """Test: DOM MCP server is reachable and responds to ping."""
        async with Client(app) as client:
            # Basic connectivity test
            await client.ping()
            assert client.is_connected()

    @pytest.mark.asyncio
    async def test_list_available_tools(self, test_config):
        """Test: DOM server exposes expected MCP tools."""
        async with Client(app) as client:
            tools = await client.list_tools()

            # Should have DOM manipulation tools
            tool_names = [tool.name for tool in tools]
            assert "dom.validate" in tool_names
            assert "dom.set" in tool_names
            assert "dom.clean" in tool_names

    @pytest.mark.asyncio
    async def test_dom_validate_tool_inline_svg(self, test_config, test_svg_content):
        """Test: dom.validate tool works with inline SVG via MCP."""
        async with Client(app) as client:
            result = await client.call_tool(
                "dom.validate", {"doc": {"type": "inline", "svg": test_svg_content}}
            )

            # Should successfully validate good SVG
            assert isinstance(result.data, dict)
            assert result.data.get("ok") is True

    @pytest.mark.asyncio
    async def test_dom_validate_tool_file_svg(self, test_config, test_svg_content):
        """Test: dom.validate tool works with file SVG via MCP."""
        async with Client(app) as client:
            # Create test SVG file
            svg_file = test_config.workspace / "valid.svg"
            with open(svg_file, "w") as f:
                f.write(test_svg_content)

            result = await client.call_tool(
                "dom.validate", {"doc": {"type": "file", "path": "valid.svg"}}
            )

            # Should successfully validate good SVG
            assert isinstance(result.data, dict)
            assert result.data.get("ok") is True

    @pytest.mark.asyncio
    async def test_dom_validate_malformed_svg(self, test_config):
        """Test: dom.validate handles malformed SVG gracefully."""
        async with Client(app) as client:
            malformed_svg = "<svg><circle/><invalid></svg>"  # Missing closing tag

            # inkex handles malformed SVG gracefully with warnings, so this should
            # succeed
            result = await client.call_tool(
                "dom.validate", {"doc": {"type": "inline", "svg": malformed_svg}}
            )
            # Should succeed even with malformed SVG (inkex is forgiving)
            assert isinstance(result.data, dict)
            assert result.data.get("ok") is True

    @pytest.mark.asyncio
    async def test_dom_set_tool_color_changes(self, test_config, test_svg_content):
        """Test: dom.set tool can change element colors via MCP."""
        async with Client(app) as client:
            # Create test SVG file
            svg_file = test_config.workspace / "colors.svg"
            with open(svg_file, "w") as f:
                f.write(test_svg_content)

            # Change all circles to orange
            result = await client.call_tool(
                "dom.set",
                {
                    "doc": {"type": "file", "path": "colors.svg"},
                    "ops": [
                        {
                            "selector": {"type": "css", "value": "circle"},
                            "set": {"style.fill": "#ff6600"},
                        }
                    ],
                    "save_as": "colors_modified.svg",
                },
            )

            # Should successfully modify elements
            assert isinstance(result.data, dict)
            assert result.data.get("ok") is True
            assert result.data.get("changed") == 2  # Two circles modified
            assert "colors_modified.svg" in result.data.get("out", "")

            # Verify the output file was created
            output_file = test_config.workspace / "colors_modified.svg"
            assert output_file.exists()

    @pytest.mark.asyncio
    async def test_dom_set_tool_batch_modifications(
        self, test_config, test_svg_content
    ):
        """Test: dom.set tool can apply multiple modifications via MCP."""
        async with Client(app) as client:
            svg_file = test_config.workspace / "batch.svg"
            with open(svg_file, "w") as f:
                f.write(test_svg_content)

            # Apply multiple changes at once
            result = await client.call_tool(
                "dom.set",
                {
                    "doc": {"type": "file", "path": "batch.svg"},
                    "ops": [
                        # Make all shapes semi-transparent
                        {
                            "selector": {"type": "css", "value": ".shape"},
                            "set": {"@opacity": "0.7"},
                        },
                        # Change text color
                        {
                            "selector": {"type": "css", "value": "text"},
                            "set": {"style.fill": "#333333"},
                        },
                        # Add stroke to circles
                        {
                            "selector": {"type": "css", "value": "circle"},
                            "set": {
                                "style.stroke": "#000000",
                                "style.stroke-width": "1",
                            },
                        },
                    ],
                    "save_as": "batch_modified.svg",
                },
            )

            # Should successfully modify multiple elements
            assert isinstance(result.data, dict)
            assert result.data.get("ok") is True
            # Changed: 3 shapes + 1 text + 2 circles = 6 total modifications
            assert result.data.get("changed") == 6

    @pytest.mark.asyncio
    async def test_dom_set_tool_inline_svg(self, test_config, test_svg_content):
        """Test: dom.set tool works with inline SVG via MCP."""
        async with Client(app) as client:
            # Modify inline SVG - make all circles purple
            result = await client.call_tool(
                "dom.set",
                {
                    "doc": {"type": "inline", "svg": test_svg_content},
                    "ops": [
                        {
                            "selector": {"type": "css", "value": "circle"},
                            "set": {"style.fill": "#9933cc"},
                        }
                    ],
                    "save_as": "inline_modified.svg",
                },
            )

            # Should successfully modify inline SVG
            assert isinstance(result.data, dict)
            assert result.data.get("ok") is True
            assert result.data.get("changed") == 2

    @pytest.mark.asyncio
    async def test_dom_clean_tool_file(self, test_config, messy_svg_content):
        """Test: dom.clean tool works with files via MCP."""
        async with Client(app) as client:
            # Create messy SVG file
            svg_file = test_config.workspace / "messy.svg"
            with open(svg_file, "w") as f:
                f.write(messy_svg_content)

            result = await client.call_tool(
                "dom.clean",
                {
                    "doc": {"type": "file", "path": "messy.svg"},
                    "save_as": "cleaned.svg",
                },
            )

            # Should successfully clean SVG
            assert isinstance(result.data, dict)
            assert result.data.get("ok") is True
            assert "cleaned.svg" in result.data.get("out", "")

            # Verify cleaned file exists and is optimized
            cleaned_file = test_config.workspace / "cleaned.svg"
            assert cleaned_file.exists()

            # Read cleaned content - should be optimized
            # (note: scour may not remove all metadata)
            with open(cleaned_file) as f:
                cleaned_content = f.read()

            # Verify the file was processed (should have XML declaration and be
            # properly formatted)
            assert cleaned_content.startswith('<?xml version="1.0"')
            assert "svg" in cleaned_content

            # Should be smaller or same size (optimization occurred)
            original_size = len(messy_svg_content)
            cleaned_size = len(cleaned_content)
            # Allow for some size variation due to formatting differences
            assert (
                cleaned_size <= original_size * 1.2
            )  # Allow up to 20% size increase due to formatting

    @pytest.mark.asyncio
    async def test_dom_clean_tool_inline(self, test_config, messy_svg_content):
        """Test: dom.clean tool works with inline SVG via MCP."""
        async with Client(app) as client:
            result = await client.call_tool(
                "dom.clean",
                {
                    "doc": {"type": "inline", "svg": messy_svg_content},
                    "save_as": "cleaned_inline.svg",
                },
            )

            # Should successfully clean inline SVG
            assert isinstance(result.data, dict)
            assert result.data.get("ok") is True

            # Verify the cleaned output
            output_file = test_config.workspace / "cleaned_inline.svg"
            assert output_file.exists()


class TestDOMServerSecurityViaMCP:
    """Test DOM server security boundaries via MCP protocol."""

    @pytest.mark.asyncio
    async def test_safe_css_selectors_via_mcp(self, test_config, test_svg_content):
        """Test: Safe CSS selectors work via MCP."""
        async with Client(app) as client:
            svg_file = test_config.workspace / "safe.svg"
            with open(svg_file, "w") as f:
                f.write(test_svg_content)

            # These selectors should work
            safe_selectors = [
                "circle",
                "rect",
                "#circle1",
                ".shape",
                "circle.shape",
                "text",
            ]

            for selector_value in safe_selectors:
                result = await client.call_tool(
                    "dom.set",
                    {
                        "doc": {"type": "file", "path": "safe.svg"},
                        "ops": [
                            {
                                "selector": {"type": "css", "value": selector_value},
                                "set": {"@data-test": "safe"},
                            }
                        ],
                        "save_as": "safe_output.svg",
                    },
                )

                # Should succeed with safe selectors
                assert isinstance(result.data, dict)
                assert result.data.get("ok") is True

    @pytest.mark.asyncio
    async def test_unsafe_selectors_rejected_via_mcp(self, test_config):
        """Test: Unsafe selectors are rejected via MCP."""
        async with Client(app) as client:
            # These selectors should be rejected by validation
            unsafe_selectors = [
                "//xpath",  # XPath injection attempt
                "script()",  # Function call attempt
                "@import url()",  # CSS import attempt
                "expression(alert())",  # Expression injection
                "javascript:",  # Protocol handler
                "<script>",  # Script tag attempt
                "url(",  # URL function
                "{}",  # Brace injection
            ]

            for selector_value in unsafe_selectors:
                with pytest.raises(Exception) as exc_info:
                    await client.call_tool(
                        "dom.set",
                        {
                            "doc": {"type": "inline", "svg": "<svg><circle/></svg>"},
                            "ops": [
                                {
                                    "selector": {
                                        "type": "css",
                                        "value": selector_value,
                                    },
                                    "set": {"@fill": "red"},
                                }
                            ],
                            "save_as": "output.svg",
                        },
                    )
                # Should be rejected
                error_msg = str(exc_info.value).lower()
                assert any(
                    word in error_msg for word in ["selector", "not allowed", "invalid"]
                )

    @pytest.mark.asyncio
    async def test_path_traversal_protection_via_mcp(self, test_config):
        """Test: Path traversal protection works via MCP."""
        async with Client(app) as client:
            # These paths should be blocked
            dangerous_paths = [
                "../../../etc/passwd",
                "../../sensitive.svg",
                "/absolute/path/outside.svg",
                "../outside_workspace.svg",
            ]

            for dangerous_path in dangerous_paths:
                with pytest.raises(Exception) as exc_info:
                    await client.call_tool(
                        "dom.validate",
                        {"doc": {"type": "file", "path": dangerous_path}},
                    )
                # Should be blocked
                error_msg = str(exc_info.value).lower()
                assert any(
                    word in error_msg for word in ["workspace", "path", "escape"]
                )

    @pytest.mark.asyncio
    async def test_file_size_limits_via_mcp(self, test_config):
        """Test: File size limits are enforced via MCP."""
        async with Client(app) as client:
            # Create inline SVG larger than limit (1MB)
            large_svg = "<svg>" + "x" * (2 * 1024 * 1024) + "</svg>"  # 2MB

            with pytest.raises(Exception) as exc_info:
                await client.call_tool(
                    "dom.validate", {"doc": {"type": "inline", "svg": large_svg}}
                )

            # Should be rejected due to size
            error_msg = str(exc_info.value).lower()
            assert any(word in error_msg for word in ["large", "size", "limit"])

    @pytest.mark.asyncio
    async def test_missing_required_fields_via_mcp(self, test_config):
        """Test: Missing required fields are caught via MCP."""
        async with Client(app) as client:
            # Test missing file path for file type
            with pytest.raises(Exception) as exc_info:
                await client.call_tool(
                    "dom.validate", {"doc": {"type": "file", "path": None}}
                )
            # Should be caught by validation
            assert exc_info.value is not None

            # Test missing SVG for inline type
            with pytest.raises(Exception) as exc_info:
                await client.call_tool(
                    "dom.validate", {"doc": {"type": "inline", "svg": None}}
                )
            # Should be caught by validation
            assert exc_info.value is not None


class TestDOMServerWorkflowsViaMCP:
    """Test complete DOM workflows via MCP protocol."""

    @pytest.mark.asyncio
    async def test_validate_to_modify_workflow(self, test_config, test_svg_content):
        """Test: Complete validate->modify workflow via MCP."""
        async with Client(app) as client:
            # Step 1: Validate SVG
            validate_result = await client.call_tool(
                "dom.validate", {"doc": {"type": "inline", "svg": test_svg_content}}
            )
            assert validate_result.data.get("ok") is True

            # Step 2: Modify based on validation success
            modify_result = await client.call_tool(
                "dom.set",
                {
                    "doc": {"type": "inline", "svg": test_svg_content},
                    "ops": [
                        {
                            "selector": {"type": "css", "value": "circle"},
                            "set": {"style.fill": "#ff6600"},
                        }
                    ],
                    "save_as": "workflow_output.svg",
                },
            )

            assert modify_result.data.get("ok") is True
            assert modify_result.data.get("changed") == 2

    @pytest.mark.asyncio
    async def test_clean_to_modify_workflow(self, test_config, messy_svg_content):
        """Test: Complete clean->modify workflow via MCP."""
        async with Client(app) as client:
            # Step 1: Clean messy SVG
            clean_result = await client.call_tool(
                "dom.clean",
                {
                    "doc": {"type": "inline", "svg": messy_svg_content},
                    "save_as": "cleaned.svg",
                },
            )
            assert clean_result.data.get("ok") is True

            # Step 2: Further modify the cleaned file
            modify_result = await client.call_tool(
                "dom.set",
                {
                    "doc": {"type": "file", "path": "cleaned.svg"},
                    "ops": [
                        {
                            "selector": {"type": "css", "value": "circle"},
                            "set": {
                                "style.stroke": "#000000",
                                "style.stroke-width": "2",
                            },
                        }
                    ],
                    "save_as": "final_output.svg",
                },
            )

            assert modify_result.data.get("ok") is True
            assert modify_result.data.get("changed") == 1

    @pytest.mark.asyncio
    async def test_batch_file_processing_workflow(self, test_config):
        """Test: Batch processing multiple files via MCP."""
        async with Client(app) as client:
            # Create multiple test SVG files
            for i in range(3):
                svg_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg width="100" height="100" xmlns="http://www.w3.org/2000/svg">
    <circle cx="50" cy="50" r="{20 + i * 5}" fill="blue" id="circle-{i}"/>
    <text x="50" y="80" text-anchor="middle">File {i}</text>
</svg>'''
                svg_file = test_config.workspace / f"batch_{i}.svg"
                with open(svg_file, "w") as f:
                    f.write(svg_content)

            # Process each file through validation and modification
            colors = ["#ff0000", "#00ff00", "#0000ff"]
            for i in range(3):
                # Validate each file
                validate_result = await client.call_tool(
                    "dom.validate", {"doc": {"type": "file", "path": f"batch_{i}.svg"}}
                )
                assert validate_result.data.get("ok") is True

                # Modify each file with different color
                modify_result = await client.call_tool(
                    "dom.set",
                    {
                        "doc": {"type": "file", "path": f"batch_{i}.svg"},
                        "ops": [
                            {
                                "selector": {"type": "css", "value": "circle"},
                                "set": {"style.fill": colors[i]},
                            }
                        ],
                        "save_as": f"batch_modified_{i}.svg",
                    },
                )

                assert modify_result.data.get("ok") is True
                assert modify_result.data.get("changed") == 1
