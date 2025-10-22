"""CLI-based Inkscape MCP server for actions and exports."""

import os
import platform
import signal
import subprocess
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, TypeVar, cast

import anyio
from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError, ValidationError
from filelock import FileLock
from pydantic import BaseModel, Field, field_validator

from .config import InkscapeConfig

app = FastMCP("inkscape-cli")

# Type-safe decorator cast for ty compatibility
F = TypeVar("F", bound=Callable[..., object])
tool: Callable[[str], Callable[[F], F]] = cast(Any, app.tool)

# Global config and semaphore
CFG: InkscapeConfig | None = None
SEM: anyio.Semaphore | None = None


def _init_config(config: InkscapeConfig | None = None) -> None:
    """Initialize global configuration and semaphore."""
    global CFG, SEM
    CFG = config or InkscapeConfig()
    SEM = anyio.Semaphore(CFG.max_concurrent)


def _ensure_in_workspace(p: Path) -> Path:
    """Ensure path is within workspace."""
    if CFG is None:
        raise ToolError("Config not initialized")

    # Resolve both paths to handle symlinks consistently
    # (e.g., /var -> /private/var on macOS)
    workspace_resolved = CFG.workspace.resolve()
    p_resolved = (CFG.workspace / p).resolve() if not p.is_absolute() else p.resolve()

    if not (
        p_resolved == workspace_resolved
        or str(p_resolved).startswith(str(workspace_resolved) + os.sep)
    ):
        raise ValidationError("Path escapes workspace")
    return p_resolved


def _check_size(p: Path) -> None:
    """Check if file size is within limits."""
    if CFG is None:
        raise ToolError("Config not initialized")

    try:
        if p.stat().st_size > CFG.max_file_size:
            raise ValidationError(f"File too large: {p.stat().st_size}")
    except FileNotFoundError as e:
        raise ValidationError("File not found") from e


# Explicit allowlist of safe actions
SAFE_ACTIONS = {
    "select-all",
    "select-clear",
    "select-by-id",
    "select-by-class",
    "select-by-element",
    "path-union",
    "path-difference",
    "path-intersection",
    "path-division",
    "path-exclusion",
    "path-simplify",
    "object-to-path",
    "object-stroke-to-path",
    "selection-group",
    "selection-ungroup",
    "export-area-page",
    "export-area-drawing",
    "export-type",
    "export-filename",
    "export-dpi",
    "export-do",
    "file-save",
    "file-close",
    "transform-translate",
    "transform-scale",
    "transform-rotate",
    "query-x",
    "query-y",
    "query-width",
    "query-height",
    "query-all",
}


def _is_safe_action(a: str) -> bool:
    """Check if action is in the safe allowlist."""
    aid = a.split(":", 1)[0]
    return aid in SAFE_ACTIONS


class Doc(BaseModel):
    """Document specification."""

    type: Literal["file", "inline"]
    path: str | None = None
    svg: str | None = None


class Export(BaseModel):
    """Export specification."""

    type: Literal["png", "pdf", "svg"]
    out: str
    dpi: int | None = None
    area: Literal["page", "drawing"] = "page"


class RunArgs(BaseModel):
    """Arguments for running Inkscape actions."""

    doc: Doc
    actions: list[str] = Field(default_factory=list)
    export: Export | None = None
    timeout_s: int | None = None

    @field_validator("actions")
    @classmethod
    def validate_actions(cls, v: list[str]) -> list[str]:
        """Validate that all actions are safe."""
        for a in v:
            if not _is_safe_action(a):
                raise ValueError(f"Unsafe action: {a}")
        return v


def _write_inline(svg: str) -> Path:
    """Write inline SVG to temporary file."""
    if CFG is None:
        raise ToolError("Config not initialized")

    if svg is None:
        raise ValidationError("Missing inline SVG")
    if len(svg.encode("utf-8")) > CFG.max_file_size:
        raise ValidationError("Inline SVG too large")

    p = CFG.workspace / f"inline-{uuid.uuid4().hex}.svg"
    with open(p, "w", encoding="utf-8") as f:
        f.write(svg)
    return p


def _mk_cmd(infile: Path, args: RunArgs, tmp_export: Path | None) -> list[str]:
    """Build Inkscape command."""
    acts = []
    if any(a.startswith("select-") or a.startswith("query-") for a in args.actions):
        acts.append("select-clear")
    acts += args.actions

    if args.export:
        acts.append(
            "export-area-page" if args.export.area == "page" else "export-area-drawing"
        )
        acts += [f"export-type:{args.export.type}", f"export-filename:{tmp_export}"]
        if args.export.dpi:
            acts.append(f"export-dpi:{args.export.dpi}")
        acts.append("export-do")

    # Let Inkscape close naturally - file-close causes crashes in batch mode
    return ["inkscape", str(infile), f"--actions={';'.join(acts)}", "--batch-process"]


async def _action_list_impl() -> dict:
    """Internal implementation for listing actions."""
    if SEM is None:
        raise ToolError("Server not initialized")

    async with SEM:
        try:
            env = os.environ.copy()
            env["DISPLAY"] = ""  # Force headless mode to prevent GUI issues
            with anyio.fail_after(5):
                p = await anyio.run_process(["inkscape", "--action-list"], env=env)
            if p.returncode != 0:
                raise ToolError("action-list failed")

            items = []
            for line in p.stdout.decode().splitlines():
                if " : " in line:
                    aid, doc = line.split(" : ", 1)
                    items.append({"id": aid.strip(), "doc": doc.strip()})
            return {"actions": items}
        except TimeoutError as e:
            raise ToolError("action-list timeout") from e


@tool("action_list")
async def action_list(ctx: Context) -> dict:
    """List available Inkscape actions."""
    return await _action_list_impl()


async def _action_run_impl(
    doc: Doc,
    actions: list[str] | None = None,
    export: Export | None = None,
    timeout_s: int | None = None,
) -> dict:
    """Internal implementation for running actions."""
    if CFG is None or SEM is None:
        raise ToolError("Server not initialized")

    # Create args object for internal use
    args = RunArgs(
        doc=doc,
        actions=actions or [],
        export=export,
        timeout_s=timeout_s,
    )

    timeout = args.timeout_s or CFG.timeout_default

    async with SEM:
        # Resolve input
        if args.doc.type == "file":
            if not args.doc.path:
                raise ValidationError("Missing file path")
            infile = _ensure_in_workspace(Path(args.doc.path))
            _check_size(infile)
        else:
            if args.doc.svg is None:
                raise ValidationError("Missing inline SVG")
            infile = _write_inline(args.doc.svg)

        # Prepare export temp
        tmp_export = None
        final_export = None
        if args.export:
            final_export = _ensure_in_workspace(Path(args.export.out))
            # Preserve the export type extension for Inkscape compatibility
            tmp_name = (
                final_export.stem + f".tmp-{uuid.uuid4().hex}" + final_export.suffix
            )
            tmp_export = final_export.parent / tmp_name

        # Per-file lock only for real files
        lock_path = infile if args.doc.type == "file" else None

        cmd = _mk_cmd(infile, args, tmp_export)

        # Robust subprocess with cleanup
        env = os.environ.copy()
        env["DISPLAY"] = ""  # Force headless mode to prevent GUI issues

        if platform.system() != "Windows":
            popen_kw = {"preexec_fn": os.setsid, "env": env}
        else:
            popen_kw = {
                "creationflags": 0x00000010,
                "env": env,
            }  # CREATE_NEW_PROCESS_GROUP

        try:
            if lock_path:
                with FileLock(str(lock_path) + ".lock"):
                    proc = subprocess.Popen(
                        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **popen_kw
                    )
                    try:
                        stdout, stderr = proc.communicate(timeout=timeout)
                    except subprocess.TimeoutExpired:
                        if platform.system() != "Windows":
                            os.killpg(proc.pid, signal.SIGTERM)
                        else:
                            proc.terminate()
                        try:
                            stdout, stderr = proc.communicate(timeout=5)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            stdout, stderr = proc.communicate()
                        raise ToolError("Operation timed out") from None
            else:
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **popen_kw
                )
                try:
                    stdout, stderr = proc.communicate(timeout=timeout)
                except subprocess.TimeoutExpired:
                    if platform.system() != "Windows":
                        os.killpg(proc.pid, signal.SIGTERM)
                    else:
                        proc.terminate()
                    try:
                        stdout, stderr = proc.communicate(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        stdout, stderr = proc.communicate()
                    raise ToolError("Operation timed out") from None

            if proc.returncode != 0:
                raise ToolError("inkscape failed")

            # Atomic move of export
            if tmp_export and final_export:
                tmp_export = Path(tmp_export)
                if not tmp_export.exists():
                    raise ToolError("export missing")
                final_export.parent.mkdir(parents=True, exist_ok=True)
                os.replace(tmp_export, final_export)

            return {"ok": True, "out": str(final_export) if final_export else None}

        finally:
            # Cleanup tmp inline
            if args.doc.type == "inline":
                try:
                    infile.unlink(missing_ok=True)
                except Exception:
                    pass
            # Cleanup tmp export if still present
            if tmp_export:
                try:
                    Path(tmp_export).unlink(missing_ok=True)
                except Exception:
                    pass


@tool("action_run")
async def action_run(
    ctx: Context,
    doc: Doc,
    actions: list[str] | None = None,
    export: Export | None = None,
    timeout_s: int | None = None,
) -> dict:
    """Run Inkscape actions on a document."""
    return await _action_run_impl(doc, actions, export, timeout_s)


def main(config: InkscapeConfig | None = None) -> None:
    """Main entry point for CLI server."""
    _init_config(config)
    app.run()


if __name__ == "__main__":
    main()
