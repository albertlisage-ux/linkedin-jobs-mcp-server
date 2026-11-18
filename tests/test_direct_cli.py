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


def test_analyze_command_prints_profile_match_overview(monkeypatch, capsys):
    config = SimpleNamespace(
        server=SimpleNamespace(tool_timeout_seconds=30.0),
    )
    monkeypatch.setattr(direct_cli, "_configure", lambda args: config)

    async def fake_analysis(args, query, *, tool_timeout):
        assert query == "data engineer"
        assert args.limit == 1
        assert tool_timeout == 30.0
        search = {
            "url": "https://www.linkedin.com/jobs/search/",
            "job_ids": ["101"],
            "references": {
                "search_results": [
                    {
                        "kind": "job",
                        "url": "/jobs/view/101/",
                        "text": "Data Engineer",
                    }
                ]
            },
        }
        profile = {
            "url": "https://www.linkedin.com/in/example/",
            "sections": {
                "experience": "Senior Data Engineer",
                "skills": "Python\nSQL",
            },
        }
        details = [
            {
                "url": "https://www.linkedin.com/jobs/view/101/",
                "sections": {
                    "job_posting": (
                        "Data Engineer\nAcme · Berlin · Remote\n"
                        "About the job\nBuild data systems with Python and SQL."
                    )
                },
            }
        ]
        return search, profile, details

    monkeypatch.setattr(direct_cli, "_collect_analysis", fake_analysis)

    assert direct_cli.main(["analyze", "data engineer", "--limit", "1"]) == 0

    output = capsys.readouterr().out
    assert "LINKEDIN JOB FIT OVERVIEW" in output
    assert "[Strong match] Data Engineer" in output
    assert "Matched evidence: Python, SQL" in output


def test_search_html_option_implies_analysis_and_writes_report(
    monkeypatch, capsys, tmp_path
):
    config = SimpleNamespace(
        server=SimpleNamespace(tool_timeout_seconds=30.0),
    )
    monkeypatch.setattr(direct_cli, "_configure", lambda args: config)

    async def fake_analysis(args, query, *, tool_timeout):
        assert query == "data engineer"
        assert args.analyze is False
        assert args.html == str(report_path)
        search = {
            "url": "https://www.linkedin.com/jobs/search/",
            "job_ids": ["101"],
            "references": {
                "search_results": [
                    {
                        "kind": "job",
                        "url": "/jobs/view/101/",
                        "text": "Data Engineer",
                    }
                ]
            },
        }
        profile = {
            "url": "https://www.linkedin.com/in/example/",
            "sections": {"skills": "Python\nSQL"},
        }
        details = [
            {
                "url": "https://www.linkedin.com/jobs/view/101/",
                "sections": {
                    "job_posting": (
                        "Data Engineer\nAcme · Berlin · Remote\n"
                        "About the job\nBuild data systems with Python and SQL."
                    )
                },
            }
        ]
        return search, profile, details

    report_path = tmp_path / "comparison.html"
    monkeypatch.setattr(direct_cli, "_collect_analysis", fake_analysis)
    opened = []
    monkeypatch.setattr(
        direct_cli,
        "_open_html_report",
        lambda path: opened.append(path) or "Google Chrome",
    )

    assert (
        direct_cli.main(
            [
                "search",
                "data engineer",
                "--limit",
                "1",
                "--html",
                str(report_path),
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "LINKEDIN JOB FIT OVERVIEW" in output
    assert f"HTML report: {report_path.resolve()}" in output
    assert "Opened report in Google Chrome." in output
    assert opened == [report_path.resolve()]
    assert report_path.exists()
    assert "Job comparison" in report_path.read_text(encoding="utf-8")


def test_no_open_keeps_html_generation_without_launching_browser(
    monkeypatch, capsys, tmp_path
):
    report_path = tmp_path / "comparison.html"
    monkeypatch.setattr(
        direct_cli,
        "_write_html_report",
        lambda path, report, *, language="en": report_path,
    )
    monkeypatch.setattr(
        direct_cli,
        "_open_html_report",
        lambda path: pytest.fail("browser should not be opened"),
    )

    direct_cli._write_and_open_report(
        SimpleNamespace(
            html=str(report_path),
            no_open=True,
            json=False,
        ),
        {},
    )

    output = capsys.readouterr().out
    assert f"HTML report: {report_path}" in output
    assert "Opened" not in output


@pytest.mark.parametrize("pages", ["0", "11"])
def test_search_rejects_out_of_range_pages(pages):
    with pytest.raises(SystemExit) as raised:
        direct_cli.main(["search", "python", "--pages", pages])

    assert raised.value.code == 2


def test_resume_search_requires_a_resume_file():
    with pytest.raises(SystemExit) as raised:
        direct_cli.main(["search", "--resume-search"])

    assert raised.value.code == 2


def test_profile_document_extracts_text_from_pdf(monkeypatch, tmp_path):
    import pypdf

    pdf_path = tmp_path / "Profile.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    class Page:
        def __init__(self, text):
            self.text = text

        def extract_text(self):
            return self.text

    class Reader:
        is_encrypted = False
        pages = [Page("Python SQL"), Page("Databricks analytics")]

        def __init__(self, path):
            assert path == str(pdf_path)

    monkeypatch.setattr(pypdf, "PdfReader", Reader)

    profile = direct_cli._profile_document(str(pdf_path))

    assert profile["sections"]["profile_document"] == (
        "Python SQL\nDatabricks analytics"
    )


def test_profile_document_reports_a_missing_path(tmp_path):
    missing = tmp_path / "resume.pdf"

    with pytest.raises(
        direct_cli.DirectCommandError,
        match="Profile file not found",
    ):
        direct_cli._profile_document(str(missing))


def test_resume_search_does_not_require_a_job_title(
    monkeypatch, capsys, tmp_path
):
    config = SimpleNamespace(
        server=SimpleNamespace(tool_timeout_seconds=30.0),
    )
    monkeypatch.setattr(direct_cli, "_configure", lambda args: config)
    resume = tmp_path / "resume.txt"
    resume.write_text("Python SQL Databricks analytics", encoding="utf-8")
    report_path = tmp_path / "resume-report.html"

    async def fake_analysis(args, query, *, tool_timeout):
        assert query is None
        assert args.resume_search is True
        search = {
            "url": "resume-search",
            "job_ids": ["101"],
            "search_mode": "resume",
            "search_queries": ["Python SQL Databricks"],
            "resume_search_signals": {
                "skills": ["Python", "SQL", "Databricks"],
                "domains": ["data"],
                "query_specs": [],
            },
            "references": {
                "search_results": [
                    {
                        "kind": "job",
                        "url": "/jobs/view/101/",
                        "text": "Data Engineer",
                        "search_query": "Python SQL Databricks",
                    }
                ]
            },
        }
        profile = {
            "url": str(resume),
            "sections": {
                "profile_document": resume.read_text(encoding="utf-8")
            },
        }
        details = [
            {
                "sections": {
                    "job_posting": (
                        "Data Engineer\nAcme · Berlin\nAbout the job\n"
                        "Build pipelines with Python and SQL."
                    )
                }
            }
        ]
        return search, profile, details

    monkeypatch.setattr(direct_cli, "_collect_analysis", fake_analysis)
    monkeypatch.setattr(direct_cli, "_open_html_report", lambda path: "Chrome")

    assert (
        direct_cli.main(
            [
                "search",
                "--resume",
                str(resume),
                "--resume-search",
                "--limit",
                "1",
                "--html",
                str(report_path),
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "resume-based skills" in output
    assert "Python SQL Databricks" in output
    assert report_path.exists()
