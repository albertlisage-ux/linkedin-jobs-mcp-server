# src/linkedin_mcp_server/__init__.py
"""LinkedIn Jobs MCP Server package.

A jobs-focused MCP server that reads LinkedIn through the user's own browser
session. The package retains the upstream browser, authentication and page
infrastructure while publishing job-only tools by default.
"""

from importlib.metadata import PackageNotFoundError, version

from linkedin_mcp_server.greenlet_runtime import explain_a_missing_runtime

# Before anything reaches patchright, where the failure would otherwise surface
# as a bare DLL error with nothing pointing at its cause. Both entry paths, the
# console script and ``python -m``, import this module first.
explain_a_missing_runtime()

try:
    __version__ = version("mcp-server-linkedin")
except PackageNotFoundError:
    try:
        # Fallback for environments installed under the pre-rename name
        __version__ = version("linkedin-scraper-mcp")
    except PackageNotFoundError:
        __version__ = "0.0.0.dev"  # Running from source without install
