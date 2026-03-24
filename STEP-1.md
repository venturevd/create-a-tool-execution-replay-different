# Step 1: Core: Create a Tool-Execution Replay & Differe

**File to create:** `main.py`
**Estimated size:** ~120 lines

## Instructions

Write a Python script that: Build a runnable utility that lets any agent operator capture a tool call (inputs, resolved tool version/implementation hash, environment, and outputs) and later replay it deterministically to produce a differential report (what changed, why it likely changed, and whether the change is acceptable vs failing a contract).

Why this is needed: the farm has integrity/verifiers, drift detectors, and integration-contract tooling, but there is no dedicated “replay the exact tool execution and diff the 

## Verification

Run: `python3 main.py --help`
