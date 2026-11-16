"""The public server identity and default tool surface are jobs-only."""

import pytest

from linkedin_mcp_server.server import create_mcp_server


JOB_TOOLS = {
    "search_jobs",
    "get_job_details",
    "get_job_apply_url",
    "get_easy_apply_form",
    "get_saved_jobs",
    "dismiss_job",
}

SESSION_TOOLS = {"get_session_status", "close_session"}


async def test_default_toolset_is_jobs_and_session_only():
    tools = await create_mcp_server().list_tools()

    assert {tool.name for tool in tools} == JOB_TOOLS | SESSION_TOOLS
    assert "get_person_profile" not in {tool.name for tool in tools}
    assert "send_message" not in {tool.name for tool in tools}
    assert "search_posts" not in {tool.name for tool in tools}


async def test_full_toolset_remains_available_for_upstream_compatibility():
    tools = await create_mcp_server(toolset="full").list_tools()
    names = {tool.name for tool in tools}

    assert JOB_TOOLS | SESSION_TOOLS <= names
    assert {"get_person_profile", "send_message", "search_posts"} <= names


def test_unknown_toolset_is_rejected():
    with pytest.raises(ValueError, match="toolset"):
        create_mcp_server(toolset="unknown")  # type: ignore[arg-type]
