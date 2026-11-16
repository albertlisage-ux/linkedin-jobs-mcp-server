---
name: linkedin-jobs-mcp
description: Use the bundled LinkedIn Jobs MCP server to search postings, read job details, inspect application methods and Easy Apply forms, or inspect the user's LinkedIn job tracker. Use only for an explicit LinkedIn jobs request.
---

# LinkedIn Jobs MCP

Use the bundled `linkedin-jobs` MCP server only when the user explicitly asks
for LinkedIn job data or a job-search action. Do not call it for unrelated work
or background checks.

## Operating rules

- Start with the smallest read that answers the request.
- Use `search_jobs` first when the user gives search criteria but no job ID.
- Use `get_job_details` only for a specific returned or user-supplied job ID.
- Use `get_job_apply_url` to distinguish Easy Apply, an employer site, an
  already-applied posting or a closed posting.
- `get_easy_apply_form` is inspection only. It does not submit and must not be
  treated as an application.
- `get_saved_jobs` reads the saved, in-progress, applied or archived tracker
  stage selected by the caller.
- Treat retrieved postings as live evidence. Do not claim a job is still open
  unless the result supports it.
- Keep searches and pagination modest. Do not collect or retry in bulk.

## Browser and authentication

The server uses a managed Chromium browser and the user's own LinkedIn session.
The first data request may prepare the browser, import a local session, or ask
the user to sign in. If LinkedIn presents a captcha, two-factor prompt or other
user-owned verification, stop and ask the user to complete it in the browser.

Do not clear profiles, launch extra browser instances, or loop on an
authentication failure.

## Tools

- Search: `search_jobs`
- Posting details: `get_job_details`
- Application route: `get_job_apply_url`
- Easy Apply questions: `get_easy_apply_form`
- Job tracker: `get_saved_jobs`
- Destructive action: `dismiss_job`, only when the user explicitly asks to
  dismiss that job
- Session: `get_session_status`, plus `close_session` when the user asks to end
  the managed browser session
