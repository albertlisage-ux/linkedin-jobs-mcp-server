#!/usr/bin/env python3
"""Entry point for the LinkedIn Jobs MCP command and ``python -m``."""


def main() -> None:
    """Import and run the job-focused server."""
    from linkedin_mcp_server.cli_main import main as run_server

    run_server()


if __name__ == "__main__":
    main()
