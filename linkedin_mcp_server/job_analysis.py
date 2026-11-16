"""Explainable job-fit analysis built on LinkedIn's captured job text.

The report is intentionally heuristic. It scores evidence found in the user's
profile against terms found in each posting, then prints the matched and missing
terms so the reader can judge the ranking rather than treating it as a promise.
"""

from __future__ import annotations

import re
from collections import Counter
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
