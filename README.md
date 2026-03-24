# Tool Execution Replay & Differential Debugger

A utility for capturing, replaying, and diffing tool executions to diagnose drift, environment configurations, and contract mismatches in agent-based systems.

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
- **Change classification**: `none`, `drift`, `env_change`, `contract_change`
- **Environment differences**: specific fingerprint changes
- **Output diff**: unified diff preview (truncated by default)
- **Duration changes**: absolute and percentage

Example output:

```
=== Differential Report ===
Tool: search_web

--- Assessment ---
  Output drift detected (value_change)
  Environment changed: 2 differences
  Duration changed by +150.5%

Health: FAILED

--- Environment Changes (2) ---
  python_version: 3.11.0 -> 3.12.0
  platform: Linux-5.4 -> Linux-6.6.0

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

## Integration with Tool Monitoring

The Farm's `tool_monitor.py` can be extended to:

1. Capture execution bundles during production monitoring
2. Store them in `logs/executions/` with timestamps
3. Run `replay` with `--fresh` on drift detection
4. Use `diff` to compare baseline vs regressed executions

## Why This Matters

When tests fail or agents behave oddly, this tool helps answer:

- **Is this tool-code drift?** Did the implementation change?
- **Is this environment drift?** Did Python/library versions change?
- **Is this nondeterminism?** Could the old output be reproduced?
- **Is this contract-breaking?** Did output structure/format change?

This is essential for maintaining integrity in multi-agent orchestration systems like the Farm.

## Testing

Run the help to verify installation:

```bash
python3 main.py --help
```

Create a test bundle:

```bash
python3 main.py capture --tool test_tool sample.json
python3 main.py replay sample.json
python3 main.py diff sample.json sample.json
```
