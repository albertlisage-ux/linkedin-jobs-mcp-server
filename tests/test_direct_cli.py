"""Direct terminal commands use the same job tools as the MCP server."""

from types import SimpleNamespace

import pytest

from linkedin_mcp_server import direct_cli


def test_search_shortcuts_reach_the_job_search_arguments():
    args = direct_cli.build_parser().parse_args(
        [
            "search",
            "platform engineer",
            "--location",
            "Berlin",
            "--remote",
            "--this-week",
            "--easy-apply",
            "--limit",
            "7",
        ]
    )

    assert direct_cli._search_arguments(args, args.query) == {
        "keywords": "platform engineer",
        "location": "Berlin",
        "max_pages": 1,
        "date_posted": "past_week",
        "job_type": None,
        "experience_level": None,
        "work_type": "remote",
        "easy_apply": True,
        "sort_by": None,
    }
    assert args.limit == 7


def test_search_formatter_names_jobs_and_preserves_linkedin_links():
    data = {
        "url": "https://www.linkedin.com/jobs/search/?keywords=python",
        "job_ids": ["123", "456"],
        "promoted_job_ids": ["456"],
        "total": {"count": 1000, "exact": False},
        "references": {
            "search_results": [
                {
                    "kind": "job",
                    "url": "/jobs/view/123/",
                    "text": "Python Platform Engineer",
                },
                {
                    "kind": "job",
                    "url": "/jobs/view/456/",
                    "text": "Backend Engineer",
                },
            ]
        },
        "section_errors": {
            "search_results": {
                "error_type": "filters_dropped",
                "error_message": "LinkedIn dropped the location filter.",
            }
        },
    }

    rendered = direct_cli.format_job_list(data, heading="Python jobs", limit=1)

    assert "Python Platform Engineer" in rendered
    assert "https://www.linkedin.com/jobs/view/123/" in rendered
    assert "Showing 1 of 2 returned jobs" in rendered
    assert "LinkedIn reports: 1000+ jobs" in rendered
    assert "Backend Engineer" not in rendered
    assert "LinkedIn dropped the location filter." in rendered


def test_job_details_formatter_includes_application_route():
    rendered = direct_cli.format_job_details(
        {
            "url": "https://www.linkedin.com/jobs/view/123/",
            "sections": {"job_posting": "About the job\nBuild reliable systems."},
        },
        apply={
            "apply": {
                "type": "external",
                "url": "https://employer.example/apply",
            }
        },
    )

    assert "Build reliable systems." in rendered
    assert "Application type: external" in rendered
    assert "https://employer.example/apply" in rendered


def test_search_command_prints_results(monkeypatch, capsys):
    config = SimpleNamespace(
        server=SimpleNamespace(tool_timeout_seconds=30.0),
    )
    monkeypatch.setattr(direct_cli, "_configure", lambda args: config)

    async def fake_calls(calls, *, tool_timeout):
        assert tool_timeout == 30.0
        assert calls == [
            (
                "search_jobs",
                {
                    "keywords": "python",
                    "location": "Berlin",
                    "max_pages": 1,
                    "date_posted": None,
                    "job_type": None,
                    "experience_level": None,
                    "work_type": "remote",
                    "easy_apply": False,
                    "sort_by": None,
                },
            )
        ]
        return [
            {
                "url": "https://www.linkedin.com/jobs/search/",
                "job_ids": ["123"],
                "references": {
                    "search_results": [
                        {
                            "kind": "job",
                            "url": "/jobs/view/123/",
                            "text": "Python Engineer",
                        }
                    ]
                },
            }
        ]

    monkeypatch.setattr(direct_cli, "_call_tools", fake_calls)

    assert direct_cli.main(
        ["search", "python", "--location", "Berlin", "--remote"]
    ) == 0

    output = capsys.readouterr().out
    assert 'LinkedIn jobs for "python" in Berlin' in output
    assert "Python Engineer" in output
    assert "Job ID: 123" in output


def test_job_command_can_include_application_type(monkeypatch, capsys):
    config = SimpleNamespace(
        server=SimpleNamespace(tool_timeout_seconds=30.0),
    )
    monkeypatch.setattr(direct_cli, "_configure", lambda args: config)

    async def fake_calls(calls, *, tool_timeout):
        assert calls == [
            ("get_job_details", {"job_id": "123"}),
            ("get_job_apply_url", {"job_id": "123"}),
        ]
        return [
            {
                "url": "https://www.linkedin.com/jobs/view/123/",
                "sections": {"job_posting": "About the job\nAnalyze data."},
            },
            {"apply": {"type": "easy_apply"}},
        ]

    monkeypatch.setattr(direct_cli, "_call_tools", fake_calls)

    assert direct_cli.main(["job", "123", "--apply"]) == 0

    output = capsys.readouterr().out
    assert "Analyze data." in output
    assert "Application type: easy_apply" in output


@pytest.mark.parametrize("pages", ["0", "11"])
def test_search_rejects_out_of_range_pages(pages):
    with pytest.raises(SystemExit) as raised:
        direct_cli.main(["search", "python", "--pages", pages])

    assert raised.value.code == 2
