# Usage Examples

This document provides concrete examples for using the Tool Execution Replay & Differential Debugger.

## Table of Contents

1. [Basic Replay](#basic-replay)
2. [Fresh Replay (Drift Detection)](#fresh-replay-drift-detection)
3. [Diff Two Executions](#diff-two-executions)
4. [Capturing Tool Executions](#capturing-tool-executions)
5. [Integrating With Tool Monitoring](#integrating-with-tool-monitoring)
6. [Scripting and Automation](#scripting-and-automation)

---

## Basic Replay

Simply show the stored result from a previously captured execution:

```bash
python3 main.py replay execution_bundle.json
```

Output:
```
=== Replay Result ===
Tool: test_tool
Call ID: call_1774339900454
Status: SUCCESS
Duration: 0ms
Version: unknown

Output:
{
  "result": "executed_test_tool",
  "echo": {
    "query": "test2"
  },
  "timestamp": "2026-03-24T08:11:40.454659+00:00"
}
```

## Fresh Replay (Drift Detection)

Execute with current code to detect if the tool's output has changed:

```bash
python3 main.py replay execution_bundle.json --fresh --tool-path ./test_tool.py
```

Output when drift detected:
```
=== Replay Result ===
Tool: test_tool
Call ID: call_1774339900454
Status: SUCCESS
Duration: 0ms
Version: 95c55b5327049c4b

Output:
{
  "result": "executed_test_tool",
  "echo": {
    "query": "test2"
  },
  "timestamp": "2026-03-24T12:35:12.123456+00:00"
}

--- Analysis ---
Output changed (drift). Diff:
--- original
+++ current
@@ -1 +1 @@
-{"echo":{"query":"test2"},"result":"executed_test_tool","timestamp":"2026-03-24T08:11:40.454659+00:00"}
+{"echo":{"query":"test2"},"result":"executed_test_tool","timestamp":"2026-03-24T12:35:12.861636+00:00"}
```

### What Changed?

The timestamp field is different because the fresh execution generates a new timestamp. This is expected nondeterministic behavior. To test actual drift:

1. Modify `test_tool.py` to return different output
2. Run the fresh replay again
3. The diff will show the actual output changes

## Diff Two Executions

Compare two saved execution bundles to find differences:

```bash
python3 main.py diff old_execution.json new_execution.json
```

Sample output:
```
=== Differential Report ===

--- Assessment ---
  Outputs match - no drift detected
  Environment matches

Health: PASSED

--- Duration ---
  Old: 15ms
  New: 12ms (-20.0%)
```

### JSON Output for Scripting

For automation/CI, use `--json` to get machine-readable output:

```bash
python3 main.py diff --json old.json new.json
```

Output:
```json
{
  "comparison_ts": "2026-03-24T12:35:00Z",
  "assessment": {
    "health": "passed",
    "messages": ["Outputs match - no drift detected", "Environment matches"]
  },
  "duration_comparison": {
    "old_ms": 15,
    "new_ms": 12,
    "change_ms": -3,
    "change_pct": -20.0
  }
}
```

## Capturing Tool Executions

Create a new execution bundle for later comparison:

```bash
# Capture with simple arguments
python3 main.py capture --tool web_search --args '{"query": "python tutorials"}' captured.json

# Capture with a specific tool implementation for version hashing
python3 main.py capture --tool data_fetcher --tool-path ./my_tool.py --args '{"url": "https://api.example.com/data"}' execution.json
```

**Important:** The `capture` command uses a mock tool by default. To capture real tool executions, you would need to extend the script to load and run actual tools. This is intended as a reference implementation.

## Integrating With Tool Monitoring

In a production system, you would:

1. **Capture**: The Farm's `tool_monitor.py` captures executions during monitoring
2. **Store**: Bundles are stored in `logs/executions/` with timestamps
3. **Replay**: Run `replay` with `--fresh` on drift detection
4. **Diff**: Compare baseline vs regressed executions

### Example Workflow

```bash
# First, establish a baseline
python3 main.py capture --tool my_tool --tool-path ./tools/my_tool.py baseline.json

# Later, when drift is suspected
python3 main.py capture --tool my_tool --tool-path ./tools/my_tool.py recent.json

# Compare to find differences
python3 main.py diff baseline.json recent.json

# Or replay with current code (even if tool implementation changed)
python3 main.py replay baseline.json --fresh --tool-path ./tools/my_tool.py
```

## Scripting and Automation

### CI/CD Integration

Check if a tool's output has regressed:

```bash
#!/bin/bash
# check-drift.sh

BASELINE=".baseline/execution.json"
RECENT="build/execution.json"

if ! python3 main.py diff --json "$BASELINE" "$RECENT" | python3 -c "
import sys, json
report = json.load(sys.stdin)
sys.exit(0 if report['assessment']['health'] == 'passed' else 1)
"; then
    echo "FAILED: Tool output drift detected!"
    python3 main.py diff "$BASELINE" "$RECENT"
    exit 1
fi

echo "PASSED: No drift detected"
```

### Find All Drift Results

Process multiple bundle pairs:

```bash
#!/usr/bin/env python3
import json
from pathlib import Path

def check_all_diffs(results_dir):
    """Check all diff results in a directory."""
    for diff_file in Path(results_dir).glob("diff-*.json"):
        with open(diff_file) as f:
            report = json.load(f)
        status = report["assessment"]["health"]
        print(f"{diff_file.name}: {status}")
        if status != "passed":
            print("  Messages:", "; ".join(report["assessment"]["messages"]))

if __name__ == "__main__":
    check_all_diffs("./results")
```

