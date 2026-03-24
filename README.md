# Tool Execution Replay & Differential Debugger

A utility for capturing, replaying, and diffing tool executions to diagnose
drift, environment changes, and contract mismatches in agent-based systems.

## What It Does

This tool helps operators:

- **Capture** tool executions with full context (input arguments, environment fingerprint, output, timing)
- **Replay** past executions to reproduce issues exactly
- **Diff** two executions to identify what changed (output drift, environment changes, duration shifts)
- **Detect** contract incompatibilities when output structures change
- **Classify** issues as drift, environment drift, or contract failures

## Installation

```bash
# No external dependencies - pure stdlib
# Just clone or copy the files and run:
python3 main.py --help
```

## Usage

### Replay a Captured Execution

Show the stored result from a previously captured execution:

```bash
python3 main.py replay execution_bundle.json
```

Compare with current implementation to detect drift:

```bash
python3 main.py replay execution_bundle.json --fresh --tool-path ./my_tool.py
```

**Important:** The `--fresh` flag requires the tool implementation to be available at the specified `--tool-path`. If the tool is not found, the replay will fail with a clear error message pointing you to check the tool path.

### Compare Two Executions

Generate a differential report between old and new executions:

```bash
python3 main.py diff old_execution.json new_execution.json
```

For scripting/automation:

```bash
python3 main.py diff --json old.json new.json
```

### Capture an Execution

Create a new execution bundle:

```bash
python3 main.py capture --tool search_web --args '{"query": "python tutorials"}' captured.json
```

## Output Format

Execution bundles are JSON files with this structure:

```json
{
  "tool_name": "search_web",
  "tool_call_id": "call_abc123",
  "tool_version": "sha256:abcd1234...",
  "input_args": {},
  "input_kwargs": {"query": "python tutorials"},
  "env_fingerprint": {
    "python_version": "3.12.0",
    "platform": "Linux-6.6.0"
  },
  "output": {"results": [...]},
  "error": null,
  "duration_ms": 1250,
  "timestamp": "2026-03-24T12:00:00Z"
}
```

## Differential Report

The `diff` command produces reports with:

- **Health status**: `passed`, `degraded`, or `failed`
- **Change classification**: `none`, `drift`, `contract_change`
- **Environment differences**: specific fingerprint changes
- **Duration changes**: absolute and percentage

Example output:

```
=== Differential Report ===

--- Assessment ---
  Output drift detected (drift)
  Environment matches

Health: FAILED

--- Duration ---
  Old: 1000ms
  New: 2505ms (+150.5%)

--- Output Diff ---
--- original
+++ current
@@ -1,3 +1,3 @@
-{"results": ["a", "b"]}
+{"results": ["a", "b", "c"]}
```

## Fresh Replay Mode (`--fresh`)

The `--fresh` flag executes the tool with the current implementation to detect drift:

```bash
python3 main.py replay execution_bundle.json --fresh --tool-path ./my_tool.py
```

### Tool Loading Rules

The tool loader searches in this order:

1. **Specific module path** (from `--tool-path`): Loads a Python file and looks for a function matching the tool name, or common patterns like `main`, `run`, `execute`, or `handler`.

2. **Installed tools package**: Imports from `tools.<tool_name>` expecting a function named `<tool_name>`.

3. **Local file**: If tool name is a simple name (no dots), tries loading from `<tool_name>.py` in the current directory.

**Important:** The `--fresh` flag will fail if the tool implementation cannot be found. The error message will indicate this and suggest checking your tool path.

## Why This Matters

When tests fail or agents behave oddly, this tool helps answer:

- **Is this tool-code drift?** Did the implementation change?
- **Is this environment drift?** Did Python/library versions change?
- **Is this nondeterminism?** Could the old output be reproduced?
- **Is this contract-breaking?** Did output structure/format change?

This is essential for maintaining integrity in multi-agent orchestration systems.

## Testing

```bash
# Verify installation
python3 main.py --help

# Test basic replay
python3 main.py replay new_bundle.json

# Test fresh replay (requires test_tool.py)
python3 main.py replay new_bundle.json --fresh --tool-path ./test_tool.py

# Test diff between two bundles
python3 main.py diff new_bundle.json new_bundle.json

# Create a sample bundle
python3 main.py capture --tool sample_tool --args '{"test": true}' sample.json
```
