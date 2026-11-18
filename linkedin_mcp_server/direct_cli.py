"""Direct command-line LinkedIn job search.

These commands intentionally use the same job tools and browser lifecycle as
the MCP server. That keeps one implementation of LinkedIn page handling while
letting someone search without installing an MCP client.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import webbrowser
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


DATE_POSTED_CHOICES = ("past_hour", "past_24_hours", "past_week", "past_month")
JOB_TYPE_CHOICES = (
    "full_time",
    "part_time",
    "contract",
    "temporary",
    "volunteer",
    "internship",
    "other",
)
EXPERIENCE_CHOICES = (
    "internship",
    "entry",
    "associate",
    "mid_senior",
    "director",
    "executive",
)
WORK_TYPE_CHOICES = ("on_site", "remote", "hybrid")
TRACKER_STAGES = ("saved", "in_progress", "applied", "archived")


class DirectCommandError(RuntimeError):
    """A direct command could not complete."""


def _add_browser_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--headful",
        action="store_true",
        help="Show the browser window while the command runs.",
    )
    parser.add_argument(
        "--profile",
        metavar="PATH",
        help="Override the saved browser profile directory.",
    )
    parser.add_argument(
        "--page-timeout",
        type=int,
        metavar="MS",
        help="Per-page browser timeout in milliseconds.",
    )
    parser.add_argument(
        "--tool-timeout",
        type=float,
        metavar="SECONDS",
        help="Whole-command timeout in seconds.",
    )
    parser.add_argument(
        "--claim-profile-root",
        action="store_true",
        help="Take ownership of a non-default profile directory once.",
    )


def _add_output_options(
    parser: argparse.ArgumentParser,
    *,
    default_limit: int = 20,
) -> None:
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the raw structured tool result as JSON.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=default_limit,
        metavar="N",
        help=(
            "Maximum jobs to print; 0 prints all returned jobs "
            f"(default: {default_limit})."
        ),
    )


def _add_search_filters(
    parser: argparse.ArgumentParser,
    *,
    default_pages: int = 1,
) -> None:
    parser.add_argument(
        "query",
        nargs="?",
        help="Search keywords; prompts when omitted.",
    )
    parser.add_argument("--location", help="City, region, country or Remote.")
    parser.add_argument(
        "--radius-km",
        type=int,
        metavar="KM",
        help=(
            "Include LinkedIn jobs within this many kilometres of --location "
            "(0-100). For example, --radius-km 50 includes nearby cities."
        ),
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=default_pages,
        metavar="N",
        help=f"LinkedIn result pages to read, 1-10 (default: {default_pages}).",
    )
    posted = parser.add_mutually_exclusive_group()
    posted.add_argument(
        "--posted",
        choices=DATE_POSTED_CHOICES,
        help="Only jobs posted in the selected period.",
    )
    posted.add_argument(
        "--today",
        dest="posted",
        action="store_const",
        const="past_24_hours",
        help="Only jobs posted in the last 24 hours.",
    )
    posted.add_argument(
        "--this-week",
        dest="posted",
        action="store_const",
        const="past_week",
        help="Only jobs posted in the last week.",
    )
    parser.add_argument(
        "--job-type",
        choices=JOB_TYPE_CHOICES,
        help="Filter by employment type.",
    )
    parser.add_argument(
        "--experience",
        choices=EXPERIENCE_CHOICES,
        help="Filter by experience level.",
    )
    work_type = parser.add_mutually_exclusive_group()
    work_type.add_argument(
        "--work-type",
        choices=WORK_TYPE_CHOICES,
        help="Filter by on-site, remote or hybrid work.",
    )
    work_type.add_argument(
        "--remote",
        dest="work_type",
        action="store_const",
        const="remote",
        help="Shortcut for --work-type remote.",
    )
    work_type.add_argument(
        "--hybrid",
        dest="work_type",
        action="store_const",
        const="hybrid",
        help="Shortcut for --work-type hybrid.",
    )
    work_type.add_argument(
        "--on-site",
        dest="work_type",
        action="store_const",
        const="on_site",
        help="Shortcut for --work-type on_site.",
    )
    parser.add_argument(
        "--easy-apply",
        action="store_true",
        help="Only show Easy Apply jobs.",
    )
    parser.add_argument(
        "--sort",
        choices=("date", "relevance"),
        help="Result ordering.",
    )
    parser.add_argument(
        "--company",
        action="append",
        default=[],
        metavar="NAME",
        help=(
            "Limit results to a company name or LinkedIn company slug. "
            "Repeat or comma-separate for multiple companies."
        ),
    )
    parser.add_argument(
        "--company-id",
        action="append",
        default=[],
        metavar="ID",
        help=(
            "Limit results to numeric LinkedIn company ID(s). "
            "Repeat or comma-separate for multiple companies."
        ),
    )
    parser.add_argument(
        "--strict-filters",
        action="store_true",
        help=(
            "Do not automatically relax location, remote, date or job-type "
            "filters when a resume search returns no jobs."
        ),
    )


def _add_profile_analysis_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--profile-file",
        metavar="PATH",
        help="Use a UTF-8 text, Markdown or PDF resume instead of LinkedIn profile.",
    )
    parser.add_argument(
        "--resume",
        dest="profile_file",
        metavar="PATH",
        help="Resume path (.txt, .md or text-based .pdf); alias for --profile-file.",
    )
    parser.add_argument(
        "--resume-search",
        action="store_true",
        help=(
            "Generate several skill-based searches from the resume instead of "
            "requiring or filtering by a job title."
        ),
    )
    parser.add_argument(
        "--resume-queries",
        type=int,
        default=3,
        metavar="N",
        help="Number of resume-derived queries to run, 1-5 (default: 3).",
    )
    parser.add_argument(
        "--profile-sections",
        default="experience,skills",
        metavar="LIST",
        help=(
            "LinkedIn profile sections to read when no profile file is supplied "
            "(default: experience,skills)."
        ),
    )
    parser.add_argument(
        "--profile-scrolls",
        type=int,
        default=10,
        metavar="N",
        help="Maximum Show-more clicks per profile section (default: 10).",
    )
    parser.add_argument(
        "--html",
        nargs="?",
        const="linkedin-jobs-report.html",
        metavar="PATH",
        help=(
            "Write a standalone HTML comparison report. Omit PATH to use "
            "linkedin-jobs-report.html."
        ),
    )
    parser.add_argument(
        "--language",
        choices=("en", "zh", "de"),
        default="en",
        help="Initial HTML report language: English, Chinese or German.",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Write the HTML report without opening it in a browser.",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the direct-use subcommand parser."""
    parser = argparse.ArgumentParser(
        prog="linkedin-jobs-mcp",
        description=(
            "Search and inspect LinkedIn jobs directly. Running without a "
            "subcommand starts the MCP server."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)

    login = commands.add_parser(
        "login",
        help="Sign in through a visible browser and save the session.",
    )
    _add_browser_options(login)

    search = commands.add_parser(
        "search",
        help="Search LinkedIn jobs and print titles, links and job IDs.",
    )
    _add_search_filters(search)
    search.add_argument(
        "--analyze",
        action="store_true",
        help="Compare the returned jobs with your profile before printing.",
    )
    _add_profile_analysis_options(search)
    _add_output_options(search)
    _add_browser_options(search)

    analyze = commands.add_parser(
        "analyze",
        help="Rank searched jobs against your profile and show evidence.",
    )
    _add_search_filters(analyze)
    _add_profile_analysis_options(analyze)
    _add_output_options(analyze, default_limit=5)
    _add_browser_options(analyze)

    job = commands.add_parser(
        "job",
        help="Read a specific LinkedIn job posting.",
    )
    job.add_argument("job_id", help="LinkedIn numeric job ID or posting URL.")
    job.add_argument(
        "--apply",
        action="store_true",
        help="Also show whether it uses Easy Apply or an employer site.",
    )
    _add_output_options(job)
    _add_browser_options(job)

    saved = commands.add_parser(
        "saved",
        help="List jobs from your LinkedIn job tracker.",
    )
    saved.add_argument(
        "--stage",
        choices=TRACKER_STAGES,
        default="saved",
        help="Tracker stage (default: saved).",
    )
    saved.add_argument(
        "--pages",
        type=int,
        default=1,
        metavar="N",
        help="Tracker pages to read, 1-10 (default: 1).",
    )
    _add_output_options(saved)
    _add_browser_options(saved)
    return parser


def _config_arguments(args: argparse.Namespace) -> list[str]:
    values: list[str] = []
    if getattr(args, "headful", False):
        values.append("--no-headless")
    if profile := getattr(args, "profile", None):
        values.extend(("--user-data-dir", profile))
    if page_timeout := getattr(args, "page_timeout", None):
        values.extend(("--timeout", str(page_timeout)))
    if tool_timeout := getattr(args, "tool_timeout", None):
        values.extend(("--tool-timeout", str(tool_timeout)))
    if getattr(args, "claim_profile_root", False):
        values.append("--claim-profile-root")
    return values


def _configure(args: argparse.Namespace) -> Any:
    """Apply normal server configuration before using the in-process tools."""
    from linkedin_mcp_server.bootstrap import configure_browser_environment
    from linkedin_mcp_server.config import set_config
    from linkedin_mcp_server.config.loaders import load_config
    from linkedin_mcp_server.drivers.browser import set_headless
    from linkedin_mcp_server.logging_config import configure_logging
    from linkedin_mcp_server.profile_claim import ensure_profile_claim

    config = load_config(_config_arguments(args))
    set_config(config)
    configure_logging(log_level=config.server.log_level, json_format=False)
    configure_browser_environment()
    ensure_profile_claim(
        Path(config.browser.user_data_dir),
        claim_anyway=config.server.claim_profile_root,
    )
    set_headless(config.browser.headless)
    return config


def _result_text(result: Any) -> str:
    parts: list[str] = []
    for item in getattr(result, "content", ()) or ():
        text = getattr(item, "text", None)
        if text:
            parts.append(str(text))
    return "\n".join(parts).strip()


def _structured_result(result: Any) -> dict[str, Any]:
    if bool(getattr(result, "is_error", False)):
        message = _result_text(result) or "LinkedIn returned a tool error."
        raise DirectCommandError(message)
    data = getattr(result, "structured_content", None)
    if not isinstance(data, dict):
        message = _result_text(result)
        raise DirectCommandError(
            message or "LinkedIn returned no structured job result."
        )
    return data


async def _call_tools(
    calls: Sequence[tuple[str, dict[str, Any]]],
    *,
    tool_timeout: float,
    toolset: str = "jobs",
    tolerate_errors_from: int | None = None,
) -> list[dict[str, Any]]:
    from fastmcp import Client

    from linkedin_mcp_server.server import create_mcp_server

    server = create_mcp_server(tool_timeout=tool_timeout, toolset=toolset)
    answers: list[dict[str, Any]] = []
    async with Client(server) as client:
        for index, (name, arguments) in enumerate(calls):
            try:
                answers.append(
                    _structured_result(await client.call_tool(name, arguments))
                )
            except DirectCommandError as exc:
                if tolerate_errors_from is None or index < tolerate_errors_from:
                    raise
                answers.append(
                    {
                        "url": f"https://www.linkedin.com/jobs/view/"
                        f"{arguments.get('job_id', '')}/",
                        "sections": {},
                        "section_errors": {
                            "analysis": {"error_message": str(exc)}
                        },
                    }
                )
    return answers


def _absolute_linkedin_url(url: str) -> str:
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return f"https://www.linkedin.com{url}"


def _job_entries(data: dict[str, Any]) -> list[dict[str, str]]:
    reference_section = (
        data.get("references", {}).get("search_results", [])
        if isinstance(data.get("references"), dict)
        else []
    )
    by_id: dict[str, dict[str, str]] = {}
    ordered: list[dict[str, str]] = []
    for raw in reference_section:
        if not isinstance(raw, dict) or raw.get("kind") != "job":
            continue
        url = str(raw.get("url", ""))
        job_id = url.rstrip("/").rsplit("/", 1)[-1]
        entry = {
            "id": job_id,
            "url": _absolute_linkedin_url(url),
            "title": str(raw.get("text") or f"LinkedIn job {job_id}"),
        }
        if raw.get("search_query"):
            entry["search_query"] = str(raw["search_query"])
        ordered.append(entry)
        by_id[job_id] = entry

    for job_id in data.get("job_ids", []):
        value = str(job_id)
        if value not in by_id:
            entry = {
                "id": value,
                "url": f"https://www.linkedin.com/jobs/view/{value}/",
                "title": f"LinkedIn job {value}",
            }
            ordered.append(entry)
            by_id[value] = entry
    return ordered


def _search_warnings(data: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    errors = data.get("section_errors")
    if isinstance(errors, dict):
        for section, detail in errors.items():
            if isinstance(detail, dict):
                message = detail.get("error_message") or detail.get("error_type")
            else:
                message = str(detail)
            if message:
                warnings.append(f"{section}: {message}")
    return warnings


def format_job_list(
    data: dict[str, Any],
    *,
    heading: str,
    limit: int = 20,
) -> str:
    """Format search or job-tracker results for a terminal."""
    entries = _job_entries(data)
    shown = entries if limit == 0 else entries[: max(0, limit)]
    total = data.get("total")
    lines = [heading]
    if url := data.get("url"):
        lines.append(f"URL: {url}")
    if isinstance(total, dict) and total.get("count") is not None:
        suffix = "" if total.get("exact", True) else "+"
        lines.append(f"LinkedIn reports: {total['count']}{suffix} jobs")
    lines.append(f"Showing {len(shown)} of {len(entries)} returned jobs")

    promoted = {str(value) for value in data.get("promoted_job_ids", [])}
    for position, entry in enumerate(shown, start=1):
        marker = " [promoted]" if entry["id"] in promoted else ""
        lines.extend(
            (
                "",
                f"{position}. {entry['title']}{marker}",
                f"   {entry['url']}",
                f"   Job ID: {entry['id']}",
            )
        )

    if not entries:
        lines.extend(("", "No job postings were returned."))

    warnings = _search_warnings(data)
    if warnings:
        lines.extend(("", "Warnings:"))
        lines.extend(f"- {warning}" for warning in warnings)
    return "\n".join(lines)


def format_job_details(
    details: dict[str, Any],
    *,
    apply: dict[str, Any] | None = None,
) -> str:
    """Format a posting and optional application-route result."""
    lines = [f"Job: {details.get('url', '')}"]
    section = details.get("sections", {}).get("job_posting")
    if section:
        lines.extend(("", str(section).strip()))
    else:
        lines.extend(("", "No job-posting text was returned."))

    if apply is not None:
        route = apply.get("apply", {})
        lines.extend(("", f"Application type: {route.get('type', 'unknown')}"))
        if route.get("url"):
            lines.append(f"Application URL: {route['url']}")

    warnings = _search_warnings(details)
    if apply is not None:
        warnings.extend(_search_warnings(apply))
    if warnings:
        lines.extend(("", "Warnings:"))
        lines.extend(f"- {warning}" for warning in warnings)
    return "\n".join(lines)


def _search_arguments(
    args: argparse.Namespace,
    query: str,
    *,
    company_ids: str | None = None,
) -> dict[str, Any]:
    return {
        "keywords": query,
        "location": args.location,
        "distance_km": args.radius_km,
        "max_pages": args.pages,
        "date_posted": args.posted,
        "job_type": args.job_type,
        "experience_level": args.experience,
        "work_type": args.work_type,
        "company_ids": company_ids,
        "easy_apply": args.easy_apply,
        "sort_by": args.sort,
    }


def _relaxed_search_arguments(
    args: argparse.Namespace,
    query: str,
    *,
    company_ids: str | None,
) -> dict[str, Any]:
    arguments = _search_arguments(args, query, company_ids=company_ids)
    arguments.update(
        {
            "location": None,
            "distance_km": None,
            "date_posted": None,
            "job_type": None,
            "experience_level": None,
            "work_type": None,
            "easy_apply": False,
            "sort_by": None,
        }
    )
    return arguments


def _profile_document(path: str) -> dict[str, Any]:
    profile_path = Path(path).expanduser()
    if not profile_path.exists():
        raise DirectCommandError(
            f"Profile file not found: {profile_path}. "
            "Use --resume with the actual file path."
        )
    try:
        if profile_path.suffix.casefold() == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(str(profile_path))
            if reader.is_encrypted:
                raise DirectCommandError(
                    "The resume PDF is encrypted. Save an unencrypted copy "
                    "before using --resume."
                )
            text = "\n".join(
                page.extract_text() or "" for page in reader.pages
            )
        else:
            text = profile_path.read_text(encoding="utf-8")
    except DirectCommandError:
        raise
    except UnicodeDecodeError as exc:
        raise DirectCommandError(
            "The profile file must be UTF-8 text or a text-based PDF. "
            "Convert scanned PDFs or Word documents to UTF-8 text first."
        ) from exc
    except OSError as exc:
        raise DirectCommandError(f"Could not read profile file: {exc}") from exc
    except Exception as exc:
        raise DirectCommandError(
            f"Could not extract text from {profile_path.name}: {exc}. "
            "If this is a scanned PDF, run OCR or provide a UTF-8 text file."
        ) from exc
    if not text.strip():
        raise DirectCommandError(
            "The profile file contains no extractable text. "
            "If it is a scanned PDF, run OCR or provide a UTF-8 text file."
        )
    from linkedin_mcp_server.job_analysis import parse_resume_document

    parsed_sections = parse_resume_document(text)
    return {
        "url": str(profile_path),
        "sections": {
            "profile_document": text,
            **parsed_sections,
        },
    }


def _write_html_report(
    path: str,
    report: dict[str, Any],
    *,
    language: str = "en",
) -> Path:
    from linkedin_mcp_server.job_analysis import render_fit_report_html

    report_path = Path(path).expanduser()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        render_fit_report_html(report, initial_language=language),
        encoding="utf-8",
    )
    return report_path.resolve()


def _chrome_commands() -> list[list[str]]:
    """Browser launch commands, preferring an installed Chrome."""
    commands: list[list[str]] = []
    if sys.platform == "darwin":
        chrome_app = Path("/Applications/Google Chrome.app")
        if chrome_app.exists():
            commands.append(["open", "-a", "Google Chrome"])
    elif sys.platform == "win32":
        for root in (
            os.environ.get("PROGRAMFILES"),
            os.environ.get("PROGRAMFILES(X86)"),
            os.environ.get("LOCALAPPDATA"),
        ):
            if root:
                executable = (
                    Path(root)
                    / "Google"
                    / "Chrome"
                    / "Application"
                    / "chrome.exe"
                )
                if executable.exists():
                    commands.append([str(executable)])
    for name in (
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chrome",
    ):
        executable = shutil.which(name)
        if executable:
            commands.append([executable])
    return commands


def _open_html_report(path: Path) -> str:
    """Open a report in Chrome, falling back to the default browser."""
    url = path.as_uri()
    for command in _chrome_commands():
        try:
            subprocess.Popen(
                [*command, url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError:
            continue
        return "Google Chrome" if "Chrome" in command[-1] else command[0]

    try:
        opened = webbrowser.open(url)
    except webbrowser.Error:
        opened = False
    if opened:
        return "the default browser"
    raise DirectCommandError(
        "The HTML report was written, but no browser could be opened."
    )


def _write_and_open_report(
    args: argparse.Namespace,
    report: dict[str, Any],
) -> None:
    if not args.html:
        return
    report_path = _write_html_report(
        args.html,
        report,
        language=getattr(args, "language", "en"),
    )
    stream = sys.stderr if args.json else sys.stdout
    print(f"HTML report: {report_path}", file=stream)
    if args.no_open:
        return
    try:
        browser = _open_html_report(report_path)
    except DirectCommandError as exc:
        print(f"Warning: {exc}", file=sys.stderr)
    else:
        print(f"Opened report in {browser}.", file=stream)


def _split_filter_values(values: list[str] | None) -> list[str]:
    return [
        item.strip()
        for value in values or []
        for item in value.split(",")
        if item.strip()
    ]


def _company_slug_from_reference(reference: dict[str, Any]) -> str | None:
    url = str(reference.get("url", ""))
    path = urlparse(url).path.rstrip("/")
    marker = "/company/"
    if marker not in path:
        return None
    slug = path.split(marker, 1)[1].split("/", 1)[0].strip()
    return slug or None


async def _resolve_company_filters(
    client: Any,
    args: argparse.Namespace,
) -> tuple[str | None, list[dict[str, str]]]:
    """Resolve numeric IDs and company names to LinkedIn job facet IDs."""
    from linkedin_mcp_server.core.exceptions import LinkedInOperationError
    from linkedin_mcp_server.linkedin.identifiers import (
        normalize_company_identifier,
    )

    values = [
        *_split_filter_values(getattr(args, "company", None)),
        *_split_filter_values(getattr(args, "company_id", None)),
    ]
    ids: list[str] = []
    resolutions: list[dict[str, str]] = []
    for value in values:
        if value.isdigit():
            if value not in ids:
                ids.append(value)
                resolutions.append(
                    {
                        "input": value,
                        "company_id": value,
                        "linkedin_slug": "",
                    }
                )
            continue

        slug: str | None = None
        try:
            slug = normalize_company_identifier(value)
        except LinkedInOperationError:
            search_result = _structured_result(
                await client.call_tool(
                    "search_companies",
                    {"keywords": value},
                )
            )
            references = (
                search_result.get("references", {}).get("search_results", [])
                if isinstance(search_result.get("references"), dict)
                else []
            )
            candidates = [
                ref
                for ref in references
                if isinstance(ref, dict) and ref.get("kind") == "company"
            ]
            exact = [
                ref
                for ref in candidates
                if str(ref.get("text", "")).strip().casefold()
                == value.casefold()
            ]
            selected = exact[0] if exact else candidates[0] if candidates else None
            if selected is None:
                raise DirectCommandError(
                    f"Could not resolve company {value!r}. "
                    "Try a LinkedIn company slug or --company-id."
                )
            slug = _company_slug_from_reference(selected)
            if slug is None:
                raise DirectCommandError(
                    f"LinkedIn returned no company slug for {value!r}. "
                    "Try --company-id."
                )

        company_profile = _structured_result(
            await client.call_tool(
                "get_company_profile",
                {"company_name": slug},
            )
        )
        about_refs = (
            company_profile.get("references", {}).get("about", [])
            if isinstance(company_profile.get("references"), dict)
            else []
        )
        company_urn = next(
            (
                str(ref.get("value"))
                for ref in about_refs
                if isinstance(ref, dict)
                and ref.get("kind") == "company_urn"
                and str(ref.get("value", "")).isdigit()
            ),
            None,
        )
        if company_urn is None:
            raise DirectCommandError(
                f"Could not determine the LinkedIn company ID for {value!r}. "
                "Open the company page and use --company-id with its numeric ID."
            )
        if company_urn not in ids:
            ids.append(company_urn)
        resolutions.append(
            {
                "input": value,
                "company_id": company_urn,
                "linkedin_slug": slug,
            }
        )

    return (",".join(ids) if ids else None), resolutions


async def _collect_analysis(
    args: argparse.Namespace,
    query: str | None,
    *,
    tool_timeout: float,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Read search, profile and selected postings through one browser session."""
    from fastmcp import Client

    from linkedin_mcp_server.job_analysis import (
        generate_resume_search_queries,
        merge_job_search_results,
    )
    from linkedin_mcp_server.server import create_mcp_server

    profile = _profile_document(args.profile_file) if args.profile_file else None
    has_company_names = bool(
        _split_filter_values(getattr(args, "company", None))
    )
    toolset = "jobs" if profile is not None and not has_company_names else "full"
    server = create_mcp_server(tool_timeout=tool_timeout, toolset=toolset)
    async with Client(server) as client:
        company_ids, company_resolutions = await _resolve_company_filters(
            client, args
        )
        if args.resume_search:
            if profile is None:
                raise DirectCommandError(
                    "--resume-search requires --resume or --profile-file."
                )
            resume_text = str(
                profile.get("sections", {}).get("profile_document", "")
            )
            search_context = generate_resume_search_queries(
                resume_text,
                limit=args.resume_queries,
                profile=profile,
            )
            if not search_context["queries"]:
                raise DirectCommandError(
                    "Could not derive search queries from the resume."
                )
            query_specs = search_context["queries"]
            all_query_specs = list(query_specs)
            search_results = []
            for query_spec in query_specs:
                search_results.append(
                    _structured_result(
                        await client.call_tool(
                            "search_jobs",
                            _search_arguments(
                                args,
                                query_spec["query"],
                                company_ids=company_ids,
                            ),
                        )
                    )
                )
            fallback_attempts: list[dict[str, Any]] = []
            target_results = args.limit if args.limit > 0 else 10
            initial_merged = merge_job_search_results(
                search_results,
                all_query_specs,
            )
            initial_result_count = len(initial_merged.get("job_ids", []))
            if (
                not args.strict_filters
                and search_results
                and initial_result_count < target_results
            ):
                fallback_queries: list[tuple[str, str]] = []
                skills = search_context.get("skills", [])
                if len(skills) >= 2:
                    fallback_queries.append(
                        (" ".join(skills[:2]), "top two resume skills")
                    )
                if skills:
                    fallback_queries.append((skills[0], "top resume skill"))
                if company_ids:
                    fallback_queries.append(("", "all jobs from selected company"))

                for fallback_query, basis in fallback_queries:
                    fallback_result = _structured_result(
                        await client.call_tool(
                            "search_jobs",
                            _relaxed_search_arguments(
                                args,
                                fallback_query,
                                company_ids=company_ids,
                            ),
                        )
                    )
                    fallback_spec = {
                        "query": fallback_query,
                        "signals": [basis, "filters relaxed"],
                    }
                    all_query_specs.append(fallback_spec)
                    search_results.append(fallback_result)
                    fallback_attempts.append(
                        {
                            "query": fallback_query,
                            "basis": basis,
                            "job_ids": list(fallback_result.get("job_ids", [])),
                            "relaxed_filters": [
                                "location",
                                "distance_km",
                                "date_posted",
                                "job_type",
                                "experience_level",
                                "work_type",
                                "easy_apply",
                            ],
                        }
                    )
                    merged_so_far = merge_job_search_results(
                        search_results,
                        all_query_specs,
                    )
                    if len(merged_so_far.get("job_ids", [])) >= target_results:
                        break
            search_result = merge_job_search_results(
                search_results,
                all_query_specs,
            )
            search_result["search_mode"] = "resume"
            if fallback_attempts:
                search_result["fallback_search"] = {
                    "used": True,
                    "attempts": fallback_attempts,
                    "found_jobs": bool(search_result.get("job_ids")),
                    "initial_result_count": initial_result_count,
                    "target_results": target_results,
                    "final_result_count": len(search_result.get("job_ids", [])),
                }
            search_result["resume_search_signals"] = {
                "skills": search_context["skills"],
                "domains": search_context["domains"],
                "query_specs": query_specs,
            }
        else:
            if not query:
                raise DirectCommandError("A search query is required.")
            search_result = _structured_result(
                await client.call_tool(
                    "search_jobs",
                    _search_arguments(
                        args,
                        query,
                        company_ids=company_ids,
                    ),
                )
            )
        if company_resolutions:
            search_result["company_filters"] = company_resolutions
        if args.location:
            search_result["location_filter"] = {
                "location": args.location,
                "radius_km": args.radius_km,
            }

        entries = _job_entries(search_result)
        selected = entries if args.limit == 0 else entries[: args.limit]

        if profile is None:
            profile = _structured_result(
                await client.call_tool(
                    "get_my_profile",
                    {
                        "sections": args.profile_sections,
                        "max_scrolls": args.profile_scrolls,
                    },
                )
            )

        details: list[dict[str, Any]] = []
        for entry in selected:
            try:
                details.append(
                    _structured_result(
                        await client.call_tool(
                            "get_job_details", {"job_id": entry["id"]}
                        )
                    )
                )
            except DirectCommandError as exc:
                details.append(
                    {
                        "url": entry["url"],
                        "sections": {},
                        "section_errors": {
                            "analysis": {"error_message": str(exc)}
                        },
                    }
                )
    return search_result, profile, details


async def _execute(args: argparse.Namespace) -> int:
    tool_timeout = args.tool_timeout or 180.0
    if args.command == "search":
        query = args.query
        if not query and not args.resume_search:
            query = input("Search LinkedIn jobs: ").strip()
        if not query and not args.resume_search:
            raise DirectCommandError("A search query is required.")
        if args.analyze or args.html or args.resume_search:
            from linkedin_mcp_server.job_analysis import (
                analyze_job_fit,
                format_fit_report,
            )

            search_result, profile, details = await _collect_analysis(
                args,
                query,
                tool_timeout=tool_timeout,
            )
            report = analyze_job_fit(
                query=query or "Resume-based search",
                search_result=search_result,
                profile=profile,
                job_details=details,
                limit=args.limit,
            )
            if args.json:
                print(json.dumps(report, indent=2, ensure_ascii=False))
            else:
                print(format_fit_report(report))
            _write_and_open_report(args, report)
            return 0

        data = (
            await _call_tools(
                [("search_jobs", _search_arguments(args, query))],
                tool_timeout=tool_timeout,
            )
        )[0]
        if args.json:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            location = f" in {args.location}" if args.location else ""
            print(
                format_job_list(
                    data,
                    heading=f'LinkedIn jobs for "{query}"{location}',
                    limit=args.limit,
                )
            )
        return 0

    if args.command == "analyze":
        from linkedin_mcp_server.job_analysis import (
            analyze_job_fit,
            format_fit_report,
        )

        query = args.query
        if not query and not args.resume_search:
            query = input("Search LinkedIn jobs to analyze: ").strip()
        if not query and not args.resume_search:
            raise DirectCommandError("A search query is required.")
        search_result, profile, details = await _collect_analysis(
            args,
            query,
            tool_timeout=tool_timeout,
        )
        report = analyze_job_fit(
            query=query or "Resume-based search",
            search_result=search_result,
            profile=profile,
            job_details=details,
            limit=args.limit,
        )
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print(format_fit_report(report))
        _write_and_open_report(args, report)
        return 0

    if args.command == "job":
        calls = [("get_job_details", {"job_id": args.job_id})]
        if args.apply:
            calls.append(("get_job_apply_url", {"job_id": args.job_id}))
        answers = await _call_tools(calls, tool_timeout=tool_timeout)
        details = answers[0]
        apply_result = answers[1] if len(answers) > 1 else None
        if args.json:
            data = {"details": details}
            if apply_result is not None:
                data["apply"] = apply_result
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print(format_job_details(details, apply=apply_result))
        return 0

    if args.command == "saved":
        data = (
            await _call_tools(
                [
                    (
                        "get_saved_jobs",
                        {"max_pages": args.pages, "stage": args.stage},
                    )
                ],
                tool_timeout=tool_timeout,
            )
        )[0]
        if args.json:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print(
                format_job_list(
                    data,
                    heading=f"LinkedIn job tracker: {args.stage}",
                    limit=args.limit,
                )
            )
        return 0

    raise DirectCommandError(f"Unknown command {args.command!r}")


def main(argv: Sequence[str] | None = None) -> int:
    """Run one direct LinkedIn jobs command."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "login":
        from linkedin_mcp_server.cli_main import main as run_server_cli

        run_server_cli(["--login", *_config_arguments(args)])
        return 0

    if getattr(args, "pages", None) is not None and not 1 <= args.pages <= 10:
        parser.error("--pages must be between 1 and 10")
    if getattr(args, "limit", None) is not None and args.limit < 0:
        parser.error("--limit must be zero or greater")
    if (
        getattr(args, "profile_scrolls", None) is not None
        and not 1 <= args.profile_scrolls <= 50
    ):
        parser.error("--profile-scrolls must be between 1 and 50")
    if getattr(args, "resume_queries", None) is not None and not (
        1 <= args.resume_queries <= 5
    ):
        parser.error("--resume-queries must be between 1 and 5")
    if getattr(args, "resume_search", False) and not args.profile_file:
        parser.error("--resume-search requires --resume or --profile-file")
    if (
        getattr(args, "radius_km", None) is not None
        and not 0 <= args.radius_km <= 100
    ):
        parser.error("--radius-km must be between 0 and 100")
    if getattr(args, "radius_km", None) is not None and not args.location:
        parser.error("--radius-km requires --location")

    try:
        config = _configure(args)
        runtime_args = argparse.Namespace(**vars(args))
        runtime_args.tool_timeout = (
            args.tool_timeout or config.server.tool_timeout_seconds
        )
        return asyncio.run(
            _execute(runtime_args)
        )
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"LinkedIn jobs command failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
