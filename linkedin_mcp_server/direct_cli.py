"""Direct command-line LinkedIn job search.

These commands intentionally use the same job tools and browser lifecycle as
the MCP server. That keeps one implementation of LinkedIn page handling while
letting someone search without installing an MCP client.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any


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


def _add_output_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the raw structured tool result as JSON.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        metavar="N",
        help="Maximum jobs to print; 0 prints all returned jobs (default: 20).",
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
    search.add_argument(
        "query",
        nargs="?",
        help="Search keywords; prompts when omitted.",
    )
    search.add_argument("--location", help="City, region, country or Remote.")
    search.add_argument(
        "--pages",
        type=int,
        default=1,
        metavar="N",
        help="LinkedIn result pages to read, 1-10 (default: 1).",
    )
    posted = search.add_mutually_exclusive_group()
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
    search.add_argument(
        "--job-type",
        choices=JOB_TYPE_CHOICES,
        help="Filter by employment type.",
    )
    search.add_argument(
        "--experience",
        choices=EXPERIENCE_CHOICES,
        help="Filter by experience level.",
    )
    work_type = search.add_mutually_exclusive_group()
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
    search.add_argument(
        "--easy-apply",
        action="store_true",
        help="Only show Easy Apply jobs.",
    )
    search.add_argument(
        "--sort",
        choices=("date", "relevance"),
        help="Result ordering.",
    )
    _add_output_options(search)
    _add_browser_options(search)

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
) -> list[dict[str, Any]]:
    from fastmcp import Client

    from linkedin_mcp_server.server import create_mcp_server

    server = create_mcp_server(tool_timeout=tool_timeout)
    answers: list[dict[str, Any]] = []
    async with Client(server) as client:
        for name, arguments in calls:
            answers.append(
                _structured_result(await client.call_tool(name, arguments))
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


def _search_arguments(args: argparse.Namespace, query: str) -> dict[str, Any]:
    return {
        "keywords": query,
        "location": args.location,
        "max_pages": args.pages,
        "date_posted": args.posted,
        "job_type": args.job_type,
        "experience_level": args.experience,
        "work_type": args.work_type,
        "easy_apply": args.easy_apply,
        "sort_by": args.sort,
    }


async def _execute(args: argparse.Namespace) -> int:
    tool_timeout = args.tool_timeout or 180.0
    if args.command == "search":
        query = args.query or input("Search LinkedIn jobs: ").strip()
        if not query:
            raise DirectCommandError("A search query is required.")
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
