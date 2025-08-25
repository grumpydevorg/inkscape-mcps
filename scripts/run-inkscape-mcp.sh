#!/bin/bash

# Inkscape MCP Server startup script for Claude Code
# This ensures proper environment setup

set -e  # Exit on any error

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Set up workspace directory (create if it doesn't exist)
export INKS_WORKSPACE="${INKS_WORKSPACE:-$HOME/inkscape-workspace}"
mkdir -p "$INKS_WORKSPACE"

# Check if uv is available
if ! command -v uv &> /dev/null; then
    echo "Error: uv is not installed or not in PATH" >&2
    echo "Please install uv: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
    exit 1
fi

# Check if we're in the right directory
if [[ ! -f "src/inkscape_mcp/combined.py" ]]; then
    echo "Error: Cannot find inkscape_mcp source files" >&2
    echo "Please run this script from the inkscape-mcps directory" >&2
    exit 1
fi

# Run the MCP server
echo "Starting Inkscape MCP server..." >&2
echo "Workspace: $INKS_WORKSPACE" >&2
exec uv run python -m inkscape_mcp.combined