#!/usr/bin/env python3
"""Entry point for the LinkedIn Jobs MCP command and ``python -m``."""

import sys


_DIRECT_COMMANDS = frozenset({"search", "job", "saved", "login"})


def main() -> None:
    """Run a direct command, or start the job-focused MCP server."""
    if len(sys.argv) > 1 and sys.argv[1] in _DIRECT_COMMANDS:
        from linkedin_mcp_server.direct_cli import main as run_direct

        raise SystemExit(run_direct(sys.argv[1:]))

    from linkedin_mcp_server.cli_main import main as run_server

    run_server()


if __name__ == "__main__":
    main()
