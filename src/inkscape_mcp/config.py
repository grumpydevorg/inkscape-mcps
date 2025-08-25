"""Configuration management for Inkscape MCP servers."""

import os
from pathlib import Path

from pydantic import BaseModel, Field


class InkscapeConfig(BaseModel):
    """Configuration for Inkscape MCP servers."""

    workspace: Path = Field(
        default_factory=lambda: Path(
            os.getenv("INKS_WORKSPACE", "./inkspace")
        ).resolve()
    )
    max_file_size: int = Field(
        default_factory=lambda: int(os.getenv("INKS_MAX_FILE", str(50 * 1024 * 1024)))
    )
    timeout_default: int = Field(
        default_factory=lambda: int(os.getenv("INKS_TIMEOUT", "60"))
    )
    max_concurrent: int = Field(
        default_factory=lambda: int(os.getenv("INKS_MAX_CONC", "4"))
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.workspace.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls, prefix: str = "INKS_") -> "InkscapeConfig":
        """Create config from environment variables with given prefix."""
        return cls(
            workspace=Path(os.getenv(f"{prefix}WORKSPACE", "./inkspace")).resolve(),
            max_file_size=int(os.getenv(f"{prefix}MAX_FILE", str(50 * 1024 * 1024))),
            timeout_default=int(os.getenv(f"{prefix}TIMEOUT", "60")),
            max_concurrent=int(os.getenv(f"{prefix}MAX_CONC", "4")),
        )


# Global default config instance
default_config = InkscapeConfig()
