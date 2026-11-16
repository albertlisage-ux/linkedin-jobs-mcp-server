"""Explainable job-fit analysis built on LinkedIn's captured job text.

The report is intentionally heuristic. It scores evidence found in the user's
profile against terms found in each posting, then prints the matched and missing
terms so the reader can judge the ranking rather than treating it as a promise.
"""

from __future__ import annotations

import re
import html
from collections import Counter
from datetime import datetime
from typing import Any


_SKILL_ALIASES: dict[str, tuple[str, ...]] = {
    "A/B Testing": ("a/b testing", "ab testing"),
    "Agile": ("agile",),
    "Airflow": ("airflow", "apache airflow"),
    "Ansible": ("ansible",),
    "AWS": ("aws", "amazon web services"),
    "Azure": ("azure",),
    "Bash": ("bash", "shell scripting"),
    "BigQuery": ("bigquery", "big query"),
    "Business Analysis": ("business analysis", "business analyst"),
    "C#": ("c#", "c sharp"),
    "C++": ("c++",),
    "CI/CD": ("ci/cd", "continuous integration", "continuous delivery"),
    "Computer Vision": ("computer vision",),
    "CRM": ("crm", "customer relationship management"),
    "CSS": ("css",),
    "Customer Success": ("customer success",),
    "Dart": ("dart",),
    "Data Analysis": ("data analysis", "data analytics"),
    "Databricks": ("databricks",),
    "dbt": ("dbt", "data build tool"),
    "Deep Learning": ("deep learning",),
    "Django": ("django",),
    "Docker": ("docker", "containerization"),
    "Elasticsearch": ("elasticsearch", "elastic search"),
    "Excel": ("excel", "microsoft excel"),
    "FastAPI": ("fastapi", "fast api"),
    "Figma": ("figma",),
    "Financial Modeling": ("financial modeling", "financial modelling"),
    "Flask": ("flask",),
    "Flutter": ("flutter",),
    "GCP": ("gcp", "google cloud", "google cloud platform"),
    "Git": ("git",),
    "GitHub Actions": ("github actions",),
    "Go": ("golang", "go programming"),
    "Grafana": ("grafana",),
    "GraphQL": ("graphql",),
    "HTML": ("html",),
    "Java": ("java",),
    "JavaScript": ("javascript", "java script"),
    "Jenkins": ("jenkins",),
    "Jira": ("jira",),
    "Kafka": ("kafka", "apache kafka"),
    "Kotlin": ("kotlin",),
    "Kubernetes": ("kubernetes", "k8s"),
    "LangChain": ("langchain",),
    "Linux": ("linux",),
    "LLM": ("llm", "large language model", "large language models"),
    "Machine Learning": ("machine learning", "ml engineering"),
    "Marketing": ("marketing", "digital marketing"),
    "MongoDB": ("mongodb", "mongo db"),
    "MLOps": ("mlops", "ml ops"),
    "MySQL": ("mysql",),
    "Natural Language Processing": (
        "natural language processing",
        "nlp",
    ),
    "Next.js": ("next.js", "nextjs"),
    "Node.js": ("node.js", "nodejs"),
    "NumPy": ("numpy",),
    "Pandas": ("pandas",),
    "PostgreSQL": ("postgresql", "postgres"),
    "Power BI": ("power bi", "powerbi"),
    "Product Management": ("product management", "product manager"),
    "Project Management": ("project management", "project manager"),
    "Prometheus": ("prometheus",),
    "Prototyping": ("prototyping",),
    "PyTorch": ("pytorch",),
    "Python": ("python",),
    "Rails": ("ruby on rails", "rails"),
    "React": ("react", "react.js", "reactjs"),
    "Redis": ("redis",),
    "Roadmapping": ("roadmapping", "product roadmap"),
    "Ruby": ("ruby",),
    "Rust": ("rust",),
    "Salesforce": ("salesforce",),
    "SAP": ("sap",),
    "Scala": ("scala",),
    "scikit-learn": ("scikit-learn", "sklearn"),
    "Scrum": ("scrum",),
    "SEO": ("seo", "search engine optimization"),
    "Snowflake": ("snowflake",),
    "Spark": ("apache spark", "pyspark"),
    "Spring": ("spring boot", "spring framework"),
    "SQL": ("sql",),
    "Stakeholder Management": (
        "stakeholder management",
        "stakeholder engagement",
    ),
    "Swift": ("swift",),
    "Tableau": ("tableau",),
    "TensorFlow": ("tensorflow",),
    "Terraform": ("terraform",),
    "TypeScript": ("typescript",),
    "UI Design": ("ui design", "user interface design"),
    "UX": ("ux", "user experience"),
    "Vue": ("vue.js", "vuejs"),
    "Wireframing": ("wireframing", "wireframe"),
}

_SENIORITY_LEVELS = {
    "internship": 0,
    "entry": 1,
    "junior": 1,
    "mid": 2,
    "senior": 3,
    "staff": 4,
    "lead": 4,
    "principal": 5,
    "manager": 5,
    "director": 6,
    "head": 6,
    "executive": 7,
    "vice president": 7,
    "vp": 7,
}

_ROLE_STOPWORDS = {
    "a",
    "and",
    "at",
    "developer",
    "engineer",
    "for",
    "hybrid",
    "in",
    "job",
    "of",
    "on",
    "onsite",
    "remote",
    "role",
    "the",
    "with",
}

_SKILL_NOISE = {
    "add",
    "all",
    "close",
    "edit",
    "education",
    "experience",
    "follow",
    "main",
    "profile",
    "see",
    "show",
    "show all",
    "skills",
    "view",
}

_RESPONSIBILITY_HEADINGS = {
    "responsibilities",
    "the role",
    "what you'll do",
    "what you will do",
    "what you’ll do",
    "your role",
}

_REQUIREMENT_HEADINGS = {
    "qualifications",
    "requirements",
    "skills",
    "what we're looking for",
    "what we’re looking for",
    "what you'll need",
    "what you’ll need",
    "who you are",
    "you have",
}

_KNOWN_HEADINGS = {
    "about the job",
    "about this job",
    "benefits",
    "description",
    "responsibilities",
    "role",
    "skills",
    "the role",
    "what you'll do",
    "what you will do",
    "what you’ll do",
    "what we're looking for",
    "what we’re looking for",
    "what you'll need",
    "what you’ll need",
    "who you are",
    "you have",
    "qualifications",
    "requirements",
}


def _term_pattern(term: str) -> re.Pattern[str]:
    escaped = re.escape(term).replace(r"\ ", r"\s+")
    return re.compile(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", re.IGNORECASE)


_COMPILED_ALIASES = {
    canonical: tuple(_term_pattern(alias) for alias in aliases)
    for canonical, aliases in _SKILL_ALIASES.items()
}


def _find_skill_terms(text: str) -> set[str]:
    return {
        canonical
        for canonical, patterns in _COMPILED_ALIASES.items()
        if any(pattern.search(text) for pattern in patterns)
    }


def _clean_lines(text: str) -> list[str]:
    cleaned: list[str] = []
    for raw in text.splitlines():
        line = raw.strip().lstrip("•-–—* ").strip()
        if line:
            cleaned.append(re.sub(r"\s+", " ", line))
    return cleaned


def _profile_skill_lines(profile: dict[str, Any]) -> list[str]:
    sections = profile.get("sections")
    if not isinstance(sections, dict):
        return []
    skills_text = sections.get("skills")
    if not isinstance(skills_text, str):
        return []

    out: list[str] = []
    seen: set[str] = set()
    for line in _clean_lines(skills_text):
        normalized = line.casefold()
        if normalized in _SKILL_NOISE:
            continue
        if len(line) < 2 or len(line) > 80:
            continue
        if normalized.startswith(("show all", "show ", "skills (")):
            continue
        if normalized not in seen:
            seen.add(normalized)
            out.append(line)
    return out


def _profile_terms(profile: dict[str, Any]) -> set[str]:
    sections = profile.get("sections")
    profile_text = (
        "\n".join(str(value) for value in sections.values())
        if isinstance(sections, dict)
        else ""
    )
    return _find_skill_terms(profile_text)


def _job_terms(
    job_text: str,
    profile_skill_lines: list[str],
) -> tuple[set[str], set[str]]:
    job_skills = _find_skill_terms(job_text)
    canonical_by_fold = {
        alias.casefold(): canonical
        for canonical, aliases in _SKILL_ALIASES.items()
        for alias in aliases
    }
    for line in profile_skill_lines:
        pattern = _term_pattern(line)
        if not pattern.search(job_text):
            continue
        canonical = canonical_by_fold.get(line.casefold())
        job_skills.add(canonical or line)
    return job_skills, set(profile_skill_lines)


def _significant_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9+#.]+", text.casefold())
        if len(token) > 1 and token not in _ROLE_STOPWORDS
    }


def _detect_level(text: str) -> tuple[str, int | None]:
    folded = text.casefold()
    for phrase in (
        "vice president",
        "principal",
        "director",
        "executive",
        "manager",
        "staff",
        "lead",
        "senior",
        "junior",
        "entry",
        "internship",
        "intern",
        "mid-level",
        "mid level",
    ):
        if re.search(rf"(?<![a-z]){re.escape(phrase)}(?![a-z])", folded):
            normalized = "mid" if phrase.startswith("mid") else phrase
            return normalized, _SENIORITY_LEVELS.get(normalized)
    return "unspecified", None


def _level_alignment(job_level: int | None, profile_level: int | None) -> float:
    if job_level is None or profile_level is None:
        return 0.6
    difference = abs(job_level - profile_level)
    if difference <= 1:
        return 1.0
    if difference == 2:
        return 0.5
    return 0.2


def _header_parts(
    job_text: str,
    fallback_title: str,
) -> tuple[str | None, str | None, str | None]:
    company: str | None = None
    location: str | None = None
    lines = _clean_lines(job_text)
    for line in lines[:15]:
        folded = line.casefold()
        if folded in _KNOWN_HEADINGS:
            break
        if " · " not in line:
            continue
        parts = [part.strip() for part in line.split(" · ") if part.strip()]
        if len(parts) >= 2:
            if company is None and parts[0].casefold() != fallback_title.casefold():
                company = parts[0]
            location = parts[1]
            break
    return company, location, None


def _work_mode(text: str) -> str:
    folded = text.casefold()
    for value in ("hybrid", "remote", "on-site", "on site", "onsite"):
        if re.search(rf"(?<![a-z]){re.escape(value)}(?![a-z])", folded):
            return "on_site" if value in {"on-site", "on site", "onsite"} else value
    return "unspecified"


def _employment_type(text: str) -> str:
    folded = text.casefold()
    for value in (
        "full-time",
        "full time",
        "part-time",
        "part time",
        "contract",
        "temporary",
        "internship",
    ):
        if re.search(rf"(?<![a-z]){re.escape(value)}(?![a-z])", folded):
            return value.replace(" ", "_").replace("-", "_")
    return "unspecified"


def _section_items(
    job_text: str,
    headings: set[str],
    *,
    limit: int = 5,
) -> list[str]:
    lines = _clean_lines(job_text)
    start: int | None = None
    for index, line in enumerate(lines):
        if line.casefold().rstrip(":") in headings:
            start = index + 1
            break
    if start is None:
        return []

    items: list[str] = []
    for line in lines[start:]:
        folded = line.casefold().rstrip(":")
        if folded in _KNOWN_HEADINGS:
            break
        if len(line) < 10:
            continue
        items.append(line)
        if len(items) == limit:
            break
    return items


def _description_excerpt(job_text: str, limit: int = 500) -> str:
    lines = _clean_lines(job_text)
    start = 0
    for index, line in enumerate(lines):
        if line.casefold() in {"about the job", "about this job", "description"}:
            start = index + 1
            break
    excerpt = " ".join(lines[start:])
    if len(excerpt) <= limit:
        return excerpt
    cut = excerpt[:limit].rsplit(" ", 1)[0]
    return f"{cut}..."


def _years_required(text: str) -> int | None:
    matches = [
        int(value)
        for value in re.findall(
            r"(?<!\d)(\d{1,2})\+?\s*(?:years?|yrs?)(?:\s+of)?\s+experience",
            text,
            re.IGNORECASE,
        )
    ]
    return min(matches) if matches else None


def _rating(score: int) -> tuple[str, str]:
    if score >= 70:
        return "strong_match", "Strong match"
    if score >= 55:
        return "good_match", "Good match"
    if score >= 40:
        return "possible_match", "Worth reviewing"
    return "stretch", "Stretch"


def _analyze_one_job(
    *,
    query: str,
    entry: dict[str, str],
    details: dict[str, Any],
    profile_skills: set[str],
    profile_skill_lines: list[str],
    profile_level: int | None,
    profile_level_name: str,
) -> dict[str, Any]:
    section = details.get("sections", {}).get("job_posting", "")
    job_text = str(section or "")
    job_skills, expanded_profile_skills = _job_terms(job_text, profile_skill_lines)
    known_profile = profile_skills | expanded_profile_skills
    matched = sorted(job_skills & known_profile, key=str.casefold)
    missing = sorted(job_skills - known_profile, key=str.casefold)

    query_tokens = _significant_tokens(query)
    title = entry.get("title", "")
    title_tokens = _significant_tokens(f"{title} {job_text[:800]}")
    role_alignment = (
        len(query_tokens & title_tokens) / len(query_tokens)
        if query_tokens
        else 0.0
    )

    level_name, job_level = _detect_level(title)
    if job_level is None:
        level_name, job_level = _detect_level(job_text[:1200])
    seniority_fit = _level_alignment(job_level, profile_level)
    coverage = len(matched) / len(job_skills) if job_skills else 0.0
    score = round(
        100 * (0.55 * coverage + 0.30 * role_alignment + 0.15 * seniority_fit)
    )
    score = max(0, min(100, score))
    rating_key, rating = _rating(score)
    company, location, _ = _header_parts(job_text, title)

    section_errors = details.get("section_errors")
    error_message = None
    if isinstance(section_errors, dict):
        for detail in section_errors.values():
            if isinstance(detail, dict):
                error_message = detail.get("error_message")
                if error_message:
                    break

    return {
        "job_id": entry["id"],
        "title": title or f"LinkedIn job {entry['id']}",
        "company": company,
        "location": location,
        "url": entry["url"],
        "fit_score": score,
        "fit_rating": rating,
        "fit_rating_key": rating_key,
        "confidence": (
            "high"
            if len(profile_skills) >= 5 and len(job_skills) >= 5 and len(job_text) > 800
            else "medium"
            if job_skills and job_text
            else "low"
        ),
        "matched_skills": matched,
        "missing_skills": missing,
        "job_level": level_name,
        "profile_level": profile_level_name,
        "seniority_alignment": round(seniority_fit, 2),
        "work_mode": _work_mode(job_text[:2000]),
        "employment_type": _employment_type(job_text[:2000]),
        "years_required": _years_required(job_text),
        "responsibilities": _section_items(
            job_text, _RESPONSIBILITY_HEADINGS
        ),
        "requirements": _section_items(job_text, _REQUIREMENT_HEADINGS),
        "description_excerpt": _description_excerpt(job_text),
        "error": error_message,
    }


def analyze_job_fit(
    *,
    query: str,
    search_result: dict[str, Any],
    profile: dict[str, Any],
    job_details: list[dict[str, Any]],
    limit: int = 5,
) -> dict[str, Any]:
    """Rank captured jobs against the profile evidence available."""
    from linkedin_mcp_server.direct_cli import _job_entries

    entries = _job_entries(search_result)
    selected = entries if limit == 0 else entries[: max(0, limit)]
    profile_skills = _profile_terms(profile)
    profile_skill_lines = _profile_skill_lines(profile)
    sections = profile.get("sections", {})
    profile_level_text = (
        "\n".join(
            str(sections.get(name, ""))
            for name in ("experience", "main_profile")
        )
        if isinstance(sections, dict)
        else ""
    )
    profile_level_name, profile_level = _detect_level(profile_level_text)

    jobs: list[dict[str, Any]] = []
    for index, entry in enumerate(selected):
        details = job_details[index] if index < len(job_details) else {}
        jobs.append(
            _analyze_one_job(
                query=query,
                entry=entry,
                details=details,
                profile_skills=profile_skills,
                profile_skill_lines=profile_skill_lines,
                profile_level=profile_level,
                profile_level_name=profile_level_name,
            )
        )
    jobs.sort(key=lambda item: (-item["fit_score"], item["title"].casefold()))

    strength_counts = Counter(
        skill for job in jobs for skill in job["matched_skills"]
    )
    gap_counts = Counter(skill for job in jobs for skill in job["missing_skills"])
    rating_counts = Counter(job["fit_rating_key"] for job in jobs)
    return {
        "query": query,
        "profile_url": profile.get("url"),
        "profile_sections_read": sorted(sections) if isinstance(sections, dict) else [],
        "profile_skills_detected": sorted(profile_skills, key=str.casefold),
        "profile_level": profile_level_name,
        "jobs_returned": len(entries),
        "jobs_analyzed": len(jobs),
        "rating_counts": {
            "strong_match": rating_counts["strong_match"],
            "good_match": rating_counts["good_match"],
            "possible_match": rating_counts["possible_match"],
            "stretch": rating_counts["stretch"],
        },
        "common_strengths": [
            {"skill": skill, "jobs": count}
            for skill, count in strength_counts.most_common(8)
        ],
        "common_gaps": [
            {"skill": skill, "jobs": count}
            for skill, count in gap_counts.most_common(8)
        ],
        "jobs": jobs,
        "methodology": (
            "Fit is a heuristic based on skill evidence found in the captured "
            "profile and posting, query/title overlap, and observed seniority "
            "signals. It is not a hiring probability or an employer decision."
        ),
    }


def format_fit_report(report: dict[str, Any]) -> str:
    """Format an overview followed by detailed evidence for each job."""
    counts = report["rating_counts"]
    lines = [
        "LINKEDIN JOB FIT OVERVIEW",
        "",
        f'Search: {report["query"]}',
        f'Profile: {report.get("profile_url") or "supplied profile document"}',
        (
            "Profile signals: "
            f'{report.get("profile_level", "unspecified")}; '
            f'{len(report.get("profile_skills_detected", []))} skills detected'
        ),
        (
            f'Analysed: {report["jobs_analyzed"]} jobs '
            f'(strong {counts["strong_match"]}, good {counts["good_match"]}, '
            f'worth reviewing {counts["possible_match"]}, '
            f'stretch {counts["stretch"]})'
        ),
    ]

    strengths = ", ".join(
        item["skill"] for item in report.get("common_strengths", [])[:6]
    )
    gaps = ", ".join(item["skill"] for item in report.get("common_gaps", [])[:6])
    if strengths:
        lines.append(f"Most repeated strengths: {strengths}")
    if gaps:
        lines.append(f"Most repeated gaps: {gaps}")
    lines.extend(("", "METHODOLOGY", report["methodology"]))

    for position, job in enumerate(report["jobs"], start=1):
        lines.extend(
            (
                "",
                f'{position}. [{job["fit_rating"]}] {job["title"]}',
                " | ".join(
                    value
                    for value in (
                        job.get("company"),
                        job.get("location"),
                        job.get("work_mode"),
                        job.get("employment_type"),
                    )
                    if value and value != "unspecified"
                ),
                f'Fit score: {job["fit_score"]}/100 ({job["confidence"]} confidence)',
                f'LinkedIn: {job["url"]}',
                f'Job ID: {job["job_id"]}',
                (
                    f'Seniority: posting={job["job_level"]}; '
                    f'profile={job["profile_level"]}'
                ),
            )
        )
        if job.get("years_required") is not None:
            lines.append(f'Experience requested: {job["years_required"]}+ years')
        if job["matched_skills"]:
            lines.append(f'Matched evidence: {", ".join(job["matched_skills"])}')
        if job["missing_skills"]:
            shown = job["missing_skills"][:12]
            suffix = (
                f" (+{len(job['missing_skills']) - len(shown)} more)"
                if len(job["missing_skills"]) > len(shown)
                else ""
            )
            lines.append(
                f'Not found in profile: {", ".join(shown)}{suffix}'
            )
        if job["requirements"]:
            lines.append("Key requirements:")
            lines.extend(f"- {item}" for item in job["requirements"])
        if job["responsibilities"]:
            lines.append("Main responsibilities:")
            lines.extend(f"- {item}" for item in job["responsibilities"])
        if job["description_excerpt"]:
            lines.append(f'Posting snapshot: {job["description_excerpt"]}')
        if job.get("error"):
            lines.append(f'Posting warning: {job["error"]}')
    return "\n".join(lines)


_REPORT_CSS = r"""
:root {
  color-scheme: light dark;
  --background: #f8fafc;
  --surface: #ffffff;
  --surface-raised: #f2f6fd;
  --foreground: #172554;
  --muted-foreground: #4d5f7c;
  --primary: #1e40af;
  --secondary: #2563eb;
  --accent: #b45309;
  --border: #dbe7f7;
  --strong: #166534;
  --strong-soft: #dcfce7;
  --good: #1d4ed8;
  --good-soft: #dbeafe;
  --review: #92400e;
  --review-soft: #fef3c7;
  --stretch: #991b1b;
  --stretch-soft: #fee2e2;
  --shadow: 0 18px 45px rgba(30, 64, 175, 0.09);
  --radius: 18px;
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 24px;
  --space-6: 32px;
  --space-7: 48px;
}

@media (prefers-color-scheme: dark) {
  :root {
    --background: #08111f;
    --surface: #101c2e;
    --surface-raised: #16253b;
    --foreground: #e8f0ff;
    --muted-foreground: #adc0dd;
    --primary: #8bb4ff;
    --secondary: #67e8f9;
    --accent: #fbbf24;
    --border: #29405e;
    --strong: #86efac;
    --strong-soft: #123522;
    --good: #93c5fd;
    --good-soft: #142b4a;
    --review: #fcd34d;
    --review-soft: #3b2b08;
    --stretch: #fca5a5;
    --stretch-soft: #441616;
    --shadow: 0 18px 45px rgba(0, 0, 0, 0.28);
  }
}

* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  background:
    radial-gradient(circle at top left, rgba(37, 99, 235, 0.13), transparent 32rem),
    var(--background);
  color: var(--foreground);
  font-family: "Fira Sans", "Avenir Next", "Segoe UI", sans-serif;
  font-size: 16px;
  line-height: 1.6;
}
a { color: var(--primary); }
a:hover { color: var(--accent); }
a:focus-visible, summary:focus-visible {
  outline: 3px solid var(--accent);
  outline-offset: 3px;
  border-radius: 4px;
}
.skip-link {
  position: absolute;
  left: 16px;
  top: -80px;
  z-index: 100;
  padding: 12px 16px;
  background: var(--surface);
  color: var(--foreground);
  border: 1px solid var(--border);
  border-radius: 10px;
}
.skip-link:focus { top: 16px; }
.shell {
  width: min(1180px, calc(100% - 32px));
  margin: 0 auto;
  padding: 48px 0 72px;
}
.hero {
  padding: clamp(24px, 5vw, 48px);
  background: linear-gradient(135deg, var(--surface), var(--surface-raised));
  border: 1px solid var(--border);
  border-radius: 28px;
  box-shadow: var(--shadow);
}
.eyebrow {
  margin: 0 0 8px;
  color: var(--accent);
  font: 600 0.78rem/1.3 "Fira Code", ui-monospace, monospace;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}
h1, h2, h3, h4 {
  margin-top: 0;
  font-family: "Fira Code", ui-monospace, monospace;
  line-height: 1.25;
  letter-spacing: -0.03em;
}
h1 { max-width: 22ch; margin-bottom: 12px; font-size: clamp(2rem, 6vw, 4rem); }
h2 { margin-bottom: 20px; font-size: clamp(1.4rem, 3vw, 2rem); }
h3 { margin-bottom: 8px; font-size: 1.25rem; }
h4 { margin: 24px 0 8px; font-size: 0.95rem; }
.hero-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 18px;
  color: var(--muted-foreground);
}
.section { margin-top: 48px; }
.stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin: 24px 0 0;
}
.stat {
  min-height: 132px;
  padding: 20px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
}
.stat strong {
  display: block;
  margin-bottom: 4px;
  font: 700 2rem/1 "Fira Code", ui-monospace, monospace;
}
.stat span { color: var(--muted-foreground); }
.signals {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}
.panel {
  padding: 22px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
.chips { display: flex; flex-wrap: wrap; gap: 8px; }
.chip {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 4px 10px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface-raised);
  color: var(--foreground);
  font-size: 0.88rem;
}
.chip.missing {
  border-color: color-mix(in srgb, var(--stretch) 28%, var(--border));
  background: var(--stretch-soft);
  color: var(--stretch);
}
.table-wrap {
  overflow-x: auto;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
}
table { width: 100%; border-collapse: collapse; }
caption {
  padding: 16px 20px;
  color: var(--muted-foreground);
  text-align: left;
}
th, td {
  padding: 14px 16px;
  border-top: 1px solid var(--border);
  text-align: left;
  vertical-align: top;
}
th {
  color: var(--muted-foreground);
  font: 600 0.78rem/1.4 "Fira Code", ui-monospace, monospace;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.score {
  display: inline-flex;
  align-items: baseline;
  gap: 2px;
  font: 700 1.05rem/1 "Fira Code", ui-monospace, monospace;
  font-variant-numeric: tabular-nums;
}
.score small { color: var(--muted-foreground); font-size: 0.68rem; }
.badge {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 3px 10px;
  border-radius: 999px;
  font-weight: 600;
  white-space: nowrap;
}
.strong_match { color: var(--strong); background: var(--strong-soft); }
.good_match { color: var(--good); background: var(--good-soft); }
.possible_match { color: var(--review); background: var(--review-soft); }
.stretch { color: var(--stretch); background: var(--stretch-soft); }
.score-track {
  height: 8px;
  margin-top: 10px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--surface-raised);
}
.score-fill {
  width: var(--score);
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--secondary), var(--accent));
}
.job-list { display: grid; gap: 20px; }
.job-card {
  overflow: hidden;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 22px;
  box-shadow: var(--shadow);
  scroll-margin-top: 24px;
}
.job-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(180px, 240px);
  gap: 24px;
  padding: 24px;
  background: linear-gradient(135deg, var(--surface-raised), var(--surface));
  border-bottom: 1px solid var(--border);
}
.job-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  color: var(--muted-foreground);
}
.job-body {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 24px;
  padding: 24px;
}
.job-body > .full { grid-column: 1 / -1; }
.job-body ul { margin: 0; padding-left: 1.2rem; }
.job-body li + li { margin-top: 7px; }
.snapshot {
  padding: 16px 18px;
  border-left: 4px solid var(--secondary);
  border-radius: 0 12px 12px 0;
  background: var(--surface-raised);
  color: var(--muted-foreground);
}
.warning {
  padding: 12px 14px;
  border-radius: 12px;
  background: var(--review-soft);
  color: var(--review);
}
.methodology {
  padding: 20px 22px;
  border: 1px dashed var(--border);
  border-radius: var(--radius);
  color: var(--muted-foreground);
}
footer { margin-top: 48px; color: var(--muted-foreground); font-size: 0.9rem; }
.button {
  display: inline-flex;
  align-items: center;
  min-height: 44px;
  padding: 10px 16px;
  border: 1px solid var(--primary);
  border-radius: 12px;
  color: var(--primary);
  font-weight: 600;
  text-decoration: none;
}
.button:hover {
  background: var(--primary);
  color: var(--surface);
  transition: background-color 180ms ease-out, color 180ms ease-out;
}
@media (max-width: 800px) {
  .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .signals, .job-body { grid-template-columns: 1fr; }
  .job-head { grid-template-columns: 1fr; }
  .job-body > .full { grid-column: auto; }
}
@media (max-width: 620px) {
  .shell { width: min(100% - 20px, 1180px); padding-top: 20px; }
  .hero { border-radius: 20px; }
  .stats { gap: 10px; }
  .stat { min-height: 110px; padding: 16px; }
  .table-wrap { overflow: visible; background: transparent; border: 0; box-shadow: none; }
  table, thead, tbody, tr, th, td { display: block; }
  thead { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
  tr {
    margin-bottom: 12px;
    padding: 14px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 16px;
  }
  td { border: 0; padding: 5px 0; }
  td[data-label]::before {
    content: attr(data-label) ": ";
    color: var(--muted-foreground);
    font-weight: 600;
  }
}
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
  * { transition-duration: 0.01ms !important; animation-duration: 0.01ms !important; }
}
@media print {
  body { background: white; color: #111827; }
  .shell { width: 100%; padding: 0; }
  .hero, .stat, .panel, .table-wrap, .job-card { box-shadow: none; break-inside: avoid; }
  .job-card { margin-bottom: 16px; }
  .button { display: none; }
}
"""


def _e(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _safe_href(value: Any) -> str:
    url = str(value or "")
    if url.startswith(("https://", "http://")):
        return html.escape(url, quote=True)
    return "#"


def _chip_list(items: list[str], *, missing: bool = False) -> str:
    if not items:
        return '<p class="snapshot">None detected.</p>'
    css = "chip missing" if missing else "chip"
    return '<div class="chips">' + "".join(
        f'<span class="{css}">{_e(item)}</span>' for item in items
    ) + "</div>"


def _list_html(items: list[str], empty: str) -> str:
    if not items:
        return f'<p class="snapshot">{_e(empty)}</p>'
    return "<ul>" + "".join(f"<li>{_e(item)}</li>" for item in items) + "</ul>"


def render_fit_report_html(
    report: dict[str, Any],
    *,
    generated_at: str | None = None,
) -> str:
    """Render a standalone, responsive comparison report."""
    generated_at = generated_at or datetime.now().astimezone().strftime(
        "%Y-%m-%d %H:%M %Z"
    )
    counts = report["rating_counts"]
    query = _e(report.get("query"))
    profile_url = _safe_href(report.get("profile_url"))
    profile_label = _e(report.get("profile_url") or "Supplied profile document")

    summary_rows = "".join(
        f"""
        <tr>
          <td data-label="Job"><a href="#job-{_e(job['job_id'])}">{_e(job['title'])}</a></td>
          <td data-label="Company">{_e(job.get('company') or 'Not captured')}</td>
          <td data-label="Location">{_e(job.get('location') or 'Not specified')}</td>
          <td data-label="Score"><span class="score">{_e(job['fit_score'])}<small>/100</small></span></td>
          <td data-label="Assessment"><span class="badge {_e(job['fit_rating_key'])}">{_e(job['fit_rating'])}</span></td>
          <td data-label="Matched">{_e(', '.join(job['matched_skills'][:5]) or 'No direct matches')}</td>
        </tr>
        """
        for job in report["jobs"]
    )

    job_cards: list[str] = []
    for index, job in enumerate(report["jobs"], start=1):
        details = [
            (
                f'Work mode: {job["work_mode"]}'
                if job.get("work_mode") != "unspecified"
                else "Work mode: not clear"
            ),
            (
                f'Employment: {job["employment_type"]}'
                if job.get("employment_type") != "unspecified"
                else "Employment type: not clear"
            ),
            f'Posting seniority: {job.get("job_level")}',
            f'Profile seniority: {job.get("profile_level")}',
        ]
        if job.get("years_required") is not None:
            details.append(f'{job["years_required"]}+ years requested')
        warning = (
            f'<p class="warning"><strong>Posting warning:</strong> '
            f'{_e(job["error"])}</p>'
            if job.get("error")
            else ""
        )
        snapshot = (
            f'<p class="snapshot">{_e(job["description_excerpt"])}</p>'
            if job.get("description_excerpt")
            else ""
        )
        job_cards.append(
            f"""
            <article class="job-card" id="job-{_e(job['job_id'])}">
              <header class="job-head">
                <div>
                  <p class="eyebrow">Detailed assessment {index}</p>
                  <h3>{_e(job['title'])}</h3>
                  <div class="job-meta">
                    <span>{_e(job.get('company') or 'Company not captured')}</span>
                    <span>{_e(job.get('location') or 'Location not captured')}</span>
                    <a href="{_safe_href(job['url'])}">Open LinkedIn posting</a>
                  </div>
                </div>
                <div>
                  <span class="badge {_e(job['fit_rating_key'])}">{_e(job['fit_rating'])}</span>
                  <div class="score">{_e(job['fit_score'])}<small>/100</small></div>
                  <div class="score-track" role="img" aria-label="Fit score {_e(job['fit_score'])} out of 100">
                    <div class="score-fill" style="--score:{_e(job['fit_score'])}%"></div>
                  </div>
                  <p class="job-meta">{_e(job['confidence'])} confidence</p>
                </div>
              </header>
              <div class="job-body">
                <section>
                  <h4>Matched profile evidence</h4>
                  {_chip_list(job['matched_skills'])}
                </section>
                <section>
                  <h4>Skills not found in profile</h4>
                  {_chip_list(job['missing_skills'], missing=True)}
                </section>
                <section class="full">
                  <h4>Role signals</h4>
                  <div class="chips">
                    {''.join(f'<span class="chip">{_e(item)}</span>' for item in details)}
                  </div>
                </section>
                <section>
                  <h4>Key requirements</h4>
                  {_list_html(job['requirements'], 'Requirements were not isolated from this posting.')}
                </section>
                <section>
                  <h4>Main responsibilities</h4>
                  {_list_html(job['responsibilities'], 'Responsibilities were not isolated from this posting.')}
                </section>
                <section class="full">
                  <h4>Posting snapshot</h4>
                  {snapshot or '<p class="snapshot">No description snapshot was captured.</p>'}
                  {warning}
                  <p><a class="button" href="{_safe_href(job['url'])}">View full LinkedIn posting</a></p>
                </section>
              </div>
            </article>
            """
        )

    strengths = "".join(
        f'<span class="chip">{_e(item["skill"])} · {_e(item["jobs"])} jobs</span>'
        for item in report.get("common_strengths", [])
    )
    gaps = "".join(
        f'<span class="chip missing">{_e(item["skill"])} · {_e(item["jobs"])} jobs</span>'
        for item in report.get("common_gaps", [])
    )
    profile_link = (
        f'<a href="{profile_url}">{profile_label}</a>'
        if profile_url != "#"
        else profile_label
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light dark">
  <title>LinkedIn Job Fit Report · {query}</title>
  <style>{_REPORT_CSS}</style>
</head>
<body>
  <a class="skip-link" href="#main">Skip to report</a>
  <main class="shell" id="main">
    <header class="hero">
      <p class="eyebrow">LinkedIn job comparison</p>
      <h1>Fit report for “{query}”</h1>
      <div class="hero-meta">
        <span>Generated {_e(generated_at)}</span>
        <span>Profile: {profile_link}</span>
        <span>{_e(report['jobs_analyzed'])} jobs analysed</span>
      </div>
      <p>{_e(report['methodology'])}</p>
    </header>

    <section class="section" aria-labelledby="overview-heading">
      <h2 id="overview-heading">Overview</h2>
      <div class="stats">
        <div class="stat"><strong>{_e(counts['strong_match'])}</strong><span>Strong matches</span></div>
        <div class="stat"><strong>{_e(counts['good_match'])}</strong><span>Good matches</span></div>
        <div class="stat"><strong>{_e(counts['possible_match'])}</strong><span>Worth reviewing</span></div>
        <div class="stat"><strong>{_e(counts['stretch'])}</strong><span>Stretch roles</span></div>
      </div>
      <div class="signals" style="margin-top:16px">
        <section class="panel">
          <h3>Repeated strengths</h3>
          <div class="chips">{strengths or '<span class="chip">No repeated skill matches</span>'}</div>
        </section>
        <section class="panel">
          <h3>Repeated gaps</h3>
          <div class="chips">{gaps or '<span class="chip">No repeated skill gaps</span>'}</div>
        </section>
      </div>
    </section>

    <section class="section" aria-labelledby="comparison-heading">
      <h2 id="comparison-heading">Job comparison</h2>
      <div class="table-wrap">
        <table>
          <caption>Ranked from strongest to weakest evidence match.</caption>
          <thead>
            <tr>
              <th scope="col">Job</th>
              <th scope="col">Company</th>
              <th scope="col">Location</th>
              <th scope="col">Score</th>
              <th scope="col">Assessment</th>
              <th scope="col">Matched evidence</th>
            </tr>
          </thead>
          <tbody>{summary_rows}</tbody>
        </table>
      </div>
    </section>

    <section class="section" aria-labelledby="details-heading">
      <h2 id="details-heading">Detailed comparison</h2>
      <div class="job-list">{''.join(job_cards) or '<p class="panel">No job postings were returned.</p>'}</div>
    </section>

    <aside class="methodology">
      <strong>How to read this report.</strong> A high score means more of the
      captured posting language overlaps the profile evidence and the role/title
      signals align. A missing skill means it was not found in the captured
      profile sections; it does not prove the skill is absent from your
      experience. Use the evidence to decide what to verify before applying.
    </aside>
    <footer>
      Generated locally by LinkedIn Jobs MCP Server. LinkedIn is a trademark of
      LinkedIn Corporation. This independent report is not affiliated with LinkedIn.
    </footer>
  </main>
</body>
</html>
"""
