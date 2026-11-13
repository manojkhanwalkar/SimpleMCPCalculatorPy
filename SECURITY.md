# Security policy

## Reporting a vulnerability

Please do **not** open a public issue. Use GitHub's private vulnerability reporting instead
(*Security → Report a vulnerability* on this repository).

## Handling data

The servers are pure calculators: they read no files, make no network calls and store nothing.
Their only output besides MCP responses is an owner-only log file (`~/.calculator-mcp/`).

Never commit secrets or `.env` files. Test data must be synthetic.
