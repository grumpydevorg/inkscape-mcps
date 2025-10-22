"""Combined Inkscape MCP server with both CLI and DOM functionality."""

import logging
from collections.abc import Callable
from typing import Any, TypeVar, cast

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError

from . import cli_server, dom_server
from .auto_flatten import flatten_pydantic_params
from .config import InkscapeConfig

# Setup logging
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastMCP("inkscape-combined")

# Type-safe decorator cast for ty compatibility
F = TypeVar("F", bound=Callable[..., object])
tool: Callable[[str], Callable[[F], F]] = cast(Any, app.tool)

# Global config
CFG: InkscapeConfig | None = None


def _init_config(config: InkscapeConfig | None = None) -> None:
    """Initialize global configuration."""
    global CFG
    CFG = config or InkscapeConfig()


# Re-export CLI tools
@tool("action_list")
async def action_list(ctx: Context) -> dict:
    """List available Inkscape actions."""
    if CFG is None:
        raise ToolError("Config not initialized")
    cli_server._init_config(CFG)
    return await cli_server._action_list_impl()


@tool("action_run")
@flatten_pydantic_params
async def action_run(
    ctx: Context,
    doc: cli_server.Doc,
    actions: list[str] | None = None,
    export: cli_server.Export | None = None,
    timeout_s: int | None = None,
) -> dict:
    """Run Inkscape actions on a document."""
    logger.debug(f"action_run called with doc: {doc} (type: {type(doc)})")
    logger.debug(f"actions: {actions}, export: {export}, timeout_s: {timeout_s}")
    if CFG is None:
        raise ToolError("Config not initialized")
    cli_server._init_config(CFG)
    return await cli_server._action_run_impl(doc, actions, export, timeout_s)


# Re-export DOM tools
@tool("dom_validate")
@flatten_pydantic_params
async def dom_validate(ctx: Context, doc: dom_server.Doc) -> dict:
    """Validate SVG document structure."""
    logger.debug(f"dom_validate called with doc: {doc} (type: {type(doc)})")
    if CFG is None:
        raise ToolError("Config not initialized")
    dom_server._init_config(CFG)
    return await dom_server._dom_validate_impl(doc)


@tool("dom_set")
@flatten_pydantic_params
async def dom_set(
    ctx: Context, doc: dom_server.Doc, ops: list[dom_server.SetOp], save_as: str
) -> dict:
    """Set attributes/styles on DOM elements."""
    if CFG is None:
        raise ToolError("Config not initialized")
    dom_server._init_config(CFG)
    return await dom_server._dom_set_impl(doc, ops, save_as)


@tool("dom_clean")
@flatten_pydantic_params
async def dom_clean(ctx: Context, doc: dom_server.Doc, save_as: str) -> dict:
    """Clean SVG using scour optimizer."""
    if CFG is None:
        raise ToolError("Config not initialized")
    dom_server._init_config(CFG)
    return await dom_server._dom_clean_impl(doc, save_as)


def main(config: InkscapeConfig | None = None) -> None:
    """Main entry point for combined server."""
    _init_config(config)
    app.run()


if __name__ == "__main__":
    main()
