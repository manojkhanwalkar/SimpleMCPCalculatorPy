"""A fake MCP server for client tests: completes the handshake, then hangs in tools/call.

Usage: python hanging_server.py <pid file>; the pid file is written when tools/call arrives.
"""

import json
import os
import sys
import time
from pathlib import Path


def main() -> None:
    pid_file = Path(sys.argv[1])
    for line in sys.stdin:
        message = json.loads(line)
        if message.get("method") == "initialize":
            result = {
                "protocolVersion": message["params"]["protocolVersion"],
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "hanging-server", "version": "1"},
            }
            sys.stdout.write(
                json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}) + "\n"
            )
            sys.stdout.flush()
        elif message.get("method") == "tools/call":
            pid_file.write_text(str(os.getpid()))
            while True:
                time.sleep(1)


if __name__ == "__main__":
    main()
