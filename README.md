# Inkscape MCP Server

A secure, hardened MCP (Model Context Protocol) server for Inkscape operations, providing both CLI actions and DOM manipulation capabilities.

## Features

- **CLI Actions**: Execute Inkscape command-line actions (export, transforms, path operations)
- **DOM Manipulation**: Direct SVG DOM editing with CSS selectors  
- **Security Hardened**: Workspace-scoped paths, size limits, action allowlists
- **Async Support**: Non-blocking operations with rate limiting
- **Atomic Operations**: Safe file writes and process cleanup

## Installation

### From PyPI (when published)

```bash
# Using uv (recommended)
uv add inkscape-mcp

# Using pip
pip install inkscape-mcp
```

### From Source

```bash
git clone https://github.com/yourusername/inkscape-mcp
cd inkscape-mcp

# Quick development setup
./scripts/dev-setup

# Or manual setup
uv sync --dev         # Install with dev dependencies
uv build              # Build distribution packages
```

## Usage

### As Individual Servers

Start the CLI server:
```bash
inkscape-mcp-cli
```

Start the DOM server:
```bash
inkscape-mcp-dom  
```

Start combined server (both CLI and DOM tools):
```bash
inkscape-mcp
```

### Configuration

Configure via environment variables:

```bash
export INKS_WORKSPACE="./my-workspace"  # Default: ./inkspace
export INKS_MAX_FILE="104857600"        # Default: 50MB
export INKS_TIMEOUT="120"               # Default: 60s
export INKS_MAX_CONC="8"                # Default: 4
```

### MCP Client Integration

Add to your MCP client configuration (e.g., Claude Desktop):

```json
{
  "mcpServers": {
    "inkscape-mcp": {
      "command": "inkscape-mcp",
      "env": {
        "INKS_WORKSPACE": "/path/to/workspace",
        "INKS_MAX_FILE": "52428800"
      }
    }
  }
}
```

## Available Tools

### CLI Tools (`inkscape-mcp-cli`)

- `action_list` - List all available Inkscape actions
- `action_run` - Execute Inkscape actions on documents

### DOM Tools (`inkscape-mcp-dom`)

- `dom_validate` - Validate SVG document structure
- `dom_set` - Set attributes/styles using CSS selectors
- `dom_clean` - Clean/optimize SVG using scour

## Examples

### Export SVG to PNG
```python
# Via MCP client
await action_run({
    "doc": {"type": "file", "path": "input.svg"},
    "export": {"type": "png", "out": "output.png", "dpi": 300}
})
```

### Modify SVG Elements
```python
# Change fill color of all circles
await dom_set({
    "doc": {"type": "file", "path": "input.svg"},
    "ops": [{
        "selector": {"type": "css", "value": "circle"},
        "set": {"style.fill": "#ff6600"}
    }],
    "save_as": "modified.svg"
})
```

### Path Operations
```python
# Union selected paths
await action_run({
    "doc": {"type": "file", "path": "input.svg"},
    "actions": ["select-all", "path-union"]
})
```

## Security Features

- **Workspace Scoping**: All file operations restricted to configured workspace
- **Size Limits**: Configurable file size caps prevent resource exhaustion  
- **Action Allowlist**: Only explicitly approved Inkscape actions permitted
- **Safe Selectors**: CSS selectors limited to safe subset (no XPath injection)
- **Process Isolation**: Robust subprocess management with timeouts and cleanup
- **Atomic Writes**: Temporary files with atomic rename prevent corruption
- **Rate Limiting**: Concurrent operation limits prevent resource abuse

## Development

### Setup Development Environment

```bash
# Clone and setup
git clone https://github.com/yourusername/inkscape-mcp
cd inkscape-mcp

# Quick setup using just (recommended)
just setup

# Or manual setup
uv sync --dev         # Install with dev dependencies
```

### Development Workflow

This project uses [`just`](https://github.com/casey/just) for task running:

```bash
just                  # Show available commands
just setup           # Development setup
just test            # Run tests (64 integration tests)
just lint            # Run linting with ruff
just format          # Format code with black + ruff
just type-check      # Run type checking with ty
just check           # Run all checks (lint + type + test)
just build           # Build distribution packages
just clean           # Clean build artifacts
```

### Individual Server Testing

```bash
just test-cli        # Test CLI server only
just test-dom        # Test DOM server only  
just test-combined   # Test combined server only
```

## Claude Code Integration

### Install the Package

```bash
# Install from your local development copy
just build
uv pip install dist/*.whl

# Or install in development mode
uv sync --dev
```

### Configure Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "inkscape-mcp": {
      "command": "inkscape-mcp",
      "args": [],
      "env": {
        "INKS_WORKSPACE": "/Users/yourname/inkscape-workspace",
        "INKS_MAX_FILE": "52428800",
        "INKS_TIMEOUT": "120"
      }
    }
  }
}
```

### Testing with Claude Code

1. **Setup workspace**:
   ```bash
   mkdir -p ~/inkscape-workspace
   cd ~/inkscape-workspace
   
   # Create a test SVG file
   cat > test.svg << 'EOF'
   <?xml version="1.0" encoding="UTF-8"?>
   <svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
     <circle cx="50" cy="50" r="30" fill="blue" class="shape"/>
     <rect x="20" y="20" width="20" height="20" fill="red"/>
   </svg>
   EOF
   ```

2. **Restart Claude Desktop** after updating config

3. **Test in Claude Code**:
   ```
   Can you list available Inkscape actions?
   
   Can you validate this SVG: /Users/yourname/inkscape-workspace/test.svg
   
   Change all circles to red color in test.svg and save as test-red.svg
   
   Export test.svg to PNG at 300 DPI
   ```

### Entry Points Available

Three MCP servers are available:

- **`inkscape-mcp`** - Combined server (5 tools: all CLI + DOM)
- **`inkscape-mcp-cli`** - CLI only (2 tools: action_list, action_run)  
- **`inkscape-mcp-dom`** - DOM only (3 tools: dom_validate, dom_set, dom_clean)

### Troubleshooting

**Server not found:**
```bash
# Check if entry points are installed
which inkscape-mcp
uv run which inkscape-mcp
```

**Permission errors:**
```bash
# Ensure workspace directory exists and is writable
mkdir -p ~/inkscape-workspace
chmod 755 ~/inkscape-workspace
```

**Inkscape not found:**
```bash
# Install Inkscape
brew install inkscape  # macOS
# or check if already installed
which inkscape
```

### Manual Server Testing

If you need to test servers manually (without Claude Code):

```bash
# Test entry points are working
which inkscape-mcp
which inkscape-mcp-cli  
which inkscape-mcp-dom

# Test servers start correctly
inkscape-mcp --help      # Should show MCP server info
inkscape-mcp-cli --help  # CLI server 
inkscape-mcp-dom --help  # DOM server

# Or run directly with Python
uv run python -m inkscape_mcp.cli_server
uv run python -m inkscape_mcp.dom_server  
uv run python -m inkscape_mcp.combined
```

## Requirements

- Python 3.9+
- Inkscape installed and available in PATH
- Dependencies: fastmcp, pydantic, anyio, filelock, inkex, scour

## License

MIT License - see LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass and code is formatted
5. Submit a pull request

## Security

This server is designed for trusted environments. While it includes multiple security hardening measures, it should not be exposed to untrusted networks or users without additional authentication and authorization layers.