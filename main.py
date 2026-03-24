#!/usr/bin/env python3
"""
Tool Execution Replay & Differential Debugger

A utility for capturing, replaying, and diffing tool executions to diagnose
drift, environment changes, and contract mismatches.

Usage:
    # Replay a captured execution (show stored result)
    python3 main.py replay execution_bundle.json

    # Replay with fresh execution to detect drift
    python3 main.py replay execution_bundle.json --fresh

    # Generate a diff report between two execution bundles
    python3 main.py diff old_bundle.json new_bundle.json
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import difflib


@dataclass
class ExecutionBundle:
    """Captured record of a single tool execution."""
    tool_name: str
    tool_call_id: str
    tool_version: str  # implementation hash
    input_args: dict[int, Any]  # positional args stored as {index: value}
    input_kwargs: dict[str, Any]
    env_fingerprint: dict[str, str]
    output: Any
    error: str | None = None
    duration_ms: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        result = {
            "tool_name": self.tool_name,
            "tool_call_id": self.tool_call_id,
            "tool_version": self.tool_version,
            "input_args": self.input_args,
            "input_kwargs": self.input_kwargs,
            "env_fingerprint": self.env_fingerprint,
            "output": self.output,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
        }
        if self.error:
            result["error"] = self.error
        return result

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ExecutionBundle":
        return cls(
            tool_name=d["tool_name"],
            tool_call_id=d["tool_call_id"],
            tool_version=d["tool_version"],
            input_args=d.get("input_args", {}),
            input_kwargs=d.get("input_kwargs", {}),
            env_fingerprint=d.get("env_fingerprint", {}),
            output=d.get("output"),
            error=d.get("error"),
            duration_ms=d.get("duration_ms", 0),
            timestamp=d.get("timestamp", datetime.now(timezone.utc).isoformat()),
        )


@dataclass
class ReplayResult:
    """Result of replaying an execution."""
    success: bool
    output: Any = None
    error: str | None = None
    duration_ms: int = 0
    tool_version: str = ""
    diff_explanation: str = ""
    change_type: str = "none"  # none, drift, contract_change

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "tool_version": self.tool_version,
            "diff_explanation": self.diff_explanation,
            "change_type": self.change_type,
        }


class ToolLoader:
    """Loads and manages tool implementations for replay."""

    def __init__(self, tool_path: Path | None = None):
        self.tool_path = tool_path
        self._cache: dict[str, Any] = {}

    def load_tool(self, tool_name: str) -> tuple[Any, str] | None:
        """
        Load a tool function by name.

        Returns:
            (tool_callable, version_info) or None if not found
        """
        if tool_name in self._cache:
            return self._cache[tool_name]

        result = None

        # Strategy 1: Direct module loading from specified path
        if self.tool_path and self.tool_path.exists():
            result = self._load_from_path(tool_name, self.tool_path)

        # Strategy 2: Try importing from installed location
        if result is None:
            result = self._load_from_import(tool_name)

        # Strategy 3: Try loading from common tool patterns
        if result is None and self.tool_path is None and "." not in tool_name:
            # Maybe the tool is in a file with the same name in current directory
            local_path = Path(f"{tool_name}.py")
            if local_path.exists():
                result = self._load_from_path(tool_name, local_path)

        if result:
            self._cache[tool_name] = result

        return result

    def _load_from_path(self, tool_name: str, path: Path) -> tuple[Any, str] | None:
        """Load tool from a specific Python file."""
        try:
            spec = importlib.util.spec_from_file_location("_replay_tool_module", path)
            if not spec or not spec.loader:
                return None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Try exact name first
            if hasattr(module, tool_name):
                fn = getattr(module, tool_name)
                if callable(fn):
                    version = self._compute_version(path)
                    return (fn, version)

            # Try common tool function patterns
            common_names = ["main", "run", "execute", "tool", "handler"]
            for name in common_names:
                if hasattr(module, name):
                    fn = getattr(module, name)
                    if callable(fn):
                        version = self._compute_version(path)
                        return (fn, version)

            return None
        except Exception:
            return None

    def _load_from_import(self, tool_name: str) -> tuple[Any, str] | None:
        """Load tool via standard Python import."""
        try:
            import_name = tool_name.lstrip("tools.")
            parts = import_name.split(".")
            if len(parts) == 1:
                # Assume tools.<name> module with <name> function
                module_name = f"tools.{import_name}"
                fn_name = import_name
            else:
                module_name = import_name
                fn_name = parts[-1]

            mod = __import__(module_name, fromlist=[fn_name])
            fn = getattr(mod, fn_name)
            if callable(fn):
                # Try to find the module file for version computation
                if hasattr(mod, "__file__") and mod.__file__:
                    version = self._compute_version(Path(mod.__file__))
                else:
                    version = "imported"
                return (fn, version)
        except Exception:
            return None

    def _compute_version(self, path: Path) -> str:
        """Compute a version hash from file contents."""
        try:
            content = path.read_bytes()
            return hashlib.sha256(content).hexdigest()[:16]
        except Exception:
            return "unknown"


class DiffAnalyzer:
    """Analyzes differences between execution outputs."""

    @staticmethod
    def _normalize_output(output: Any) -> str:
        """Normalize output for comparison."""
        if output is None:
            return "null"
        if isinstance(output, (dict, list)):
            return json.dumps(output, sort_keys=True, separators=(",", ":"))
        return str(output)

    @staticmethod
    def compare_outputs(old: Any, new: Any) -> tuple[bool, str, str]:
        """
        Compare two outputs.

        Returns:
            (is_equal, diff_text, change_type)
        """
        old_norm = DiffAnalyzer._normalize_output(old)
        new_norm = DiffAnalyzer._normalize_output(new)

        if old_norm == new_norm:
            return True, "", "none"

        # Generate unified diff
        diff = difflib.unified_diff(
            old_norm.splitlines(keepends=True),
            new_norm.splitlines(keepends=True),
            fromfile="original",
            tofile="current",
            lineterm=""
        )
        diff_text = "".join(diff)

        # Classify change type
        change_type = "drift"
        if isinstance(old, dict):
            old_keys = set(old.keys())
            new_keys = set(new.keys()) if isinstance(new, dict) else set()
            if not new_keys.issuperset(old_keys):
                change_type = "contract_change"
        elif isinstance(old, list) and isinstance(new, list):
            if len(old) != len(new):
                change_type = "contract_change"

        return False, diff_text, change_type


class ReplayEngine:
    """Core engine for replaying and analyzing tool executions."""

    def __init__(self, tool_loader: ToolLoader):
        self.tool_loader = tool_loader

    def replay_bundle(self, bundle: ExecutionBundle, fresh_exec: bool = False) -> ReplayResult:
        """
        Replay a captured execution.

        Args:
            bundle: The original execution bundle
            fresh_exec: If True, execute with current implementation to detect drift
        """
        if not fresh_exec:
            return ReplayResult(
                success=bundle.error is None,
                output=bundle.output,
                error=bundle.error,
                duration_ms=bundle.duration_ms,
                tool_version=bundle.tool_version,
                change_type="none",
                diff_explanation="Original replay (no comparison)"
            )

        # Fresh execution: load and run the tool
        load_result = self.tool_loader.load_tool(bundle.tool_name)
        if load_result is None:
            return ReplayResult(
                success=False,
                error=f"Could not load tool: {bundle.tool_name}",
                tool_version="unknown",
                diff_explanation="Tool not available for replay. "
                                "Ensure the tool exists in the specified module or in tools.<name>."
            )

        tool_fn, tool_version = load_result

        try:
            import time
            start = time.time()

            # Reconstruct arguments
            args = tuple(bundle.input_args.get(i) for i in sorted(bundle.input_args.keys()))
            result = tool_fn(*args, **bundle.input_kwargs)
            duration = int((time.time() - start) * 1000)

            # Compare with original
            is_equal, diff_text, change_type = DiffAnalyzer.compare_outputs(
                bundle.output, result
            )

            diff_explanation = "Outputs match exactly" if is_equal else (
                f"Output changed ({change_type}). Diff:\n{diff_text[:1000]}" +
                ("..." if len(diff_text) > 1000 else "")
            )

            return ReplayResult(
                success=True,
                output=result,
                duration_ms=duration,
                tool_version=tool_version,
                diff_explanation=diff_explanation,
                change_type="none" if is_equal else change_type
            )

        except Exception as e:
            return ReplayResult(
                success=False,
                error=str(e),
                duration_ms=0,
                tool_version="unknown",
                diff_explanation=f"Execution failed: {type(e).__name__}: {e}"
            )

    def diff_bundles(self, old_bundle: ExecutionBundle, new_bundle: ExecutionBundle) -> dict[str, Any]:
        """Compare two execution bundles and produce a differential report."""
        outputs_equal, diff_text, change_type = DiffAnalyzer.compare_outputs(
            old_bundle.output, new_bundle.output
        )

        env_differences = self._compare_environments(
            old_bundle.env_fingerprint, new_bundle.env_fingerprint
        )

        duration_change = new_bundle.duration_ms - old_bundle.duration_ms
        duration_change_pct = (
            (duration_change / old_bundle.duration_ms * 100) if old_bundle.duration_ms > 0 else 0
        )

        assessment = []
        if not outputs_equal:
            if change_type == "contract_change":
                assessment.append("CRITICAL: Output structure changed - contract may be incompatible")
            else:
                assessment.append(f"Output drift detected ({change_type})")
        else:
            assessment.append("Outputs match - no drift detected")

        if env_differences:
            assessment.append(f"Environment changed: {len(env_differences)} differences")
        else:
            assessment.append("Environment matches")

        if abs(duration_change_pct) > 20:
            assessment.append(f"Duration changed by {duration_change_pct:+.1f}%")

        has_critical = change_type == "contract_change"
        health = "failed" if has_critical else ("degraded" if not outputs_equal else "passed")

        return {
            "comparison_ts": datetime.now(timezone.utc).isoformat(),
            "old_execution": {
                "tool_call_id": old_bundle.tool_call_id,
                "timestamp": old_bundle.timestamp,
                "tool_version": old_bundle.tool_version,
                "duration_ms": old_bundle.duration_ms,
            },
            "new_execution": {
                "tool_call_id": new_bundle.tool_call_id,
                "timestamp": new_bundle.timestamp,
                "tool_version": new_bundle.tool_version,
                "duration_ms": new_bundle.duration_ms,
            },
            "output_comparison": {
                "outputs_equal": outputs_equal,
                "change_type": change_type,
                "diff_preview": diff_text[:2000] if diff_text else None,
            },
            "environment_comparison": {
                "differences": env_differences,
                "has_differences": len(env_differences) > 0,
            },
            "duration_comparison": {
                "old_ms": old_bundle.duration_ms,
                "new_ms": new_bundle.duration_ms,
                "change_ms": duration_change,
                "change_pct": round(duration_change_pct, 1),
            },
            "assessment": {
                "health": health,
                "messages": assessment,
            },
        }

    @staticmethod
    def _compare_environments(old: dict[str, str], new: dict[str, str]) -> list[str]:
        """Compare environment fingerprints and return significant differences."""
        differences = []
        all_keys = set(old.keys()) | set(new.keys())

        for key in sorted(all_keys):
            old_val = old.get(key, "<missing>")
            new_val = new.get(key, "<missing>")
            if old_val != new_val:
                differences.append(f"{key}: {old_val} -> {new_val}")

        return differences


def load_bundle(path: Path) -> ExecutionBundle:
    """Load an execution bundle from a JSON file."""
    with open(path) as f:
        data = json.load(f)
    return ExecutionBundle.from_dict(data)


def save_bundle(bundle: ExecutionBundle, path: Path) -> None:
    """Save an execution bundle to a JSON file."""
    with open(path, "w") as f:
        json.dump(bundle.to_dict(), f, indent=2)


def get_env_fingerprint() -> dict[str, str]:
    """Generate a fingerprint of the current execution environment."""
    import os
    import platform
    import sys

    fp = {
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "processor": platform.processor() or "unknown",
    }

    for var in ["PATH", "PYTHONPATH", "VIRTUAL_ENV", "HOME"]:
        val = os.environ.get(var, "")
        if val:
            fp[var.lower()] = val.split(":")[0] if ":" in val else val[:100]

    return fp


def capture_execution(
    tool_name: str,
    tool_fn: Callable,
    args: tuple,
    kwargs: dict,
    tool_version: str = "unknown"
) -> ExecutionBundle:
    """Execute a tool and capture an execution bundle."""
    import time

    start = time.time()
    try:
        output = tool_fn(*args, **kwargs)
        error = None
    except Exception as e:
        output = None
        error = str(e)

    duration = int((time.time() - start) * 1000)

    return ExecutionBundle(
        tool_name=tool_name,
        tool_call_id=f"call_{int(datetime.now(timezone.utc).timestamp() * 1000)}",
        tool_version=tool_version,
        input_args=dict(enumerate(args)),
        input_kwargs=kwargs,
        env_fingerprint=get_env_fingerprint(),
        output=output,
        error=error,
        duration_ms=duration,
    )


def cmd_replay(args: argparse.Namespace) -> int:
    """Handle replay command."""
    bundle_path = Path(args.bundle)
    if not bundle_path.exists():
        print(f"Error: Bundle not found: {bundle_path}", file=sys.stderr)
        return 1

    try:
        bundle = load_bundle(bundle_path)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in bundle: {e}", file=sys.stderr)
        return 1
    except KeyError as e:
        print(f"Error: Bundle missing required field: {e}", file=sys.stderr)
        return 1

    tool_loader = ToolLoader(Path(args.tool_path) if args.tool_path else None)
    engine = ReplayEngine(tool_loader)
    result = engine.replay_bundle(bundle, fresh_exec=args.fresh)

    if args.quiet:
        print(json.dumps(result.to_dict(), separators=(",", ":")))
    else:
        _print_replay_result(bundle, result)

    return 0 if result.success else 1


def _print_replay_result(bundle: ExecutionBundle, result: ReplayResult) -> None:
    """Format and print replay result."""
    print(f"\n=== Replay Result ===")
    print(f"Tool: {bundle.tool_name}")
    print(f"Call ID: {bundle.tool_call_id}")
    print(f"Status: {'SUCCESS' if result.success else 'FAILED'}")
    print(f"Duration: {result.duration_ms}ms")
    print(f"Version: {result.tool_version}")

    if result.error:
        print(f"\nError: {result.error}")
    elif result.output is not None:
        if isinstance(result.output, (dict, list)):
            output_preview = json.dumps(result.output, indent=2)
        else:
            output_preview = str(result.output)
        truncated = output_preview[:1000] if len(output_preview) > 1000 else output_preview
        print(f"\nOutput:\n{truncated}" + ("..." if len(output_preview) > 1000 else ""))

    if result.diff_explanation and result.diff_explanation != "Original replay (no comparison)":
        print(f"\n--- Analysis ---\n{result.diff_explanation}")


def cmd_diff(args: argparse.Namespace) -> int:
    """Handle diff command."""
    old_path = Path(args.old)
    new_path = Path(args.new)

    for p in [old_path, new_path]:
        if not p.exists():
            print(f"Error: Bundle not found: {p}", file=sys.stderr)
            return 1

    try:
        old_bundle = load_bundle(old_path)
        new_bundle = load_bundle(new_path)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}", file=sys.stderr)
        return 1
    except KeyError as e:
        print(f"Error: Bundle missing required field: {e}", file=sys.stderr)
        return 1

    tool_loader = ToolLoader()
    engine = ReplayEngine(tool_loader)
    report = engine.diff_bundles(old_bundle, new_bundle)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_diff_report(report)

    return 0 if report["assessment"]["health"] == "passed" else 1


def _print_diff_report(report: dict[str, Any]) -> None:
    """Format and print differential report."""
    print(f"\n=== Differential Report ===")
    print(f"\n--- Assessment ---")
    for msg in report["assessment"]["messages"]:
        print(f"  {msg}")
    print(f"\nHealth: {report['assessment']['health'].upper()}")

    if report["environment_comparison"]["differences"]:
        print(f"\n--- Environment Changes ({len(report['environment_comparison']['differences'])}) ---")
        for diff in report["environment_comparison"]["differences"][:10]:
            print(f"  {diff}")
        if len(report["environment_comparison"]["differences"]) > 10:
            print(f"  ... and {len(report['environment_comparison']['differences']) - 10} more")

    print(f"\n--- Duration ---")
    old_d = report["duration_comparison"]["old_ms"]
    new_d = report["duration_comparison"]["new_ms"]
    print(f"  Old: {old_d}ms")
    print(f"  New: {new_d}ms ({report['duration_comparison']['change_pct']:+.1f}%)")

    if report["output_comparison"]["diff_preview"]:
        print(f"\n--- Output Diff ---")
        preview = report["output_comparison"]["diff_preview"][:800]
        print(preview)
        if len(report["output_comparison"]["diff_preview"]) > 800:
            print("... (truncated, use --json for full diff)")


def cmd_capture(args: argparse.Namespace) -> int:
    """Handle capture command - create a sample bundle."""
    tool_name = args.tool
    tool_args = json.loads(args.args) if args.args else {}

    # Create a mock tool function for demonstration
    def mock_tool(**kwargs):
        return {"result": f"executed_{tool_name}", "echo": kwargs, "timestamp": datetime.now(timezone.utc).isoformat()}

    # Determine version from tool path or current code
    tool_version = "unknown"
    if args.tool_path:
        try:
            tool_path = Path(args.tool_path)
            if tool_path.exists():
                tool_version = hashlib.sha256(tool_path.read_bytes()).hexdigest()[:16]
        except Exception:
            pass

    bundle = capture_execution(
        tool_name=tool_name,
        tool_fn=mock_tool,
        args=(),
        kwargs=tool_args,
        tool_version=tool_version
    )

    output_path = Path(args.output)
    save_bundle(bundle, output_path)
    print(f"Saved execution bundle to {output_path}")
    print(f"Tool: {tool_name}, Version: {tool_version}")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Tool Execution Replay & Differential Debugger",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Replay a captured execution (show stored result)
  python3 main.py replay execution.json

  # Replay with fresh execution to detect drift
  python3 main.py replay execution.json --fresh --tool-path ./my_tool.py

  # Compare two executions to find differences
  python3 main.py diff old_execution.json new_execution.json

  # Create a sample bundle for testing
  python3 main.py capture --tool my_tool --args '{"query": "test"}' sample.json

  # Full JSON output for scripting
  python3 main.py diff --json old.json new.json
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Replay command
    replay_parser = subparsers.add_parser(
        "replay",
        help="Replay a captured execution",
        description="Replay a captured tool execution, optionally comparing with current implementation"
    )
    replay_parser.add_argument("bundle", type=Path, help="Path to execution bundle JSON")
    replay_parser.add_argument("--fresh", action="store_true", help="Execute with current code to detect drift")
    replay_parser.add_argument("--tool-path", type=str, help="Path to tool implementation module (.py file)")
    replay_parser.add_argument("--quiet", "-q", action="store_true", help="JSON output only")
    replay_parser.set_defaults(func=cmd_replay)

    # Diff command
    diff_parser = subparsers.add_parser(
        "diff",
        help="Compare two execution bundles",
        description="Generate a differential report comparing two captured executions"
    )
    diff_parser.add_argument("old", type=Path, help="Path to old execution bundle")
    diff_parser.add_argument("new", type=Path, help="Path to new execution bundle")
    diff_parser.add_argument("--json", action="store_true", help="JSON output only")
    diff_parser.set_defaults(func=cmd_diff)

    # Capture command
    capture_parser = subparsers.add_parser(
        "capture",
        help="Create an execution bundle",
        description="Execute a tool and capture its execution context"
    )
    capture_parser.add_argument("--tool", required=True, help="Tool name")
    capture_parser.add_argument("--args", type=str, help="JSON arguments, e.g. '{\"query\": \"test\"}'")
    capture_parser.add_argument("--tool-path", type=str, help="Path to tool implementation for version hash")
    capture_parser.add_argument("output", type=Path, help="Output bundle path")
    capture_parser.set_defaults(func=cmd_capture)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
