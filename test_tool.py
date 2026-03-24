#!/usr/bin/env python3
"""
A sample tool for testing the replay functionality.
This tool implements the same interface as the mock tool used during capture.
"""

def test_tool(query="default"):
    """
    A simple test tool that returns a standardized response.

    Args:
        query: The query string to process

    Returns:
        dict: A standardized result with echo and timestamp
    """
    from datetime import datetime, timezone
    return {
        "result": "executed_test_tool",
        "echo": {"query": query},
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


if __name__ == "__main__":
    # Can be run directly for quick testing
    import json
    result = test_tool(query="direct_test")
    print(json.dumps(result, indent=2))
