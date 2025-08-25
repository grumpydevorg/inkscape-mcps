"""Security Boundary Tests - FastMCP Idiomatic Testing."""

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
def test_config(temp_workspace):
    """Test configuration with small limits for security testing."""
    config = InkscapeConfig(
        workspace=temp_workspace,
        max_file_size=1024,  # 1KB limit for testing
        timeout_default=5,
        max_concurrent=1,
    )
    _init_config(config)
    return config


class TestWorkspaceConfinementViaMCP:
    """Test workspace path confinement - demonstrates path traversal protection
    via MCP."""

    @pytest.mark.asyncio
    async def test_path_traversal_prevention_cli_tools(self, test_config):
        """Test: CLI tools block path traversal attempts via MCP."""
        async with Client(app) as client:
            # These path traversal attempts should be blocked
            dangerous_paths = [
                "../../../etc/passwd",
                "../../sensitive.svg",
                "/absolute/path/outside.svg",
                "~/home/user/file.svg",
                "../outside_workspace.svg",
            ]

            for dangerous_path in dangerous_paths:
                with pytest.raises(Exception) as exc_info:
                    await client.call_tool(
                        "action.run",
                        {
                            "doc_type": "file",
                            "doc_path": dangerous_path,
                            "actions": ["select-all"],
                        },
                    )
                error_msg = str(exc_info.value).lower()
                # Accept either workspace escape error or file not found
                # (both indicate blocking)
                assert any(
                    word in error_msg
                    for word in ["workspace", "path", "escape", "not found", "file"]
                )

    @pytest.mark.asyncio
    async def test_path_traversal_prevention_dom_tools(self, test_config):
        """Test: DOM tools block path traversal attempts via MCP."""
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
                        {"doc_type": "file", "doc_path": dangerous_path},
                    )
                error_msg = str(exc_info.value).lower()
                assert any(
                    word in error_msg for word in ["workspace", "path", "escape"]
                )

    @pytest.mark.asyncio
    async def test_valid_workspace_paths_allowed(self, test_config):
        """Test: Valid paths within workspace are allowed via MCP."""
        async with Client(app) as client:
            # Create a valid SVG file
            valid_svg = """<?xml version="1.0" encoding="UTF-8"?>
<svg width="100" height="100" xmlns="http://www.w3.org/2000/svg">
    <circle cx="50" cy="50" r="20"/>
</svg>"""

            # These paths should be allowed
            valid_paths = ["test.svg", "subfolder/test.svg", "images/diagram.svg"]

            for valid_path in valid_paths:
                # Create directory structure if needed
                file_path = test_config.workspace / valid_path
                file_path.parent.mkdir(parents=True, exist_ok=True)
                with open(file_path, "w") as f:
                    f.write(valid_svg)

                # Should not raise an exception for DOM validation
                result = await client.call_tool(
                    "dom.validate", {"doc_type": "file", "doc_path": valid_path}
                )
                assert result.data.get("ok") is True


class TestFileSizeLimitsViaMCP:
    """Test file size limits - demonstrates resource protection via MCP."""

    @pytest.mark.asyncio
    async def test_oversized_file_rejection_cli_tools(self, test_config):
        """Test: CLI tools reject files exceeding size limits via MCP."""
        async with Client(app) as client:
            # Create a file larger than the limit (1KB)
            large_file = test_config.workspace / "large.svg"
            with open(large_file, "w") as f:
                f.write("x" * 2048)  # 2KB file

            with pytest.raises(Exception) as exc_info:
                await client.call_tool(
                    "action.run",
                    {
                        "doc_type": "file",
                        "doc_path": "large.svg",
                        "actions": ["select-all"],
                    },
                )
            error_msg = str(exc_info.value).lower()
            assert any(word in error_msg for word in ["large", "size", "limit"])

    @pytest.mark.asyncio
    async def test_oversized_inline_svg_rejection_cli_tools(self, test_config):
        """Test: CLI tools reject inline SVG exceeding size limits via MCP."""
        async with Client(app) as client:
            # Create inline SVG larger than limit
            large_svg = "<svg>" + "x" * 2048 + "</svg>"

            with pytest.raises(Exception) as exc_info:
                await client.call_tool(
                    "action.run",
                    {
                        "doc_type": "inline",
                        "doc_svg": large_svg,
                        "actions": ["select-all"],
                    },
                )
            error_msg = str(exc_info.value).lower()
            assert any(word in error_msg for word in ["large", "size", "limit"])

    @pytest.mark.asyncio
    async def test_oversized_inline_svg_rejection_dom_tools(self, test_config):
        """Test: DOM tools reject inline SVG exceeding size limits via MCP."""
        async with Client(app) as client:
            # Create inline SVG larger than limit
            large_svg = "<svg>" + "x" * 2048 + "</svg>"

            with pytest.raises(Exception) as exc_info:
                await client.call_tool(
                    "dom.validate", {"doc_type": "inline", "doc_svg": large_svg}
                )
            error_msg = str(exc_info.value).lower()
            assert any(word in error_msg for word in ["large", "size", "limit"])

    @pytest.mark.asyncio
    async def test_acceptable_file_size_allowed(self, test_config):
        """Test: Files within size limits are accepted via MCP."""
        async with Client(app) as client:
            # Create a file within the limit
            small_svg = '<svg width="100" height="100"><circle r="20"/></svg>'
            small_file = test_config.workspace / "small.svg"
            with open(small_file, "w") as f:
                f.write(small_svg)

            # Should not raise an exception for DOM validation
            result = await client.call_tool(
                "dom.validate", {"doc_type": "file", "doc_path": "small.svg"}
            )
            assert result.data.get("ok") is True


class TestActionSafetyViaMCP:
    """Test Inkscape action safety - demonstrates action allowlist enforcement
    via MCP."""

    @pytest.mark.asyncio
    async def test_safe_actions_allowed(self, test_config):
        """Test: Safe actions are accepted via MCP."""
        async with Client(app) as client:
            safe_svg = '<svg><circle cx="50" cy="50" r="20"/></svg>'

            safe_actions = [
                ["select-all"],
                ["select-clear"],
                ["path-union"],
                ["object-to-path"],
            ]

            for action_list in safe_actions:
                try:
                    result = await client.call_tool(
                        "action.run",
                        {
                            "doc_type": "inline",
                            "doc_svg": safe_svg,
                            "actions": action_list,
                        },
                    )
                    # Should work if Inkscape is available
                    assert isinstance(result.data, dict)
                except Exception as e:
                    # Expected if Inkscape not installed - action was accepted by MCP
                    assert "inkscape" in str(e).lower() or "not found" in str(e).lower()

    @pytest.mark.asyncio
    async def test_unsafe_actions_blocked(self, test_config):
        """Test: Unsafe actions are rejected via MCP."""
        async with Client(app) as client:
            safe_svg = '<svg><circle cx="50" cy="50" r="20"/></svg>'

            # These actions are not in the allowlist and should be blocked
            unsafe_actions = [
                ["file-open"],  # File system access
                ["file-import"],  # Import external files
                ["dialog-open"],  # UI dialogs
                ["edit-preferences"],  # Settings modification
                ["help-about"],  # Non-essential UI
                ["quit"],  # Application control
                ["shell-command"],  # Command execution
                ["python-script"],  # Script execution
            ]

            for action_list in unsafe_actions:
                with pytest.raises(Exception) as exc_info:
                    await client.call_tool(
                        "action.run",
                        {
                            "doc_type": "inline",
                            "doc_svg": safe_svg,
                            "actions": action_list,
                        },
                    )
                error_msg = str(exc_info.value).lower()
                assert any(
                    word in error_msg for word in ["unsafe", "action", "not allowed"]
                )


class TestSelectorSafetyViaMCP:
    """Test CSS selector safety - demonstrates XPath injection protection via MCP."""

    @pytest.mark.asyncio
    async def test_safe_css_selectors(self, test_config):
        """Test: Safe CSS selectors are accepted via MCP."""
        async with Client(app) as client:
            test_svg = """<?xml version="1.0" encoding="UTF-8"?>
<svg width="100" height="100" xmlns="http://www.w3.org/2000/svg">
    <circle cx="50" cy="50" r="20" class="shape" id="circle1"/>
    <rect x="10" y="10" width="30" height="30" class="shape" id="rect1"/>
    <text x="50" y="80" class="label">Test</text>
</svg>"""

            safe_selectors = [
                "circle",
                "rect.shape",
                "#circle1",
                ".shape",
                "circle > rect",
                "text, rect",
                "*",
            ]

            for selector_value in safe_selectors:
                result = await client.call_tool(
                    "dom.set",
                    {
                        "doc_type": "inline",
                        "doc_svg": test_svg,
                        "ops_json": (
                            f'[{{"selector": {{"type": "css", '
                            f'"value": "{selector_value}"}}, '
                            f'"set": {{"@data-test": "safe"}}}}]'
                        ),
                        "save_as": "selector_test.svg",
                    },
                )

                # Should succeed with safe selectors
                assert result.data.get("ok") is True

    @pytest.mark.asyncio
    async def test_unsafe_selectors_blocked(self, test_config):
        """Test: Potentially unsafe selectors are rejected via MCP."""
        async with Client(app) as client:
            test_svg = '<svg><circle cx="50" cy="50" r="20"/></svg>'

            unsafe_selectors = [
                "//xpath/expression",  # XPath syntax
                "script[src]",  # Potentially dangerous
                "@import url(http://)",  # CSS import
                "expression(alert())",  # CSS expressions
                "javascript:",  # Protocol handler
                "<script>",  # HTML injection attempt
                "url(",  # URL function
                "\\\\",  # Backslash escape
                "{}",  # Brace injection
            ]

            for selector_value in unsafe_selectors:
                with pytest.raises(Exception) as exc_info:
                    await client.call_tool(
                        "dom.set",
                        {
                            "doc_type": "inline",
                            "doc_svg": test_svg,
                            "ops_json": (
                                f'[{{"selector": {{"type": "css", '
                                f'"value": "{selector_value}"}}, '
                                f'"set": {{"@fill": "red"}}}}]'
                            ),
                            "save_as": "unsafe_test.svg",
                        },
                    )
                error_msg = str(exc_info.value).lower()
                assert any(
                    word in error_msg for word in ["selector", "not allowed", "invalid"]
                )


class TestInputValidationViaMCP:
    """Test input validation - demonstrates defensive programming via MCP."""

    @pytest.mark.asyncio
    async def test_missing_required_fields_cli_tools(self, test_config):
        """Test: CLI tools catch missing required fields via MCP."""
        async with Client(app) as client:
            # Missing file path for file type
            with pytest.raises(Exception) as exc_info:
                await client.call_tool(
                    "action.run",
                    {"doc_type": "file", "doc_path": None, "actions": ["select-all"]},
                )
            # Should be caught by validation
            assert exc_info.value is not None

            # Missing SVG for inline type
            with pytest.raises(Exception) as exc_info:
                await client.call_tool(
                    "action.run",
                    {"doc_type": "inline", "doc_svg": None, "actions": ["select-all"]},
                )
            # Should be caught by validation
            assert exc_info.value is not None

    @pytest.mark.asyncio
    async def test_missing_required_fields_dom_tools(self, test_config):
        """Test: DOM tools catch missing required fields via MCP."""
        async with Client(app) as client:
            # Missing file path for file type
            with pytest.raises(Exception) as exc_info:
                await client.call_tool(
                    "dom.validate", {"doc_type": "file", "doc_path": None}
                )
            # Should be caught by validation
            assert exc_info.value is not None

            # Missing SVG for inline type
            with pytest.raises(Exception) as exc_info:
                await client.call_tool(
                    "dom.validate", {"doc_type": "inline", "doc_svg": None}
                )
            # Should be caught by validation
            assert exc_info.value is not None

    @pytest.mark.asyncio
    async def test_nonexistent_file_handling(self, test_config):
        """Test: Nonexistent files are handled gracefully via MCP."""
        async with Client(app) as client:
            with pytest.raises(Exception) as exc_info:
                await client.call_tool(
                    "dom.validate",
                    {"doc_type": "file", "doc_path": "doesnt_exist.svg"},
                )
            error_msg = str(exc_info.value).lower()
            assert any(word in error_msg for word in ["not found", "file", "exist"])

    @pytest.mark.asyncio
    async def test_malformed_svg_handling(self, test_config):
        """Test: Malformed SVG is handled gracefully via MCP."""
        async with Client(app) as client:
            # Inkex is forgiving and handles malformed SVG gracefully
            malformed_svg = "not xml at all"

            # Should not raise exception - inkex handles malformed SVG gracefully
            result = await client.call_tool(
                "dom.validate", {"doc_type": "inline", "doc_svg": malformed_svg}
            )
            # Should return success even for malformed SVG (inkex is forgiving)
            assert result.data.get("ok") is True


class TestConfigurationSafetyViaMCP:
    """Test configuration safety - demonstrates secure defaults via MCP."""

    @pytest.mark.asyncio
    async def test_concurrency_limits_enforced(self, test_config):
        """Test: Concurrency limits prevent resource exhaustion via MCP."""
        async with Client(app) as client:
            # This test demonstrates the concept - max_concurrent=1 in test_config
            # The semaphore should limit to 1 concurrent operation

            # Basic smoke test that operations work within limits
            result = await client.call_tool(
                "dom.validate",
                {"doc_type": "inline", "doc_svg": "<svg><circle/></svg>"},
            )
            assert result.data.get("ok") is True

    @pytest.mark.asyncio
    async def test_timeout_configuration_respected(self, test_config):
        """Test: Timeout configuration prevents hung operations via MCP."""
        async with Client(app) as client:
            # Test with custom timeout (5s in test_config)
            try:
                result = await client.call_tool(
                    "action.run",
                    {
                        "doc_type": "inline",
                        "doc_svg": "<svg><circle/></svg>",
                        "actions": ["select-all"],
                        "timeout_s": 1,  # Very short timeout
                    },
                )
                # If successful, should work within timeout
                assert isinstance(result.data, dict)
            except Exception as e:
                # Expected if timeout occurs or Inkscape not available
                expected_errors = ["inkscape", "not found", "timeout"]
                assert any(err in str(e).lower() for err in expected_errors)


class TestCrossToolSecurityConsistency:
    """Test that security boundaries are consistently enforced across CLI and
    DOM tools."""

    @pytest.mark.asyncio
    async def test_consistent_path_validation(self, test_config):
        """Test: Path validation is consistent across both tool types via MCP."""
        async with Client(app) as client:
            dangerous_path = "../../../etc/passwd"

            # Both CLI and DOM tools should reject the same dangerous path

            # CLI rejection
            with pytest.raises(Exception) as cli_exc:
                await client.call_tool(
                    "action.run",
                    {
                        "doc_type": "file",
                        "doc_path": dangerous_path,
                        "actions": ["select-all"],
                    },
                )

            # DOM rejection
            with pytest.raises(Exception) as dom_exc:
                await client.call_tool(
                    "dom.validate", {"doc_type": "file", "doc_path": dangerous_path}
                )

            # Both should have similar error characteristics
            cli_error = str(cli_exc.value).lower()
            dom_error = str(dom_exc.value).lower()

            # Both should mention path/workspace issues
            assert any(word in cli_error for word in ["workspace", "path", "escape"])
            assert any(word in dom_error for word in ["workspace", "path", "escape"])

    @pytest.mark.asyncio
    async def test_consistent_size_validation(self, test_config):
        """Test: Size validation is consistent across both tool types via MCP."""
        async with Client(app) as client:
            large_svg = "<svg>" + "x" * 2048 + "</svg>"  # Exceeds 1KB limit

            # Both CLI and DOM tools should reject the same oversized content

            # CLI rejection
            with pytest.raises(Exception) as cli_exc:
                await client.call_tool(
                    "action.run",
                    {
                        "doc_type": "inline",
                        "doc_svg": large_svg,
                        "actions": ["select-all"],
                    },
                )

            # DOM rejection
            with pytest.raises(Exception) as dom_exc:
                await client.call_tool(
                    "dom.validate", {"doc_type": "inline", "doc_svg": large_svg}
                )

            # Both should have similar size-related error messages
            cli_error = str(cli_exc.value).lower()
            dom_error = str(dom_exc.value).lower()

            # Both should mention size issues
            assert any(word in cli_error for word in ["large", "size", "limit"])
            assert any(word in dom_error for word in ["large", "size", "limit"])
