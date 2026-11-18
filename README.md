# LinkedIn Jobs MCP Server

A jobs-focused [Model Context Protocol](https://modelcontextprotocol.io/) server
for searching LinkedIn and reading job postings through the user's own signed-in
browser session.

This repository is a derivative of
[stickerdaniel/linkedin-mcp-server](https://github.com/stickerdaniel/linkedin-mcp-server).
It keeps the upstream browser-session, authentication, pagination, rate-limit
and LinkedIn page-reading infrastructure while narrowing the published MCP
surface to job workflows.

> Independent open-source project. Not affiliated with LinkedIn or Microsoft.
> LinkedIn is a trademark of LinkedIn Corporation.

## Job tools

| Tool | What it does |
| --- | --- |
| `search_jobs` | Search by keywords, location, recency, job type, experience level, work type, Easy Apply and sort order. |
| `get_job_details` | Read a posting's description, requirements and company details. |
| `get_job_apply_url` | Determine whether a posting uses Easy Apply, an external employer site, is already applied to, or is closed. |
| `get_easy_apply_form` | Inspect Easy Apply questions and prefilled fields without submitting or keeping a draft. |
| `get_saved_jobs` | Read the authenticated user's saved, in-progress, applied or archived jobs. |
| `dismiss_job` | Dismiss an unwanted job from LinkedIn search. This is irreversible. |
| `get_session_status` | Inspect local saved-session state without opening a browser. |
| `close_session` | Close the shared browser session without deleting the saved login. |

The server does not expose profile edits, people search, messaging, connection
requests, feeds or post tools.

## Requirements

- Python 3.12.4 or newer
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- A LinkedIn account
- A local desktop session for the first browser login

## Quick start

Run directly from GitHub with `uvx`:

```bash
uvx --from git+https://github.com/albertlisage-ux/linkedin-jobs-mcp-server.git \
  linkedin-jobs-mcp
```

The first operation that needs LinkedIn authentication can reuse a signed-in
local Chromium-family browser or open a login window. To create the stored
session explicitly:

```bash
uvx --from git+https://github.com/albertlisage-ux/linkedin-jobs-mcp-server.git \
  linkedin-jobs-mcp --login
```

After signing in, retry the tool call.

## Search directly from the terminal

Install the command once, then use it without an MCP client:

```bash
uv tool install \
  "git+https://github.com/albertlisage-ux/linkedin-jobs-mcp-server.git"

linkedin-jobs-mcp login
linkedin-jobs-mcp search "platform engineer" \
  --location Berlin \
  --remote \
  --this-week \
  --limit 10
```

The terminal output lists each job title, LinkedIn URL and job ID. Common
shortcuts are `--remote`, `--hybrid`, `--on-site`, `--today` and `--this-week`.
Use `--pages 2` or more to read additional result pages, and `--json` for
machine-readable output.

Read a posting:

```bash
linkedin-jobs-mcp job 4252026496
linkedin-jobs-mcp job 4252026496 --apply
```

Analyze the returned jobs against your profile:

```bash
linkedin-jobs-mcp search "data engineer" \
  --location Berlin \
  --remote \
  --this-week \
  --limit 5 \
  --analyze \
  --language zh \
  --html linkedin-jobs-report.html

linkedin-jobs-mcp analyze "data engineer" \
  --location Berlin \
  --remote \
  --this-week \
  --limit 5
```

The analysis reads your LinkedIn `experience` and `skills` sections, reads the
details of the selected postings, and prints:

- an overview with strong, good, review-worthy and stretch matches;
- repeated strengths and recurring skill gaps;
- an improvement roadmap prioritized by how many jobs require each gap;
- concrete learn, build, demonstrate and interview-preparation steps;
- personal bridge projects built from your existing skills and current role;
- experience-gap plans derived from captured profile date ranges;
- a ranked fit score for each job with matched and missing evidence;
- observed seniority, work mode, employment type and requested experience;
- key requirements, responsibilities, benefits and a description snapshot;
- expandable full job descriptions, preserving the language supplied by LinkedIn.

Each detailed job also has a collapsible improvement plan. The report never
invents experience or recommends adding unsupported skills; each skill step
starts by verifying the gap and then builds a project that can provide real
evidence.

The report identifies the profile name and current or most recent role when
available. For each missing skill it selects the nearest skills already present
in your profile, explains the bridge, and proposes a project that extends that
existing evidence into the missing area.

`search --analyze --html` writes a standalone responsive report containing the
overview, ranking table and detailed comparison cards. The report opens in
Google Chrome automatically; add `--no-open` to write it without launching a
browser. `--html` also implies analysis, so
`search "data engineer" --html report.html` is sufficient. Omitting the path
writes `linkedin-jobs-report.html` in the current directory. The report includes
print styles, semantic headings, accessible score labels, light/dark color
support and no external JavaScript.

The report has English, Simplified Chinese and German interface controls.
Use `--language en`, `--language zh` or `--language de` to choose the
initial language. The report can switch between all three after opening.
LinkedIn job descriptions and requirements remain in their original language.

The score is an explainable keyword/evidence heuristic, not a hiring
probability. To analyze a resume or profile text instead of the LinkedIn
profile:

```bash
linkedin-jobs-mcp analyze "platform engineer" \
  --profile-file ~/resume.txt \
  --remote \
  --limit 5
```

Search using only the resume, with no job title or exact-title filter:

```bash
linkedin-jobs-mcp search \
  --resume ~/resume.txt \
  --resume-search \
  --resume-queries 3 \
  --location Berlin \
  --remote \
  --this-week \
  --limit 5 \
  --language zh \
  --html linkedin-jobs-report.html
```

`--resume-search` detects and ranks skills and domain signals from the resume,
generates up to five complementary queries, runs them through LinkedIn, removes
duplicate jobs and analyzes the merged result. The report records the resume
signals and every query used, so the search remains explainable.

`--resume` accepts UTF-8 `.txt`/`.md` files and text-based PDF resumes. Scanned
PDFs need OCR first. For example:

```bash
linkedin-jobs-mcp search \
  --resume ~/Downloads/Profile.pdf \
  --resume-search \
  --remote \
  --this-week \
  --limit 5 \
  --language zh \
  --html linkedin-jobs-report.html
```

Use `--json` for the complete structured analysis. If you do not want to read
the default `experience,skills` sections, adjust them with
`--profile-sections`.

List jobs in your tracker:

```bash
linkedin-jobs-mcp saved
linkedin-jobs-mcp saved --stage in_progress
```

If the saved session expires, run `linkedin-jobs-mcp login` again.

## MCP client configuration

Add this to an MCP client that supports `stdio` servers:

```json
{
  "mcpServers": {
    "linkedin-jobs": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/albertlisage-ux/linkedin-jobs-mcp-server.git",
        "linkedin-jobs-mcp"
      ],
      "env": {
        "UV_HTTP_TIMEOUT": "300"
      }
    }
  }
}
```

For reproducible installs, append a commit or release tag to the Git URL.

## Local development

```bash
git clone https://github.com/albertlisage-ux/linkedin-jobs-mcp-server.git
cd linkedin-jobs-mcp-server
uv sync --group dev
uv run linkedin-jobs-mcp --login
uv run linkedin-jobs-mcp
```

Useful checks:

```bash
uv run ruff check .
uv run pytest
```

Browser-backed tests may download or require Patchright Chromium. LinkedIn
live checks are not part of the default test suite.

## Example requests

Once the server is connected to an MCP client, prompts such as these work:

- “Find remote Python platform engineering jobs posted in the last week.”
- “Search for senior data roles in Berlin and return the job IDs for the first two pages.”
- “Read job `4252026496` and summarize its responsibilities and requirements.”
- “Check whether this posting uses Easy Apply or an employer application page.”
- “List my in-progress LinkedIn jobs.”

`search_jobs` returns LinkedIn's rendered search text, job IDs, pagination
state and references. Feed a returned job ID to `get_job_details`,
`get_job_apply_url` or `get_easy_apply_form`.

## Search filters

`search_jobs` accepts:

- `keywords`
- `location`
- `date_posted`: `past_hour`, `past_24_hours`, `past_week`, `past_month`
- `job_type`: `full_time`, `part_time`, `contract`, `temporary`, `volunteer`, `internship`, `other`
- `experience_level`: `internship`, `entry`, `associate`, `mid_senior`, `director`, `executive`
- `work_type`: `on_site`, `remote`, `hybrid`
- `easy_apply`
- `sort_by`: `date`, `relevance`
- `max_pages`: 1 to 10

LinkedIn is migrating accounts to a redesigned search that may drop some
classic filters. The server reports this in `section_errors` instead of
silently presenting broader results. If location or work type is dropped, try
putting it in the keywords, such as `remote Python developer in Berlin`.

## Authentication and privacy

The browser profile and session data stay on the machine running the server.
The default profile directory is `~/.linkedin-mcp/profile`. Treat that directory
like a password: it contains cookies that can access the account.

The server reads LinkedIn's rendered pages and does not use LinkedIn's private
Voyager API. Automated browser access can still be restricted by LinkedIn and
may be subject to LinkedIn's user agreement. Use conservative request volumes,
do not operate unattended at scale, and stop if LinkedIn presents a captcha,
security challenge or rate-limit page.

`get_easy_apply_form` never submits an application. `dismiss_job` changes the
account's job-search state and is marked destructive.

## Configuration

Copy `.env.example` to `.env` or set environment variables in the MCP client.
The most relevant settings are:

| Variable | Purpose |
| --- | --- |
| `USER_DATA_DIR` | Browser profile and stored-session directory. |
| `HEADLESS` | Run Chromium headlessly; use `false` while debugging login. |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING` or `ERROR`. |
| `TRANSPORT` | `stdio` or `streamable-http`. |
| `TIMEOUT` | Per-page browser timeout in milliseconds. |
| `TOOL_TIMEOUT` | Whole-tool timeout in seconds. |
| `AUTO_IMPORT_FROM_BROWSER` | Reuse a signed-in local browser session. |
| `PROXY_SERVER` | Optional browser-only proxy. |

Run `linkedin-jobs-mcp --help` for the complete option set.

For HTTP mode:

```bash
uv run linkedin-jobs-mcp \
  --transport streamable-http \
  --host 127.0.0.1 \
  --port 8000 \
  --path /mcp
```

Keep the bind address on loopback unless the endpoint is protected. A local
HTTP MCP server can otherwise be reached by a web page the user visits.

## Docker

The repository includes a Dockerfile but does not publish a maintained image.
Build it locally:

```bash
docker build -t linkedin-jobs-mcp .
```

Create the browser session on the host with the same profile directory you
mount into the container:

```bash
uv run linkedin-jobs-mcp --login --user-data-dir "$HOME/.linkedin-mcp/profile"
docker run --rm -i \
  -v "$HOME/.linkedin-mcp:/home/pwuser/.linkedin-mcp" \
  linkedin-jobs-mcp
```

Do not run host and container login/logout commands against the same profile
at the same time.

## Changes from upstream

- The default server registers only job and session tools.
- The MCP server identity and instructions are jobs-specific.
- The package description, CLI help, README and attribution describe a
  jobs-focused product.
- Optional upstream remote-catalog tools are not loaded.
- The existing LinkedIn page-reading, browser-session and job extraction code
  remains the implementation foundation.

## License and attribution

This derivative is distributed under the Apache License 2.0. Upstream code is
Copyright 2025-2026 Daniel Sticker and is based on
[linkedin-mcp-server](https://github.com/stickerdaniel/linkedin-mcp-server).
See [LICENSE](LICENSE), [NOTICE](NOTICE) and
[MODIFICATIONS.md](MODIFICATIONS.md).
