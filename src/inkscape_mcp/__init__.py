"""Inkscape MCP Server - MCP server for Inkscape CLI and DOM operations."""

__version__ = "0.1.0"
__author__ = "Your Name"
__email__ = "your.email@example.com"

from . import cli_server, combined, config, dom_server

__all__ = ["cli_server", "dom_server", "combined", "config"]
