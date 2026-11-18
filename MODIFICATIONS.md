# Modifications from upstream

This repository is derived from
[`stickerdaniel/linkedin-mcp-server`](https://github.com/stickerdaniel/linkedin-mcp-server)
at commit `e9b47a48634200a836571b4e7c02444844038229`.

The derivative keeps the upstream Apache-2.0 license and copyright notice. Its
substantive changes are:

- `linkedin_mcp_server/server.py`: defaults to a job-only tool profile, changes
  the MCP identity and instructions, and retains an explicit `toolset="full"`
  compatibility option for upstream tests.
- `linkedin_mcp_server/__main__.py` and `linkedin_mcp_server/cli_main.py`: run
  the job-only server and no longer load the upstream optional remote catalog.
- `linkedin_mcp_server/direct_cli.py`: adds `login`, `search`, `job` and
  `saved` terminal commands so the same job tools can be used without an MCP
  client, plus an `analyze` command that compares postings with the user's
  LinkedIn profile or a supplied resume text file.
- `linkedin_mcp_server/job_analysis.py`: implements explainable skill,
  seniority, responsibility and requirement matching with visible evidence,
  plus a standalone responsive HTML comparison report with English, Chinese
  and German interface translations, full posting details, prioritized skill
  improvement roadmaps, personalized bridge projects and experience-gap action
  plans, plus resume-driven multi-query job search without an exact title.
- `direct_cli.py`: reads text, Markdown and text-based PDF resumes directly,
  using pypdf for PDF extraction.
- Resume extraction parses name, headline, location, contact, skills, languages,
  certifications, experience, education and projects into explicit sections;
  generated queries prioritize the parsed Top Skills and headline.
- Resume search uses shorter two-term queries and an adaptive fallback that
  relaxes optional filters only after a zero-result search, preserving company
  restrictions and reporting every fallback attempt.
- Job search supports LinkedIn's native location distance facet so a city query
  can include nearby cities within a configurable kilometre radius.
- `linkedin_mcp_server/update_check.py` and
  `linkedin_mcp_server/error_diagnostics.py`: point release and issue diagnostics
  at this derivative instead of the upstream package.
- `pyproject.toml`: adds the `linkedin-jobs-mcp` command, changes product
  metadata, and keeps the upstream distribution and command names for
  compatibility.
- `README.md`, `manifest.json`, extension manifests, documentation strings and
  the bundled skill: narrow product documentation and instructions to LinkedIn
  jobs.
- Tests and CI: add an explicit jobs-only server contract, update the default
  tool expectations, and preserve the upstream full-profile compatibility
  tests through `toolset="full"`.

The LinkedIn browser, authentication, page-capture, pagination, rate-limit and
job extraction implementations are inherited from upstream with only the
product-surface changes above.
