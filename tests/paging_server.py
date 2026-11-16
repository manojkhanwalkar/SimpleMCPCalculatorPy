"""A fake MCP server for client tests that returns its tool list in pages.

Usage: python paging_server.py <mode> [<pid file>]
  two-pages  page 1 is empty with a cursor; page 2 offers "cube" (x -> x^3)
  repeat     every page returns the same cursor
  endless    every page returns a new cursor
  slow       answers initialize after 3 seconds; offers no tools
"""

import json
import os
import sys
import time
from pathlib import Path

CUBE = {
    "name": "cube",
    "description": "Cube of x",
    "inputSchema": {
        "type": "object",
        "properties": {"x": {"type": "number"}},
        "required": ["x"],
    },
}


def tools_page(mode: str, cursor: str | None) -> dict[str, object]:
    if mode == "two-pages":
        return {"tools": [], "nextCursor": "p2"} if cursor is None else {"tools": [CUBE]}
    if mode == "slow":
        return {"tools": []}
    if mode == "repeat":
        return {"tools": [], "nextCursor": "same"}
    return {"tools": [], "nextCursor": f"p{int((cursor or 'p0')[1:]) + 1}"}


def reply(message: dict[str, object], result: dict[str, object]) -> None:
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}) + "\n")
    sys.stdout.flush()


def main() -> None:
    mode = sys.argv[1]
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(str(os.getpid()))
    for line in sys.stdin:
        message = json.loads(line)
        method = message.get("method")
        params = message.get("params") or {}
        assert isinstance(params, dict)
        if method == "initialize":
            if mode == "slow":
                time.sleep(3)
            reply(
                message,
                {
                    "protocolVersion": params["protocolVersion"],
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "paging-server", "version": "1"},
                },
            )
        elif method == "tools/list":
            reply(message, tools_page(mode, params.get("cursor")))
        elif method == "tools/call":
            x = params.get("arguments", {}).get("x")
            ok = params.get("name") == "cube" and isinstance(x, int | float)
            text = repr(float(x) ** 3) if ok else "Unknown tool"
            reply(message, {"content": [{"type": "text", "text": text}], "isError": not ok})


if __name__ == "__main__":
    main()
