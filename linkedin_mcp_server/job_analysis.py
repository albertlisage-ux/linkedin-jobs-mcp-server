"""Explainable job-fit analysis built on LinkedIn's captured job text.

The report is intentionally heuristic. It scores evidence found in the user's
profile against terms found in each posting, then prints the matched and missing
terms so the reader can judge the ranking rather than treating it as a promise.
"""

from __future__ import annotations

import re
import html
import json
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
    "Business Analysis": (
        "business analysis",
        "business analyst",
        "geschäftsanalyse",
        "业务分析",
    ),
    "C#": ("c#", "c sharp"),
    "C++": ("c++",),
    "CI/CD": ("ci/cd", "continuous integration", "continuous delivery"),
    "Computer Vision": ("computer vision",),
    "CRM": ("crm", "customer relationship management"),
    "CSS": ("css",),
    "Customer Success": ("customer success",),
    "Dart": ("dart",),
    "Data Analysis": (
        "data analysis",
        "data analytics",
        "datenanalyse",
        "数据分析",
    ),
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
    "Machine Learning": (
        "machine learning",
        "ml engineering",
        "maschinelles lernen",
        "机器学习",
    ),
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
    "Product Management": (
        "product management",
        "product manager",
        "produktmanagement",
        "产品管理",
    ),
    "Project Management": (
        "project management",
        "project manager",
        "projektmanagement",
        "项目管理",
    ),
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
        "stakeholder-management",
        "利益相关者管理",
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

_DOMAIN_SIGNALS: dict[str, tuple[str, ...]] = {
    "data": ("data", "analytics", "pipeline", "etl", "warehouse"),
    "machine learning": ("machine learning", "artificial intelligence", "ai"),
    "cloud": ("cloud", "aws", "azure", "gcp"),
    "software": ("software", "application", "backend", "frontend"),
    "devops": ("devops", "platform", "infrastructure", "reliability"),
    "product": ("product", "roadmap", "customer"),
    "design": ("design", "user experience", "prototype"),
    "security": ("security", "cybersecurity", "compliance"),
    "finance": ("finance", "financial", "accounting"),
    "marketing": ("marketing", "brand", "campaign"),
    "sales": ("sales", "revenue", "account management"),
    "healthcare": ("healthcare", "clinical", "medical"),
}

_RESPONSIBILITY_HEADINGS = {
    "responsibilities",
    "the role",
    "what you'll do",
    "what you will do",
    "what you’ll do",
    "your role",
    "aufgaben",
    "deine aufgaben",
    "deine rolle",
    "ihre aufgaben",
    "ihre rolle",
    "was du machst",
    "was sie tun",
    "主要职责",
    "职位职责",
    "岗位职责",
    "工作职责",
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
    "anforderungen",
    "das bringen sie mit",
    "das bringst du mit",
    "dein profil",
    "ihr profil",
    "qualifikationen",
    "voraussetzungen",
    "was du mitbringst",
    "was sie mitbringen",
    "任职要求",
    "岗位要求",
    "资格要求",
    "职位要求",
    "我们希望你",
}

_BENEFIT_HEADINGS = {
    "benefits",
    "perks",
    "what we offer",
    "what we can offer you",
    "what you'll get",
    "what you’ll get",
    "why join us",
    "benefits",
    "darauf kannst du dich freuen",
    "leistungen",
    "unser angebot",
    "was wir bieten",
    "wir bieten",
    "福利待遇",
    "我们提供",
    "职位福利",
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
    "benefits",
    "perks",
    "what we offer",
    "what we can offer you",
    "what you'll get",
    "what you’ll get",
    "why join us",
    "aufgaben",
    "deine aufgaben",
    "deine rolle",
    "ihre aufgaben",
    "ihre rolle",
    "was du machst",
    "was sie tun",
    "anforderungen",
    "das bringen sie mit",
    "das bringst du mit",
    "dein profil",
    "ihr profil",
    "qualifikationen",
    "voraussetzungen",
    "was du mitbringst",
    "was sie mitbringen",
    "darauf kannst du dich freuen",
    "leistungen",
    "unser angebot",
    "was wir bieten",
    "wir bieten",
    "主要职责",
    "职位职责",
    "岗位职责",
    "工作职责",
    "任职要求",
    "岗位要求",
    "资格要求",
    "职位要求",
    "我们希望你",
    "福利待遇",
    "我们提供",
    "职位福利",
}

_RESUME_HEADINGS: dict[str, str] = {
    "about": "about",
    "summary": "summary",
    "profile": "summary",
    "experience": "experience",
    "berufserfahrung": "experience",
    "work experience": "experience",
    "top skills": "skills",
    "skills": "skills",
    "technical skills": "skills",
    "languages": "languages",
    "sprachen": "languages",
    "certifications": "certifications",
    "zertifizierungen": "certifications",
    "education": "education",
    "ausbildung": "education",
    "projects": "projects",
    "projekte": "projects",
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


def _count_skill_mentions(text: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for canonical, patterns in _COMPILED_ALIASES.items():
        mentions = sum(len(pattern.findall(text)) for pattern in patterns)
        if mentions:
            counts[canonical] = mentions
    return counts


def generate_resume_search_queries(
    resume_text: str,
    *,
    limit: int = 3,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build broad skill/domain searches without requiring a job title."""
    limit = max(1, min(5, limit))
    sections = profile.get("sections") if isinstance(profile, dict) else None
    if isinstance(sections, dict):
        searchable_parts = [
            str(sections.get(name, ""))
            for name in (
                "headline",
                "summary",
                "about",
                "skills",
                "experience",
                "projects",
                "certifications",
            )
        ]
        search_source = "\n".join(searchable_parts)
        if not search_source.strip():
            search_source = resume_text
    else:
        search_source = resume_text
    skill_counts = _count_skill_mentions(search_source)
    if isinstance(sections, dict):
        canonical_by_alias = {
            alias.casefold(): canonical
            for canonical, aliases in _SKILL_ALIASES.items()
            for alias in aliases
        }
        for line in _profile_skill_lines(profile):
            canonical = canonical_by_alias.get(line.casefold())
            if canonical:
                skill_counts[canonical] += 3
                continue
            matched_terms = _find_skill_terms(line)
            if matched_terms:
                for skill in matched_terms:
                    skill_counts[skill] += 3
            else:
                skill_counts[line] += 3
    skills = [
        skill
        for skill, _ in sorted(
            skill_counts.items(),
            key=lambda item: (-item[1], item[0].casefold()),
        )
    ]
    folded = search_source.casefold()
    domains = sorted(
        (
            domain
            for domain, terms in _DOMAIN_SIGNALS.items()
            if any(_term_pattern(term).search(folded) for term in terms)
        ),
        key=lambda value: (
            -sum(
                len(_term_pattern(term).findall(folded))
                for term in _DOMAIN_SIGNALS[value]
            ),
            value,
        ),
    )

    query_specs: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_query(parts: list[str], basis: list[str]) -> None:
        words = [part for part in parts if part]
        unique_words: list[str] = []
        seen_words: set[str] = set()
        for word in words:
            folded_word = word.casefold()
            if folded_word not in seen_words:
                seen_words.add(folded_word)
                unique_words.append(word)
        query = " ".join(unique_words)[:80].strip()
        if not query or query.casefold() in seen:
            return
        seen.add(query.casefold())
        query_specs.append(
            {
                "query": query,
                "signals": basis,
            }
        )

    if len(skills) >= 3:
        add_query(skills[:2], skills[:2])
        add_query(skills[1:3], skills[1:3])
        if domains:
            add_query([skills[0], domains[0]], [skills[0], domains[0]])
        if len(domains) > 1:
            add_query(
                [skills[2], domains[1]],
                [skills[2], domains[1]],
            )
    elif len(skills) == 2:
        add_query(skills, skills)
        if domains:
            add_query([*skills, domains[0]], [*skills, domains[0]])
        if len(domains) > 1:
            add_query([skills[0], domains[1]], [skills[0], domains[1]])
    elif len(skills) == 1:
        add_query(skills, skills)
        for domain in domains[:2]:
            add_query([skills[0], domain], [skills[0], domain])

    if not query_specs:
        summary_line = ""
        if isinstance(sections, dict):
            summary_line = str(
                sections.get("headline")
                or sections.get("summary")
                or sections.get("about")
                or ""
            ).strip()
        if not summary_line:
            summary_line = next(
                (
                    line
                    for line in _clean_lines(search_source)
                    if len(line) >= 3
                ),
                "",
            )
        if summary_line:
            add_query([summary_line[:60]], ["resume summary"])

    return {
        "queries": query_specs[:limit],
        "skills": skills[:8],
        "domains": domains[:4],
    }


def merge_job_search_results(
    results: list[dict[str, Any]],
    query_specs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Merge several job searches, preserving the query that found each job."""
    job_ids: list[str] = []
    seen_ids: set[str] = set()
    references: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    promoted: list[str] = []
    sections: list[str] = []
    errors: dict[str, Any] = {}

    for index, result in enumerate(results):
        query = (
            str(query_specs[index].get("query", ""))
            if index < len(query_specs)
            else ""
        )
        result_sections = result.get("sections")
        if isinstance(result_sections, dict) and result_sections.get(
            "search_results"
        ):
            sections.append(
                f"Search query: {query}\n{result_sections['search_results']}"
            )
        for raw in (
            result.get("references", {}).get("search_results", [])
            if isinstance(result.get("references"), dict)
            else []
        ):
            if not isinstance(raw, dict):
                continue
            ref = dict(raw)
            if ref.get("kind") == "job":
                ref["search_query"] = query
            url = str(ref.get("url", ""))
            if url in seen_urls:
                continue
            seen_urls.add(url)
            references.append(ref)
        for value in result.get("job_ids", []):
            job_id = str(value)
            if job_id not in seen_ids:
                seen_ids.add(job_id)
                job_ids.append(job_id)
                if not any(
                    ref.get("kind") == "job"
                    and ref.get("url", "").rstrip("/").endswith(f"/{job_id}")
                    for ref in references
                ):
                    references.append(
                        {
                            "kind": "job",
                            "url": f"/jobs/view/{job_id}/",
                            "search_query": query,
                        }
                    )
        promoted.extend(
            str(value)
            for value in result.get("promoted_job_ids", [])
            if str(value) not in promoted
        )
        result_errors = result.get("section_errors")
        if isinstance(result_errors, dict):
            for section, detail in result_errors.items():
                errors[f"{query}:{section}"] = detail

    merged: dict[str, Any] = {
        "url": "resume-search",
        "sections": (
            {"search_results": "\n---\n".join(sections)} if sections else {}
        ),
        "job_ids": job_ids,
        "references": {"search_results": references},
        "search_queries": [
            str(spec.get("query", "")) for spec in query_specs
        ],
    }
    if promoted:
        merged["promoted_job_ids"] = promoted
    if errors:
        merged["section_errors"] = errors
    return merged


def _clean_lines(text: str) -> list[str]:
    cleaned: list[str] = []
    for raw in text.splitlines():
        line = raw.strip().lstrip("•-–—* ").strip()
        if line:
            cleaned.append(re.sub(r"\s+", " ", line))
    return cleaned


def parse_resume_document(text: str) -> dict[str, str]:
    """Turn a text or extracted PDF resume into searchable named sections."""
    lines = _clean_lines(text)
    if not lines:
        return {}
    sections: dict[str, str] = {}
    heading_indices: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        section = _RESUME_HEADINGS.get(line.casefold().rstrip(":"))
        if section:
            heading_indices.append((index, section))

    for position, (start, section) in enumerate(heading_indices):
        end = (
            heading_indices[position + 1][0]
            if position + 1 < len(heading_indices)
            else len(lines)
        )
        body_lines = lines[start + 1 : end]
        if section == "skills":
            merged_lines: list[str] = []
            for line in body_lines:
                if line.startswith("(") and merged_lines:
                    merged_lines[-1] = f"{merged_lines[-1]} {line}"
                else:
                    merged_lines.append(line)
            body_lines = merged_lines
        body = "\n".join(body_lines).strip()
        if body:
            sections.setdefault(section, body)

    contact_lines: list[str] = []
    first_heading = heading_indices[0][0] if heading_indices else len(lines)
    for line in lines[:first_heading]:
        folded = line.casefold()
        if "@" in line or "linkedin.com/" in folded or line.isdigit():
            contact_lines.append(line)
    if contact_lines:
        sections["contact"] = "\n".join(contact_lines)

    location_index: int | None = None
    location_pattern = re.compile(
        r"^[^@,]{2,50},\s*[^,]{2,50}(?:,\s*[^,]{2,50})?$"
    )
    for index, line in enumerate(lines[:40]):
        if (
            location_pattern.fullmatch(line)
            and "@" not in line
            and "http" not in line.casefold()
        ):
            location_index = index
            break

    if location_index is not None:
        sections["location"] = lines[location_index]
        if location_index >= 2:
            name_candidate = lines[location_index - 2]
            headline_candidate = lines[location_index - 1]
            if (
                2 <= len(name_candidate) <= 80
                and "@" not in name_candidate
                and name_candidate.casefold() not in _RESUME_HEADINGS
            ):
                sections["profile_name"] = name_candidate
            if 2 <= len(headline_candidate) <= 140:
                sections["headline"] = headline_candidate
    if "profile_name" not in sections:
        for line in lines[: min(12, len(lines))]:
            folded = line.casefold()
            if (
                2 <= len(line) <= 80
                and "@" not in line
                and "linkedin.com/" not in folded
                and folded not in _RESUME_HEADINGS
                and folded != "contact"
            ):
                sections["profile_name"] = line
                break
    return sections


def _profile_skill_lines(profile: dict[str, Any]) -> list[str]:
    sections = profile.get("sections")
    if not isinstance(sections, dict):
        return []
    skills_text = sections.get("skills")
    if not isinstance(skills_text, str):
        return []

    out: list[str] = []
    seen: set[str] = set()
    raw_lines = _clean_lines(skills_text)
    normalized_lines: list[str] = []
    for line in raw_lines:
        if line.startswith("(") and normalized_lines:
            normalized_lines[-1] = f"{normalized_lines[-1]} {line}"
        else:
            normalized_lines.append(line)
    for line in normalized_lines:
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


def _full_description(job_text: str, limit: int = 30_000) -> str:
    """Return the cleaned captured posting, bounded only to avoid pathological pages."""
    text = "\n".join(_clean_lines(job_text))
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "..."


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


_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "mär": 3,
    "märz": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "mai": 5,
    "jun": 6,
    "june": 6,
    "juni": 6,
    "jul": 7,
    "july": 7,
    "juli": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "okt": 10,
    "oktober": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
    "dez": 12,
    "dezember": 12,
}
_MONTH_PATTERN = (
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|März?|Apr(?:il)?|May|Mai|"
    r"Jun(?:e)?|Juni?|Jul(?:y)?|Juli|Aug(?:ust)?|Sep(?:t(?:ember)?)?|"
    r"Oct(?:ober)?|Okt(?:ober)?|Nov(?:ember)?|Dec(?:ember)?|Dez(?:ember)?"
)
_EXPERIENCE_RANGE_RE = re.compile(
    rf"(?:(?P<start_month>{_MONTH_PATTERN})\.?\s+)?"
    r"(?P<start_year>(?:19|20)\d{2})\s*"
    r"(?:-|–|—|to|bis)\s*"
    rf"(?:(?:(?P<end_month>{_MONTH_PATTERN})\.?\s+)?"
    r"(?P<end_year>(?:19|20)\d{2})|"
    r"(?P<current>present|current|now|heute|aktuell))",
    re.IGNORECASE,
)


def _month_number(value: str | None) -> int | None:
    if not value:
        return None
    return _MONTHS.get(value.rstrip(".").casefold())


def _profile_experience_years(experience_text: str) -> float | None:
    """Approximate non-overlapping experience from date ranges in the profile."""
    if not experience_text:
        return None
    today = datetime.now().astimezone().date()
    intervals: list[tuple[int, int]] = []
    for match in _EXPERIENCE_RANGE_RE.finditer(experience_text):
        start_year = int(match.group("start_year"))
        start_month = _month_number(match.group("start_month")) or 1
        if match.group("current"):
            end_year, end_month = today.year, today.month
        else:
            end_year = int(match.group("end_year"))
            end_month = _month_number(match.group("end_month")) or 12
        start = start_year * 12 + start_month - 1
        end = end_year * 12 + end_month
        if end > start:
            intervals.append((start, end))
    if not intervals:
        return None

    intervals.sort()
    merged: list[list[int]] = []
    for start, end in intervals:
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    months = sum(end - start for start, end in merged)
    return round(months / 12, 1) if months else None


def _priority_for_gap(count: int, total_jobs: int) -> str:
    if count >= max(2, (total_jobs + 1) // 2):
        return "high"
    if count >= 2:
        return "medium"
    return "low"


_SKILL_BRIDGES: dict[str, tuple[str, ...]] = {
    "Airflow": ("Python", "SQL", "Spark"),
    "AWS": ("Linux", "Docker", "Terraform", "Python"),
    "Azure": ("Linux", "Docker", "Terraform", "Python"),
    "BigQuery": ("SQL", "Data Analysis", "Python"),
    "Computer Vision": ("Python", "Machine Learning", "PyTorch", "TensorFlow"),
    "Databricks": ("Spark", "Python", "SQL", "Data Analysis"),
    "dbt": ("SQL", "Data Analysis", "Snowflake", "BigQuery"),
    "Django": ("Python", "SQL", "Docker"),
    "Docker": ("Linux", "CI/CD", "Bash"),
    "FastAPI": ("Python", "SQL", "Docker"),
    "Figma": ("UX", "UI Design", "Prototyping", "Wireframing"),
    "Flask": ("Python", "SQL", "Docker"),
    "GCP": ("Linux", "Docker", "Terraform", "Python"),
    "Java": ("Spring", "SQL", "Kafka"),
    "JavaScript": ("HTML", "CSS", "TypeScript"),
    "Kafka": ("Python", "Java", "SQL"),
    "Kubernetes": ("Docker", "Linux", "CI/CD"),
    "LangChain": ("Python", "LLM", "Machine Learning"),
    "LLM": ("Python", "Machine Learning", "Natural Language Processing"),
    "Machine Learning": ("Python", "Pandas", "NumPy", "scikit-learn"),
    "MLOps": ("Machine Learning", "Docker", "Kubernetes", "CI/CD"),
    "MongoDB": ("SQL", "Python", "Data Analysis"),
    "MySQL": ("SQL", "Data Analysis"),
    "Natural Language Processing": ("Python", "Machine Learning", "LLM"),
    "Next.js": ("React", "JavaScript", "TypeScript"),
    "Node.js": ("JavaScript", "TypeScript"),
    "NumPy": ("Python", "Pandas", "Data Analysis"),
    "Pandas": ("Python", "NumPy", "Data Analysis"),
    "PostgreSQL": ("SQL", "Data Analysis"),
    "Power BI": ("Data Analysis", "SQL", "Excel"),
    "Product Management": (
        "Business Analysis",
        "Data Analysis",
        "Project Management",
        "Stakeholder Management",
    ),
    "Project Management": (
        "Agile",
        "Scrum",
        "Jira",
        "Stakeholder Management",
    ),
    "PyTorch": ("Python", "Machine Learning", "NumPy"),
    "React": ("JavaScript", "TypeScript", "HTML", "CSS"),
    "Redis": ("SQL", "Python", "Docker"),
    "Salesforce": ("CRM", "Data Analysis"),
    "scikit-learn": ("Python", "Pandas", "NumPy", "Machine Learning"),
    "Snowflake": ("SQL", "Data Analysis", "dbt"),
    "Spark": ("Python", "SQL", "Data Analysis"),
    "Spring": ("Java", "SQL", "Docker"),
    "SQL": ("Data Analysis", "Python", "Excel"),
    "Stakeholder Management": ("Project Management", "Business Analysis"),
    "Tableau": ("Data Analysis", "SQL", "Excel"),
    "TensorFlow": ("Python", "Machine Learning", "NumPy"),
    "Terraform": ("AWS", "Azure", "GCP", "CI/CD"),
    "TypeScript": ("JavaScript", "React", "Node.js"),
    "UI Design": ("UX", "Figma", "Prototyping", "Wireframing"),
    "UX": ("UI Design", "Figma", "Prototyping", "Wireframing"),
    "Vue": ("JavaScript", "TypeScript", "HTML", "CSS"),
}


def _profile_name(profile: dict[str, Any]) -> str | None:
    sections = profile.get("sections")
    if not isinstance(sections, dict):
        return None
    if explicit := sections.get("profile_name"):
        return str(explicit)
    main = str(sections.get("main_profile") or sections.get("profile_document") or "")
    blocked = {
        "about",
        "contact info",
        "experience",
        "followers",
        "following",
        "message",
        "open to",
        "profile",
        "show all",
        "skills",
    }
    role_words = {
        "analyst",
        "architect",
        "consultant",
        "developer",
        "engineer",
        "manager",
        "professional",
        "scientist",
        "specialist",
        "student",
    }
    for line in _clean_lines(main)[:6]:
        folded = line.casefold()
        if any(marker in folded for marker in blocked):
            continue
        if role_words & set(re.findall(r"[a-z]+", folded)):
            continue
        if len(line) < 2 or len(line) > 80 or "·" in line:
            continue
        return line
    return None


def _profile_recent_role(profile: dict[str, Any]) -> str | None:
    sections = profile.get("sections")
    if not isinstance(sections, dict):
        return None
    if headline := sections.get("headline"):
        return str(headline)
    experience = str(sections.get("experience") or "")
    blocked = {
        "experience",
        "show all",
        "show less",
    }
    for line in _clean_lines(experience)[:12]:
        folded = line.casefold()
        if folded in blocked:
            continue
        range_match = _EXPERIENCE_RANGE_RE.search(line)
        if range_match:
            line = line[: range_match.start()].strip(" -|·")
            if len(line) < 3:
                continue
        if re.fullmatch(r"(?:19|20)\d{2}.*", line):
            continue
        if len(line) < 3 or len(line) > 120:
            continue
        return line
    return None


def _personal_bridge_skills(
    skill: str,
    profile_skills: set[str],
    fallback_skills: list[str],
) -> list[str]:
    preferred = _SKILL_BRIDGES.get(skill, ())
    bridges = [candidate for candidate in preferred if candidate in profile_skills]
    if not bridges:
        bridges = [
            candidate
            for candidate in fallback_skills
            if candidate != skill
        ]
    return bridges[:2]


def _skill_improvement_steps(
    skill: str,
    *,
    bridge_skills: list[str],
    recent_role: str | None,
) -> tuple[dict[str, list[str]], dict[str, str], dict[str, str]]:
    bridge_text = ", ".join(bridge_skills)
    role_text = recent_role or "your current role"
    if bridge_skills:
        context = {
            "en": (
                f"Use your existing {bridge_text} evidence as the bridge into {skill}."
            ),
            "zh": f"以你已有的 {bridge_text} 经验为基础，逐步衔接 {skill}。",
            "de": (
                f"Nutze deine vorhandenen Nachweise zu {bridge_text} als Brücke zu {skill}."
            ),
        }
        project = {
            "en": (
                f"Use your {bridge_text} work as a starting point, then extend "
                f"it so it also demonstrates {skill}, with a result relevant "
                f"to {role_text}."
            ),
            "zh": (
                f"扩展一个 {bridge_text} 项目，使其同时体现 {skill}，"
                f"并与你在{role_text}中的实际工作相关。"
            ),
            "de": (
                f"Erweitere ein Projekt mit {bridge_text}, sodass es zusätzlich "
                f"{skill} zeigt und für deine Rolle als {role_text} relevant ist."
            ),
        }
    else:
        context = {
            "en": f"Start with the fundamentals of {skill} and connect them to {role_text}.",
            "zh": f"先学习 {skill} 的基础，并把它与你当前“{role_text}”相关工作联系起来。",
            "de": (
                f"Beginne mit den Grundlagen von {skill} und verbinde sie mit "
                f"deiner Rolle als {role_text}."
            ),
        }
        project = {
            "en": (
                f"Build a small end-to-end project for {role_text} that produces "
                f"one visible outcome using {skill}."
            ),
            "zh": (
                f"围绕你当前的“{role_text}”工作完成一个端到端小项目，"
                f"使用 {skill} 产出一个可展示的结果。"
            ),
            "de": (
                f"Baue ein kleines End-to-End-Projekt für deine Rolle als "
                f"{role_text}, das mit {skill} ein sichtbares Ergebnis liefert."
            ),
        }
    return {
        "en": [
            (
                f"Verify that {skill} is genuinely missing. {context['en']} "
                "Review the official documentation and one structured guide."
            ),
            (
                f"{project['en']} Publish the code, architecture notes and a "
                "short README with measurable outcomes."
            ),
            (
                f"Add {skill} to your resume or LinkedIn profile only after you "
                "can support it with this project and its result."
            ),
            (
                f"Prepare a two-minute interview story explaining how you moved "
                f"from {bridge_text or role_text} to solving a real problem with {skill}."
            ),
        ],
        "zh": [
            (
                f"先确认 {skill} 是否确实缺失。{context['zh']}"
                "阅读官方文档和一份系统教程。"
            ),
            f"{project['zh']}公开代码、架构说明和带可量化结果的简短 README。",
            f"只有在项目与结果能够支撑时，才把 {skill} 写入简历或 LinkedIn 档案。",
            (
                f"准备一段两分钟面试表达，说明你如何从 {bridge_text or role_text} "
                f"延伸到使用 {skill} 解决实际问题。"
            ),
        ],
        "de": [
            (
                f"Prüfe, ob {skill} wirklich fehlt. {context['de']} "
                "Arbeite die offizielle Dokumentation und einen strukturierten Leitfaden durch."
            ),
            (
                f"{project['de']} Veröffentliche Code, Architekturhinweise und "
                "eine kurze README mit messbaren Ergebnissen."
            ),
            (
                f"Nimm {skill} erst dann in Lebenslauf oder LinkedIn-Profil auf, "
                "wenn Projekt und Ergebnis den Nachweis tragen."
            ),
            (
                f"Bereite eine zweiminütige Interviewgeschichte vor, wie du von "
                f"{bridge_text or role_text} zu einer echten Lösung mit {skill} gekommen bist."
            ),
        ],
    }, context, project


def _experience_improvement_steps(
    required: int,
    current: float | None,
    recent_role: str | None,
) -> dict[str, list[str]]:
    current_text = f"{current:g}" if current is not None else "unknown"
    role_text = recent_role or "your current role"
    return {
        "en": [
            (
                f"Compare the posting's {required}+ years with your captured "
                f"{current_text} years in {role_text}, and list the duties "
                "that lack evidence."
            ),
            (
                "Turn existing work into measurable case studies: scope, "
                "decisions, technical challenge, result and business impact."
            ),
            (
                "Create one or two end-to-end projects that exercise the "
                "missing responsibilities rather than only completing tutorials."
            ),
            (
                "Seek a stretch assignment, freelance task, open-source "
                "contribution or volunteer project that produces verifiable experience."
            ),
            (
                "Apply to adjacent or slightly less senior variants while the "
                "experience gap narrows; never overstate years or responsibilities."
            ),
        ],
        "zh": [
            (
                f"对比职位要求的 {required}+ 年经验与你档案中的 {current_text} 年，"
                f"结合“{role_text}”工作列出缺少证据的职责。"
            ),
            "把已有工作整理成可量化案例：范围、关键决策、技术难点、结果和业务影响。",
            "完成一到两个端到端项目，重点覆盖缺失的职责，而不是只做教程练习。",
            "争取延伸任务、自由职业项目、开源贡献或志愿项目，形成可验证的经验。",
            "在经验差距缩小前，投递相邻职位或资历要求略低的岗位；不要夸大年限或职责。",
        ],
        "de": [
            (
                f"Vergleiche die geforderten {required}+ Jahre mit den erfassten "
                f"{current_text} Jahren in {role_text} und notiere Aufgaben ohne Nachweis."
            ),
            (
                "Forme vorhandene Arbeit in messbare Fallstudien um: Umfang, "
                "Entscheidungen, technische Herausforderung, Ergebnis und Geschäftswirkung."
            ),
            (
                "Erstelle ein oder zwei End-to-End-Projekte, die die fehlenden "
                "Aufgaben abdecken, statt nur Tutorials abzuschließen."
            ),
            (
                "Suche eine anspruchsvollere Aufgabe, einen Freelance-Auftrag, "
                "Open-Source-Beitrag oder ein Ehrenamt mit nachweisbarer Erfahrung."
            ),
            (
                "Bewirb dich auf angrenzende oder etwas weniger seniorige Rollen, "
                "während die Lücke schrumpft; übertreibe Jahre oder Aufgaben nicht."
            ),
        ],
    }


def _rating(score: int) -> tuple[str, str]:
    if score >= 70:
        return "strong_match", "Strong match"
    if score >= 55:
        return "good_match", "Good match"
    if score >= 40:
        return "possible_match", "Worth reviewing"
    return "stretch", "Stretch"


def _fit_summary_i18n(
    matched: int,
    total: int,
    missing: int,
) -> dict[str, str]:
    return {
        "en": (
            f"Matched {matched} of {total} detected skills. "
            f"Review {missing} gap{'s' if missing != 1 else ''} before applying."
        ),
        "zh": (
            f"已匹配检测到的 {total} 项技能中的 {matched} 项。"
            f"申请前请核对 {missing} 项差距。"
        ),
        "de": (
            f"{matched} von {total} erkannten Kompetenzen stimmen überein. "
            f"Vor der Bewerbung {missing} Lücke"
            f"{'n' if missing != 1 else ''} prüfen."
        ),
    }


def _analyze_one_job(
    *,
    query: str,
    entry: dict[str, str],
    details: dict[str, Any],
    profile_skills: set[str],
    profile_skill_lines: list[str],
    profile_level: int | None,
    profile_level_name: str,
    profile_years: float | None,
) -> dict[str, Any]:
    section = details.get("sections", {}).get("job_posting", "")
    job_text = str(section or "")
    job_skills, expanded_profile_skills = _job_terms(job_text, profile_skill_lines)
    known_profile = profile_skills | expanded_profile_skills
    matched = sorted(job_skills & known_profile, key=str.casefold)
    missing = sorted(job_skills - known_profile, key=str.casefold)

    comparison_query = entry.get("search_query", query)
    query_tokens = _significant_tokens(str(comparison_query))
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
    years_required = _years_required(job_text)
    experience_gap_years = (
        round(max(0.0, years_required - profile_years), 1)
        if years_required is not None and profile_years is not None
        else None
    )

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
        "years_required": years_required,
        "experience_gap_years": experience_gap_years,
        "responsibilities": _section_items(
            job_text, _RESPONSIBILITY_HEADINGS, limit=20
        ),
        "requirements": _section_items(
            job_text, _REQUIREMENT_HEADINGS, limit=20
        ),
        "benefits": _section_items(
            job_text, _BENEFIT_HEADINGS, limit=20
        ),
        "description_excerpt": _description_excerpt(job_text),
        "full_description": _full_description(job_text),
        "fit_summary_i18n": _fit_summary_i18n(
            len(matched),
            len(job_skills),
            len(missing),
        ),
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
    profile_years = _profile_experience_years(profile_level_text)
    profile_name = _profile_name(profile)
    recent_role = _profile_recent_role(profile)

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
                profile_years=profile_years,
            )
        )
    jobs.sort(key=lambda item: (-item["fit_score"], item["title"].casefold()))

    strength_counts = Counter(
        skill for job in jobs for skill in job["matched_skills"]
    )
    gap_counts = Counter(skill for job in jobs for skill in job["missing_skills"])
    rating_counts = Counter(job["fit_rating_key"] for job in jobs)
    fallback_skills = [
        skill for skill, _ in strength_counts.most_common(6)
    ]
    all_gap_plans: list[dict[str, Any]] = []
    for skill, count in gap_counts.most_common():
        bridge_skills = _personal_bridge_skills(
            skill,
            profile_skills,
            fallback_skills,
        )
        steps_i18n, context_i18n, project_i18n = _skill_improvement_steps(
            skill,
            bridge_skills=bridge_skills,
            recent_role=recent_role,
        )
        all_gap_plans.append(
            {
                "skill": skill,
                "jobs": count,
                "priority": _priority_for_gap(count, len(jobs)),
                "bridge_skills": bridge_skills,
                "personal_context_i18n": context_i18n,
                "project_idea_i18n": project_i18n,
                "steps_i18n": steps_i18n,
            }
        )
    improvement_roadmap = all_gap_plans[:8]
    plan_by_skill = {item["skill"]: item for item in all_gap_plans}
    experience_gap_jobs = 0
    for job in jobs:
        job["improvement_plan"] = [
            plan_by_skill[skill]
            for skill in job["missing_skills"]
            if skill in plan_by_skill
        ][:10]
        gap = job.get("experience_gap_years")
        if gap:
            experience_gap_jobs += 1
            job["experience_gap_plan"] = {
                "required_years": job["years_required"],
                "profile_years": profile_years,
                "gap_years": gap,
                "steps_i18n": _experience_improvement_steps(
                    job["years_required"],
                    profile_years,
                    recent_role,
                ),
            }
        else:
            job["experience_gap_plan"] = None
        job["readiness"] = (
            "ready"
            if not job["missing_skills"] and not gap
            else "near_ready"
            if job["fit_score"] >= 55
            else "needs_development"
        )
    return {
        "query": query,
        "profile_url": profile.get("url"),
        "profile_name": profile_name,
        "recent_role": recent_role,
        "profile_sections_read": sorted(sections) if isinstance(sections, dict) else [],
        "profile_skills_detected": sorted(profile_skills, key=str.casefold),
        "profile_level": profile_level_name,
        "profile_years_experience": profile_years,
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
            {
                "skill": item["skill"],
                "jobs": item["jobs"],
                "priority": item["priority"],
            }
            for item in improvement_roadmap
        ],
        "improvement_roadmap": improvement_roadmap,
        "experience_gap_jobs": experience_gap_jobs,
        "search_mode": search_result.get("search_mode", "query"),
        "search_queries": search_result.get("search_queries", [query]),
        "company_filters": search_result.get("company_filters", []),
        "location_filter": search_result.get("location_filter"),
        "fallback_search": search_result.get("fallback_search"),
        "resume_search_signals": search_result.get(
            "resume_search_signals", {}
        ),
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
        (
            "Search mode: resume-based skills (no exact job-title filter)"
            if report.get("search_mode") == "resume"
            else "Search mode: requested keywords"
        ),
        f'Queries used: {", ".join(report.get("search_queries", []))}',
        (
            "Company filter: "
            + ", ".join(
                f'{item["input"]} (ID {item["company_id"]})'
                for item in report.get("company_filters", [])
            )
            if report.get("company_filters")
            else "Company filter: none"
        ),
        (
            "Location radius: "
            f'{report["location_filter"]["location"]} '
            f'({report["location_filter"]["radius_km"]} km)'
            if report.get("location_filter")
            and report["location_filter"].get("radius_km") is not None
            else "Location radius: not set"
        ),
        (
            "Fallback search: "
            + (
                "used; location, recency and other optional filters were relaxed"
                if (report.get("fallback_search") or {}).get("used")
                else "not needed"
            )
        ),
        (
            f'Profile: {report["profile_name"]} '
            f'({report.get("profile_url") or "supplied profile document"})'
            if report.get("profile_name")
            else f'Profile: {report.get("profile_url") or "supplied profile document"}'
        ),
        f'Current/recent role: {report.get("recent_role") or "not identified"}',
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
    roadmap = report.get("improvement_roadmap", [])
    if roadmap:
        lines.append(
            "Top improvement priorities: "
            + ", ".join(
                f'{item["skill"]} ({item["priority"]})'
                for item in roadmap[:6]
            )
        )
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
        if job.get("experience_gap_plan"):
            plan = job["experience_gap_plan"]
            lines.append(
                f'Experience gap: about {plan["gap_years"]:g} years '
                f'({plan["profile_years"]:g} captured vs '
                f'{plan["required_years"]}+ requested).'
            )
            lines.append("Experience improvement steps:")
            lines.extend(
                f"{index}. {step}"
                for index, step in enumerate(plan["steps_i18n"]["en"], start=1)
            )
        if job.get("improvement_plan"):
            lines.append("Skill improvement steps:")
            for plan in job["improvement_plan"][:4]:
                lines.append(f'- {plan["skill"]} ({plan["priority"]} priority)')
                if plan.get("personal_context_i18n"):
                    lines.append(
                        f'  Personal bridge: {plan["personal_context_i18n"]["en"]}'
                    )
                if plan.get("project_idea_i18n"):
                    lines.append(
                        f'  Project idea: {plan["project_idea_i18n"]["en"]}'
                    )
                lines.extend(
                    f"  {index}. {step}"
                    for index, step in enumerate(
                        plan["steps_i18n"]["en"], start=1
                    )
                )
        if job["requirements"]:
            lines.append("Key requirements:")
            lines.extend(f"- {item}" for item in job["requirements"])
        if job["responsibilities"]:
            lines.append("Main responsibilities:")
            lines.extend(f"- {item}" for item in job["responsibilities"])
        if job.get("benefits"):
            lines.append("Benefits and offerings:")
            lines.extend(f"- {item}" for item in job["benefits"])
        if job["description_excerpt"]:
            lines.append(f'Posting snapshot: {job["description_excerpt"]}')
        if job.get("error"):
            lines.append(f'Posting warning: {job["error"]}')
    return "\n".join(lines)


_REPORT_TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        "app.kicker": "LinkedIn job comparison",
        "app.title_template": "Fit report for “{query}”",
        "app.skip": "Skip to report",
        "app.generated": "Generated",
        "app.prepared_for": "Prepared for",
        "app.current_role": "Current or most recent role",
        "app.this_profile": "This profile",
        "app.search_mode": "Search mode",
        "app.resume_mode": "Resume-based skills, no exact title filter",
        "app.keyword_mode": "Requested keywords",
        "app.queries_used": "Queries used",
        "app.company_filter": "Company filter",
        "app.location_radius": "Location radius",
        "app.not_set": "Not set",
        "app.none": "None",
        "app.fallback_search": "Fallback search",
        "app.fallback_used": (
            "Used; location, recency and other optional filters were relaxed"
        ),
        "app.fallback_not_needed": "Not needed",
        "app.profile": "Profile",
        "app.jobs_analysed": "jobs analysed",
        "language.label": "Report language",
        "overview.title": "Overview",
        "overview.strong": "Strong matches",
        "overview.good": "Good matches",
        "overview.review": "Worth reviewing",
        "overview.stretch": "Stretch roles",
        "overview.methodology_title": "How this score works",
        "overview.methodology": (
            "The score compares skill evidence, role/title overlap and "
            "observed seniority signals. It is not a hiring probability."
        ),
        "overview.strengths": "Repeated strengths",
        "overview.gaps": "Repeated gaps",
        "overview.no_strengths": "No repeated skill matches",
        "overview.no_gaps": "No repeated skill gaps",
        "improvement.title": "Improvement roadmap",
        "improvement.subtitle": (
            "Focus on the gaps that unlock the most jobs. Each path moves from "
            "learning to evidence you can demonstrate."
        ),
        "improvement.skill_focus": "Appears in {count} analysed jobs",
        "improvement.experience_title": "Experience gap plan",
        "improvement.experience_summary": (
            "{current} years captured vs {required}+ requested; "
            "approximately {gap} years to close."
        ),
        "improvement.for_role": "How to improve for this role",
        "improvement.personal_bridge": "Your personal bridge",
        "improvement.project_idea": "Recommended project",
        "improvement.profile_years": "Profile experience",
        "improvement.required_years": "Posting requirement",
        "improvement.no_gaps": "No missing skills detected in this analysis.",
        "priority.high": "High priority",
        "priority.medium": "Medium priority",
        "priority.low": "Low priority",
        "readiness.ready": "Evidence complete",
        "readiness.near_ready": "Close with targeted evidence",
        "readiness.needs_development": "Development path recommended",
        "comparison.title": "Job comparison",
        "comparison.caption": "Ranked from strongest to weakest evidence match.",
        "table.job": "Job",
        "table.company": "Company",
        "table.location": "Location",
        "table.score": "Score",
        "table.assessment": "Assessment",
        "table.matched": "Matched evidence",
        "score.of": "/100",
        "details.title": "Detailed comparison",
        "details.assessment": "Detailed assessment",
        "details.open": "Open LinkedIn posting",
        "details.confidence": "confidence",
        "details.score_aria": "Fit score {score} out of 100",
        "details.matched": "Matched profile evidence",
        "details.missing": "Skills not found in profile",
        "details.none": "None detected.",
        "details.role_signals": "Role signals",
        "details.work_mode": "Work mode",
        "details.employment": "Employment type",
        "details.posting_seniority": "Posting seniority",
        "details.profile_seniority": "Profile seniority",
        "details.years_requested": "Years requested",
        "details.requirements": "Key requirements",
        "details.requirements_empty": "Requirements were not isolated from this posting.",
        "details.responsibilities": "Main responsibilities",
        "details.responsibilities_empty": (
            "Responsibilities were not isolated from this posting."
        ),
        "details.benefits": "Benefits and offerings",
        "details.benefits_empty": "Benefits were not isolated from this posting.",
        "details.snapshot": "Posting snapshot",
        "details.full_description": "Full job description",
        "details.no_description": "No description snapshot was captured.",
        "details.warning": "Posting warning",
        "details.view_full": "View full LinkedIn posting",
        "details.no_postings": "No job postings were returned.",
        "common.not_captured": "Not captured",
        "common.not_specified": "Not specified",
        "common.no_direct_matches": "No direct matches",
        "common.jobs_count": "{count} jobs",
        "methodology.title": "How to read this report",
        "methodology.body": (
            "A high score means more of the captured posting language overlaps "
            "the profile evidence and the role/title signals align. A missing "
            "skill means it was not found in the captured profile sections; it "
            "does not prove the skill is absent from your experience."
        ),
        "footer.disclaimer": (
            "Generated locally by LinkedIn Jobs MCP Server. LinkedIn is a "
            "trademark of LinkedIn Corporation. This independent report is not "
            "affiliated with LinkedIn."
        ),
        "footer.language_note": (
            "Interface and analytical labels are translated. Job descriptions "
            "and requirements remain in the language provided by LinkedIn."
        ),
        "rating.strong_match": "Strong match",
        "rating.good_match": "Good match",
        "rating.possible_match": "Worth reviewing",
        "rating.stretch": "Stretch",
        "confidence.high": "high",
        "confidence.medium": "medium",
        "confidence.low": "low",
        "work.hybrid": "Hybrid",
        "work.remote": "Remote",
        "work.on_site": "On-site",
        "work.unspecified": "Not clear",
        "employment.full_time": "Full-time",
        "employment.part_time": "Part-time",
        "employment.contract": "Contract",
        "employment.temporary": "Temporary",
        "employment.internship": "Internship",
        "employment.unspecified": "Not clear",
        "level.unspecified": "Not specified",
        "level.internship": "Internship",
        "level.entry": "Entry level",
        "level.junior": "Junior",
        "level.mid": "Mid-level",
        "level.senior": "Senior",
        "level.staff": "Staff",
        "level.lead": "Lead",
        "level.principal": "Principal",
        "level.manager": "Manager",
        "level.director": "Director",
        "level.head": "Head",
        "level.executive": "Executive",
        "level.vice president": "Vice President",
        "level.vp": "VP",
    },
    "zh": {
        "app.kicker": "LinkedIn 职位对比",
        "app.title_template": "“{query}”职位匹配报告",
        "app.skip": "跳到报告",
        "app.generated": "生成时间",
        "app.prepared_for": "报告对象",
        "app.current_role": "当前或最近职位",
        "app.this_profile": "此档案",
        "app.search_mode": "搜索模式",
        "app.resume_mode": "基于简历技能，不限定精确职位名称",
        "app.keyword_mode": "指定关键词",
        "app.queries_used": "使用的搜索词",
        "app.company_filter": "公司筛选",
        "app.location_radius": "地点半径",
        "app.not_set": "未设置",
        "app.none": "无",
        "app.fallback_search": "备用搜索",
        "app.fallback_used": "已启用；已放宽地点、发布时间和其他可选筛选条件",
        "app.fallback_not_needed": "未启用",
        "app.profile": "档案",
        "app.jobs_analysed": "个职位已分析",
        "language.label": "报告语言",
        "overview.title": "概览",
        "overview.strong": "高度匹配",
        "overview.good": "匹配良好",
        "overview.review": "值得进一步查看",
        "overview.stretch": "挑战职位",
        "overview.methodology_title": "评分依据",
        "overview.methodology": (
            "评分综合比较技能证据、职位/标题重合度以及识别到的资历信号。"
            "该分数不是录用概率。"
        ),
        "overview.strengths": "重复出现的优势",
        "overview.gaps": "重复出现的差距",
        "overview.no_strengths": "没有重复匹配的技能",
        "overview.no_gaps": "没有重复出现的技能差距",
        "improvement.title": "提升路线图",
        "improvement.subtitle": "优先补齐能解锁最多职位的差距。每条路径都从学习开始，最终形成可展示的证据。",
        "improvement.skill_focus": "出现在 {count} 个已分析职位中",
        "improvement.experience_title": "经验差距计划",
        "improvement.experience_summary": (
            "档案约 {current} 年，职位要求 {required}+ 年；"
            "还需补足约 {gap} 年。"
        ),
        "improvement.for_role": "如何为该职位提升",
        "improvement.personal_bridge": "适合你的衔接路径",
        "improvement.project_idea": "推荐实践项目",
        "improvement.profile_years": "档案经验",
        "improvement.required_years": "职位要求",
        "improvement.no_gaps": "本次分析未检测到缺失技能。",
        "priority.high": "高优先级",
        "priority.medium": "中优先级",
        "priority.low": "低优先级",
        "readiness.ready": "证据完整",
        "readiness.near_ready": "补充针对性证据即可",
        "readiness.needs_development": "建议制定提升计划",
        "comparison.title": "职位对比",
        "comparison.caption": "按证据匹配度从高到低排序。",
        "table.job": "职位",
        "table.company": "公司",
        "table.location": "地点",
        "table.score": "评分",
        "table.assessment": "评估",
        "table.matched": "匹配证据",
        "score.of": "/100",
        "details.title": "详细对比",
        "details.assessment": "详细评估",
        "details.open": "打开 LinkedIn 职位",
        "details.confidence": "置信度",
        "details.score_aria": "匹配评分 {score} 分，满分 100 分",
        "details.matched": "已匹配的档案证据",
        "details.missing": "档案中未发现的技能",
        "details.none": "未检测到。",
        "details.role_signals": "职位信号",
        "details.work_mode": "工作模式",
        "details.employment": "雇佣类型",
        "details.posting_seniority": "职位资历",
        "details.profile_seniority": "档案资历",
        "details.years_requested": "经验年限要求",
        "details.requirements": "主要要求",
        "details.requirements_empty": "未能从该职位中单独提取要求。",
        "details.responsibilities": "主要职责",
        "details.responsibilities_empty": "未能从该职位中单独提取职责。",
        "details.benefits": "福利与待遇",
        "details.benefits_empty": "未能从该职位中单独提取福利信息。",
        "details.snapshot": "职位摘要",
        "details.full_description": "完整职位描述",
        "details.no_description": "未捕获职位描述摘要。",
        "details.warning": "职位警告",
        "details.view_full": "查看完整 LinkedIn 职位",
        "details.no_postings": "没有返回职位。",
        "common.not_captured": "未捕获",
        "common.not_specified": "未注明",
        "common.no_direct_matches": "没有直接匹配",
        "common.jobs_count": "{count} 个职位",
        "methodology.title": "如何阅读此报告",
        "methodology.body": (
            "高分表示职位描述中的更多语言与档案证据重合，并且职位/标题信号一致。"
            "“档案中未发现”只表示在本次读取的档案内容中没有找到，并不证明你完全没有该技能。"
        ),
        "footer.disclaimer": (
            "本报告由 LinkedIn Jobs MCP Server 在本地生成。LinkedIn 是 "
            "LinkedIn Corporation 的商标。本独立报告与 LinkedIn 无隶属关系。"
        ),
        "footer.language_note": (
            "界面和分析标签已翻译。职位描述与要求保留 LinkedIn 提供的原始语言。"
        ),
        "rating.strong_match": "高度匹配",
        "rating.good_match": "匹配良好",
        "rating.possible_match": "值得查看",
        "rating.stretch": "挑战",
        "confidence.high": "高",
        "confidence.medium": "中",
        "confidence.low": "低",
        "work.hybrid": "混合办公",
        "work.remote": "远程",
        "work.on_site": "现场办公",
        "work.unspecified": "不明确",
        "employment.full_time": "全职",
        "employment.part_time": "兼职",
        "employment.contract": "合同制",
        "employment.temporary": "临时",
        "employment.internship": "实习",
        "employment.unspecified": "不明确",
        "level.unspecified": "未注明",
        "level.internship": "实习",
        "level.entry": "入门级",
        "level.junior": "初级",
        "level.mid": "中级",
        "level.senior": "高级",
        "level.staff": "资深专家",
        "level.lead": "负责人",
        "level.principal": "首席专家",
        "level.manager": "经理",
        "level.director": "总监",
        "level.head": "部门负责人",
        "level.executive": "高管",
        "level.vice president": "副总裁",
        "level.vp": "副总裁",
    },
    "de": {
        "app.kicker": "LinkedIn-Stellenvergleich",
        "app.title_template": "Passungsbericht für „{query}“",
        "app.skip": "Zum Bericht springen",
        "app.generated": "Erstellt",
        "app.prepared_for": "Erstellt für",
        "app.current_role": "Aktuelle oder letzte Rolle",
        "app.this_profile": "Dieses Profil",
        "app.search_mode": "Suchmodus",
        "app.resume_mode": "Kompetenzen aus dem Lebenslauf, kein exakter Titelfilter",
        "app.keyword_mode": "Angegebene Suchbegriffe",
        "app.queries_used": "Verwendete Suchanfragen",
        "app.company_filter": "Unternehmensfilter",
        "app.location_radius": "Standortradius",
        "app.not_set": "Nicht festgelegt",
        "app.none": "Keine",
        "app.fallback_search": "Ersatzsuche",
        "app.fallback_used": (
            "Verwendet; Ort, Aktualität und weitere optionale Filter wurden gelockert"
        ),
        "app.fallback_not_needed": "Nicht erforderlich",
        "app.profile": "Profil",
        "app.jobs_analysed": "Stellen analysiert",
        "language.label": "Berichtssprache",
        "overview.title": "Überblick",
        "overview.strong": "Starke Treffer",
        "overview.good": "Gute Treffer",
        "overview.review": "Prüfenswert",
        "overview.stretch": "Ambitionierte Rollen",
        "overview.methodology_title": "So funktioniert die Bewertung",
        "overview.methodology": (
            "Die Bewertung vergleicht Kompetenznachweise, Überschneidungen bei "
            "Rolle und Titel sowie erkannte Senioritätssignale. Sie ist keine "
            "Einstellungswahrscheinlichkeit."
        ),
        "overview.strengths": "Wiederkehrende Stärken",
        "overview.gaps": "Wiederkehrende Lücken",
        "overview.no_strengths": "Keine wiederkehrenden Kompetenztreffer",
        "overview.no_gaps": "Keine wiederkehrenden Kompetenzlücken",
        "improvement.title": "Entwicklungsplan",
        "improvement.subtitle": (
            "Konzentriere dich auf die Lücken, die die meisten Stellen öffnen. "
            "Jeder Pfad führt vom Lernen zu nachweisbarer Evidenz."
        ),
        "improvement.skill_focus": "Kommt in {count} analysierten Stellen vor",
        "improvement.experience_title": "Plan für die Erfahrungslücke",
        "improvement.experience_summary": (
            "{current} Jahre erfasst gegenüber {required}+ gefordert; "
            "etwa {gap} Jahre Lücke."
        ),
        "improvement.for_role": "So verbesserst du dich für diese Stelle",
        "improvement.personal_bridge": "Deine persönliche Brücke",
        "improvement.project_idea": "Empfohlenes Projekt",
        "improvement.profile_years": "Erfahrung im Profil",
        "improvement.required_years": "Anforderung der Stelle",
        "improvement.no_gaps": "In dieser Analyse wurden keine fehlenden Kompetenzen erkannt.",
        "priority.high": "Hohe Priorität",
        "priority.medium": "Mittlere Priorität",
        "priority.low": "Niedrige Priorität",
        "readiness.ready": "Nachweise vollständig",
        "readiness.near_ready": "Mit gezielten Nachweisen schließbar",
        "readiness.needs_development": "Entwicklungsplan empfohlen",
        "comparison.title": "Stellenvergleich",
        "comparison.caption": (
            "Sortiert von der stärksten zur schwächsten Evidenzübereinstimmung."
        ),
        "table.job": "Stelle",
        "table.company": "Unternehmen",
        "table.location": "Ort",
        "table.score": "Bewertung",
        "table.assessment": "Einschätzung",
        "table.matched": "Übereinstimmende Evidenz",
        "score.of": "/100",
        "details.title": "Detailvergleich",
        "details.assessment": "Detailbewertung",
        "details.open": "LinkedIn-Stelle öffnen",
        "details.confidence": "Sicherheit",
        "details.score_aria": "Passungsbewertung {score} von 100",
        "details.matched": "Übereinstimmende Profilnachweise",
        "details.missing": "Nicht im Profil gefundene Kompetenzen",
        "details.none": "Keine erkannt.",
        "details.role_signals": "Rollensignale",
        "details.work_mode": "Arbeitsmodell",
        "details.employment": "Beschäftigungsart",
        "details.posting_seniority": "Seniorität der Stelle",
        "details.profile_seniority": "Seniorität im Profil",
        "details.years_requested": "Geforderte Berufserfahrung",
        "details.requirements": "Wichtige Anforderungen",
        "details.requirements_empty": (
            "Anforderungen konnten aus dieser Stelle nicht separat extrahiert werden."
        ),
        "details.responsibilities": "Hauptaufgaben",
        "details.responsibilities_empty": (
            "Aufgaben konnten aus dieser Stelle nicht separat extrahiert werden."
        ),
        "details.benefits": "Leistungen und Angebote",
        "details.benefits_empty": (
            "Leistungen konnten aus dieser Stelle nicht separat extrahiert werden."
        ),
        "details.snapshot": "Stellenauszug",
        "details.full_description": "Vollständige Stellenbeschreibung",
        "details.no_description": "Kein Beschreibungsauszug erfasst.",
        "details.warning": "Hinweis zur Stelle",
        "details.view_full": "Vollständige LinkedIn-Stelle anzeigen",
        "details.no_postings": "Es wurden keine Stellen zurückgegeben.",
        "common.not_captured": "Nicht erfasst",
        "common.not_specified": "Nicht angegeben",
        "common.no_direct_matches": "Keine direkten Treffer",
        "common.jobs_count": "{count} Stellen",
        "methodology.title": "So liest du den Bericht",
        "methodology.body": (
            "Eine hohe Bewertung bedeutet, dass mehr Sprache aus der "
            "Stellenanzeige mit Profilnachweisen übereinstimmt und die "
            "Rollen-/Titelsignale passen. „Nicht im Profil gefunden“ bedeutet "
            "nur, dass die Kompetenz in den gelesenen Profilabschnitten nicht "
            "vorkam; sie kann dennoch vorhanden sein."
        ),
        "footer.disclaimer": (
            "Lokal erstellt mit LinkedIn Jobs MCP Server. LinkedIn ist eine "
            "Marke der LinkedIn Corporation. Dieser unabhängige Bericht steht "
            "in keiner Verbindung zu LinkedIn."
        ),
        "footer.language_note": (
            "Oberfläche und Analysebezeichnungen sind übersetzt. "
            "Stellenbeschreibungen und Anforderungen bleiben in der von "
            "LinkedIn gelieferten Sprache."
        ),
        "rating.strong_match": "Starker Treffer",
        "rating.good_match": "Guter Treffer",
        "rating.possible_match": "Prüfenswert",
        "rating.stretch": "Ambitioniert",
        "confidence.high": "hoch",
        "confidence.medium": "mittel",
        "confidence.low": "niedrig",
        "work.hybrid": "Hybrid",
        "work.remote": "Remote",
        "work.on_site": "Vor Ort",
        "work.unspecified": "Nicht eindeutig",
        "employment.full_time": "Vollzeit",
        "employment.part_time": "Teilzeit",
        "employment.contract": "Vertrag",
        "employment.temporary": "Befristet",
        "employment.internship": "Praktikum",
        "employment.unspecified": "Nicht eindeutig",
        "level.unspecified": "Nicht angegeben",
        "level.internship": "Praktikum",
        "level.entry": "Einstieg",
        "level.junior": "Junior",
        "level.mid": "Mittlere Ebene",
        "level.senior": "Senior",
        "level.staff": "Staff",
        "level.lead": "Lead",
        "level.principal": "Principal",
        "level.manager": "Management",
        "level.director": "Direktion",
        "level.head": "Bereichsleitung",
        "level.executive": "Geschäftsleitung",
        "level.vice president": "Vice President",
        "level.vp": "VP",
    },
}


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
.language-switcher {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 20px 0 0;
}
.language-switcher button {
  min-height: 44px;
  padding: 8px 14px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
  color: var(--foreground);
  cursor: pointer;
  font: 600 0.9rem/1.2 "Fira Sans", "Avenir Next", "Segoe UI", sans-serif;
}
.language-switcher button:hover {
  border-color: var(--primary);
  color: var(--primary);
  transition: border-color 180ms ease-out, color 180ms ease-out;
}
.language-switcher button[aria-pressed="true"] {
  border-color: var(--primary);
  background: var(--primary);
  color: var(--surface);
}
.fit-summary {
  margin: 12px 0 0;
  padding: 12px 14px;
  border-radius: 12px;
  background: var(--surface-raised);
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
.roadmap-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}
.roadmap-card {
  padding: 22px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
}
.roadmap-card.full { grid-column: 1 / -1; }
.roadmap-card h3 {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.roadmap-card ol,
.improvement-details ol {
  margin: 12px 0 0;
  padding-left: 1.3rem;
}
.roadmap-card li + li,
.improvement-details li + li { margin-top: 9px; }
.priority {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 3px 9px;
  border-radius: 999px;
  font: 600 0.74rem/1.2 "Fira Code", ui-monospace, monospace;
}
.priority.high { color: var(--stretch); background: var(--stretch-soft); }
.priority.medium { color: var(--review); background: var(--review-soft); }
.priority.low { color: var(--good); background: var(--good-soft); }
.improvement-details {
  margin-top: 14px;
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: var(--surface-raised);
}
.improvement-details summary {
  min-height: 32px;
  cursor: pointer;
  color: var(--primary);
  font-weight: 600;
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
.full-description {
  margin-top: 16px;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: var(--surface);
}
.full-description summary {
  min-height: 48px;
  padding: 13px 16px;
  cursor: pointer;
  color: var(--primary);
  font-weight: 600;
}
.full-description > div {
  max-height: 36rem;
  overflow: auto;
  padding: 0 16px 16px;
  white-space: pre-line;
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
html:lang(zh-CN) body,
html:lang(zh-CN) .language-switcher button {
  font-family: "PingFang SC", "Noto Sans SC", "Microsoft YaHei", sans-serif;
}
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
  .signals, .roadmap-grid, .job-body { grid-template-columns: 1fr; }
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


def _i18n_text(key: str) -> str:
    return _REPORT_TRANSLATIONS["en"].get(key, key)


def _i18n_span(key: str) -> str:
    return (
        f'<span data-i18n="{_e(key)}">'
        f"{_e(_i18n_text(key))}</span>"
    )


def _translated_value(prefix: str, value: str) -> str:
    key = f"{prefix}.{value}"
    return (
        f'<span data-i18n="{_e(key)}">'
        f"{_e(_i18n_text(key) if key in _REPORT_TRANSLATIONS['en'] else value)}"
        "</span>"
    )


def _value_or_i18n(value: Any, key: str) -> str:
    return _e(value) if value else _i18n_span(key)


def _chip_list(items: list[str], *, missing: bool = False) -> str:
    if not items:
        return f'<p class="snapshot">{_i18n_span("details.none")}</p>'
    css = "chip missing" if missing else "chip"
    return '<div class="chips">' + "".join(
        f'<span class="{css}">{_e(item)}</span>' for item in items
    ) + "</div>"


def _list_html(items: list[str], empty_key: str) -> str:
    if not items:
        return f'<p class="snapshot">{_i18n_span(empty_key)}</p>'
    return "<ul>" + "".join(f"<li>{_e(item)}</li>" for item in items) + "</ul>"


def _steps_html(steps_i18n: dict[str, list[str]]) -> str:
    english = steps_i18n.get("en", [])
    chinese = steps_i18n.get("zh", [])
    german = steps_i18n.get("de", [])
    items: list[str] = []
    for index, english_step in enumerate(english):
        chinese_step = chinese[index] if index < len(chinese) else english_step
        german_step = german[index] if index < len(german) else english_step
        items.append(
            f'<li data-text-en="{_e(english_step)}" '
            f'data-text-zh="{_e(chinese_step)}" '
            f'data-text-de="{_e(german_step)}">'
            f"{_e(english_step)}</li>"
        )
    return "<ol>" + "".join(items) + "</ol>"


def _multilingual_paragraph(
    text_i18n: dict[str, str],
    *,
    css: str = "",
) -> str:
    english = text_i18n.get("en", "")
    chinese = text_i18n.get("zh", english)
    german = text_i18n.get("de", english)
    return (
        f'<p class="{_e(css)}" '
        f'data-text-en="{_e(english)}" '
        f'data-text-zh="{_e(chinese)}" '
        f'data-text-de="{_e(german)}">'
        f"{_e(english)}</p>"
    )


def render_fit_report_html(
    report: dict[str, Any],
    *,
    generated_at: str | None = None,
    initial_language: str = "en",
) -> str:
    """Render a standalone, responsive comparison report."""
    generated_at = generated_at or datetime.now().astimezone().strftime(
        "%Y-%m-%d %H:%M %Z"
    )
    counts = report["rating_counts"]
    query = _e(report.get("query"))
    profile_url = _safe_href(report.get("profile_url"))
    profile_label = _e(report.get("profile_url") or "Supplied profile document")
    profile_name = _value_or_i18n(report.get("profile_name"), "app.this_profile")
    recent_role = report.get("recent_role")
    search_mode_key = (
        "app.resume_mode"
        if report.get("search_mode") == "resume"
        else "app.keyword_mode"
    )
    queries_used = " · ".join(report.get("search_queries", []))
    company_filter_values = " · ".join(
            f'{item["input"]} (ID {item["company_id"]})'
            for item in report.get("company_filters", [])
        )
    company_filter_html = (
        _e(company_filter_values)
        if company_filter_values
        else _i18n_span("app.none")
    )
    location_filter = report.get("location_filter") or {}
    location_radius_html = (
        _e(
            f'{location_filter["location"]} '
            f'({location_filter["radius_km"]} km)'
        )
        if location_filter.get("radius_km") is not None
        else _i18n_span("app.not_set")
    )
    fallback_key = (
        "app.fallback_used"
        if (report.get("fallback_search") or {}).get("used")
        else "app.fallback_not_needed"
    )

    summary_rows = "".join(
        f"""
        <tr>
          <td data-label="{_e(_i18n_text('table.job'))}" data-i18n-label="table.job">
            <a href="#job-{_e(job['job_id'])}">{_e(job['title'])}</a>
          </td>
          <td data-label="{_e(_i18n_text('table.company'))}" data-i18n-label="table.company">
            {_value_or_i18n(job.get('company'), 'common.not_captured')}
          </td>
          <td data-label="{_e(_i18n_text('table.location'))}" data-i18n-label="table.location">
            {_value_or_i18n(job.get('location'), 'common.not_specified')}
          </td>
          <td data-label="{_e(_i18n_text('table.score'))}" data-i18n-label="table.score">
            <span class="score">{_e(job['fit_score'])}<small>{_i18n_span('score.of')}</small></span>
          </td>
          <td data-label="{_e(_i18n_text('table.assessment'))}" data-i18n-label="table.assessment">
            <span class="badge {_e(job['fit_rating_key'])}" data-i18n="rating.{_e(job['fit_rating_key'])}">{_e(job['fit_rating'])}</span>
          </td>
          <td data-label="{_e(_i18n_text('table.matched'))}" data-i18n-label="table.matched">
            {_e(', '.join(job['matched_skills'][:5])) if job['matched_skills'] else _i18n_span('common.no_direct_matches')}
          </td>
        </tr>
        """
        for job in report["jobs"]
    )

    job_cards: list[str] = []
    for index, job in enumerate(report["jobs"], start=1):
        details = [
            (
                f"{_i18n_span('details.work_mode')}: "
                f"{_translated_value('work', job.get('work_mode', 'unspecified'))}"
            ),
            (
                f"{_i18n_span('details.employment')}: "
                f"{_translated_value('employment', job.get('employment_type', 'unspecified'))}"
            ),
            (
                f"{_i18n_span('details.posting_seniority')}: "
                f"{_translated_value('level', job.get('job_level', 'unspecified'))}"
            ),
            (
                f"{_i18n_span('details.profile_seniority')}: "
                f"{_translated_value('level', job.get('profile_level', 'unspecified'))}"
            ),
        ]
        if job.get("years_required") is not None:
            details.append(
                f"{_i18n_span('details.years_requested')}: "
                f"{_e(job['years_required'])}+"
            )
        summary_i18n = job.get("fit_summary_i18n", {})
        summary = (
            f'<p class="fit-summary" '
            f'data-summary-en="{_e(summary_i18n.get("en", ""))}" '
            f'data-summary-zh="{_e(summary_i18n.get("zh", ""))}" '
            f'data-summary-de="{_e(summary_i18n.get("de", ""))}">'
            f'{_e(summary_i18n.get("en", ""))}</p>'
        )
        warning = (
            f'<p class="warning"><strong data-i18n="details.warning">'
            f'{_e(_i18n_text("details.warning"))}:</strong> '
            f'{_e(job["error"])}</p>'
            if job.get("error")
            else ""
        )
        snapshot = (
            f'<p class="snapshot">{_e(job["description_excerpt"])}</p>'
            if job.get("description_excerpt")
            else f'<p class="snapshot">{_i18n_span("details.no_description")}</p>'
        )
        full_description = job.get("full_description") or ""
        full_description_html = (
            f"""
            <details class="full-description">
              <summary data-i18n="details.full_description">
                {_e(_i18n_text("details.full_description"))}
              </summary>
              <div>{_e(full_description)}</div>
            </details>
            """
            if full_description
            else ""
        )
        improvement_parts: list[str] = []
        experience_plan = job.get("experience_gap_plan")
        if experience_plan:
            summary_by_language = {
                language: _REPORT_TRANSLATIONS[language][
                    "improvement.experience_summary"
                ].format(
                    current=f'{experience_plan["profile_years"]:g}',
                    required=experience_plan["required_years"],
                    gap=f'{experience_plan["gap_years"]:g}',
                )
                for language in ("en", "zh", "de")
            }
            improvement_parts.append(
                f"""
                <h4 data-i18n="improvement.experience_title">
                  {_e(_i18n_text("improvement.experience_title"))}
                </h4>
                <p class="snapshot"
                   data-text-en="{_e(summary_by_language["en"])}"
                   data-text-zh="{_e(summary_by_language["zh"])}"
                   data-text-de="{_e(summary_by_language["de"])}">
                  {_e(summary_by_language["en"])}
                </p>
                {_steps_html(experience_plan["steps_i18n"])}
                """
            )
        for plan in job.get("improvement_plan", []):
            improvement_parts.append(
                f"""
                <h4>
                  {_e(plan["skill"])}
                  <span class="priority {_e(plan["priority"])}" data-i18n="priority.{_e(plan["priority"])}">
                    {_e(_i18n_text(f"priority.{plan['priority']}"))}
                  </span>
                </h4>
                <div class="snapshot">
                  <strong data-i18n="improvement.personal_bridge">
                    {_e(_i18n_text("improvement.personal_bridge"))}:
                  </strong>
                  {_multilingual_paragraph(plan.get("personal_context_i18n", {}))}
                </div>
                <div class="snapshot">
                  <strong data-i18n="improvement.project_idea">
                    {_e(_i18n_text("improvement.project_idea"))}:
                  </strong>
                  {_multilingual_paragraph(plan.get("project_idea_i18n", {}))}
                </div>
                {_steps_html(plan["steps_i18n"])}
                """
            )
        improvement_html = (
            f"""
            <details class="improvement-details">
              <summary data-i18n="improvement.for_role">
                {_e(_i18n_text("improvement.for_role"))}
              </summary>
              {''.join(improvement_parts)}
            </details>
            """
            if improvement_parts
            else f'<p class="snapshot">{_i18n_span("improvement.no_gaps")}</p>'
        )
        readiness_class = (
            "strong_match"
            if job["readiness"] == "ready"
            else "possible_match"
            if job["readiness"] == "near_ready"
            else "stretch"
        )
        job_cards.append(
            f"""
            <article class="job-card" id="job-{_e(job['job_id'])}">
              <header class="job-head">
                <div>
                  <p class="eyebrow">
                    <span data-i18n="details.assessment">
                      {_e(_i18n_text("details.assessment"))}
                    </span>
                    {_e(index)}
                  </p>
                  <h3>{_e(job['title'])}</h3>
                  <div class="job-meta">
                    <span>{_value_or_i18n(job.get('company'), 'common.not_captured')}</span>
                    <span>{_value_or_i18n(job.get('location'), 'common.not_specified')}</span>
                    <a href="{_safe_href(job['url'])}" data-i18n="details.open">
                      {_e(_i18n_text("details.open"))}
                    </a>
                  </div>
                </div>
                <div>
                  <span class="badge {_e(job['fit_rating_key'])}" data-i18n="rating.{_e(job['fit_rating_key'])}">
                    {_e(job['fit_rating'])}
                  </span>
                  <div class="score">
                    {_e(job['fit_score'])}<small data-i18n="score.of">{_e(_i18n_text("score.of"))}</small>
                  </div>
                  <div
                    class="score-track"
                    role="img"
                    aria-label="{_e(_i18n_text('details.score_aria').format(score=job['fit_score']))}"
                    data-i18n-aria="details.score_aria"
                    data-score="{_e(job['fit_score'])}"
                  >
                    <div class="score-fill" style="--score:{_e(job['fit_score'])}%"></div>
                  </div>
                  <p class="job-meta">
                    <span data-i18n="confidence.{_e(job['confidence'])}">
                      {_e(_i18n_text(f"confidence.{job['confidence']}"))}
                    </span>
                    <span data-i18n="details.confidence">
                      {_e(_i18n_text("details.confidence"))}
                    </span>
                  </p>
                  <span class="badge {_e(readiness_class)}" data-i18n="readiness.{_e(job['readiness'])}">
                    {_e(_i18n_text(f"readiness.{job['readiness']}"))}
                  </span>
                </div>
              </header>
              <div class="job-body">
                <section>
                  <h4 data-i18n="details.matched">{_e(_i18n_text("details.matched"))}</h4>
                  {_chip_list(job['matched_skills'])}
                </section>
                <section>
                  <h4 data-i18n="details.missing">{_e(_i18n_text("details.missing"))}</h4>
                  {_chip_list(job['missing_skills'], missing=True)}
                </section>
                <section class="full">
                  <h4 data-i18n="details.role_signals">{_e(_i18n_text("details.role_signals"))}</h4>
                  {summary}
                  <div class="chips">
                    {''.join(f'<span class="chip">{item}</span>' for item in details)}
                  </div>
                </section>
                <section>
                  <h4 data-i18n="details.requirements">{_e(_i18n_text("details.requirements"))}</h4>
                  {_list_html(job['requirements'], 'details.requirements_empty')}
                </section>
                <section>
                  <h4 data-i18n="details.responsibilities">{_e(_i18n_text("details.responsibilities"))}</h4>
                  {_list_html(job['responsibilities'], 'details.responsibilities_empty')}
                </section>
                <section>
                  <h4 data-i18n="details.benefits">{_e(_i18n_text("details.benefits"))}</h4>
                  {_list_html(job.get('benefits', []), 'details.benefits_empty')}
                </section>
                <section class="full">
                  <h4 data-i18n="details.snapshot">{_e(_i18n_text("details.snapshot"))}</h4>
                  {snapshot}
                  {full_description_html}
                  {warning}
                  {improvement_html}
                  <p>
                    <a class="button" href="{_safe_href(job['url'])}" data-i18n="details.view_full">
                      {_e(_i18n_text("details.view_full"))}
                    </a>
                  </p>
                </section>
              </div>
            </article>
            """
        )

    strengths = "".join(
        f'<span class="chip">'
        f'{_e(item["skill"])} · '
        f'<span data-i18n-template="common.jobs_count" '
        f'data-count="{_e(item["jobs"])}">{_e(item["jobs"])} jobs</span>'
        f"</span>"
        for item in report.get("common_strengths", [])
    )
    gaps = "".join(
        f'<span class="chip missing">'
        f'{_e(item["skill"])} · '
        f'<span data-i18n-template="common.jobs_count" '
        f'data-count="{_e(item["jobs"])}">{_e(item["jobs"])} jobs</span>'
        f"</span>"
        for item in report.get("common_gaps", [])
    )
    roadmap_cards = "".join(
        f"""
        <article class="roadmap-card">
          <h3>
            <span>{_e(item["skill"])}</span>
            <span class="priority {_e(item["priority"])}" data-i18n="priority.{_e(item["priority"])}">
              {_e(_i18n_text(f"priority.{item['priority']}"))}
            </span>
          </h3>
          <p class="job-meta">
            <span data-i18n-template="common.jobs_count" data-count="{_e(item["jobs"])}">
              {_e(_i18n_text("common.jobs_count").format(count=item["jobs"]))}
            </span>
          </p>
          <h4 data-i18n="improvement.personal_bridge">
            {_e(_i18n_text("improvement.personal_bridge"))}
          </h4>
          {_multilingual_paragraph(item.get("personal_context_i18n", {}), css="snapshot")}
          <h4 data-i18n="improvement.project_idea">
            {_e(_i18n_text("improvement.project_idea"))}
          </h4>
          {_multilingual_paragraph(item.get("project_idea_i18n", {}), css="snapshot")}
          {_steps_html(item["steps_i18n"])}
        </article>
        """
        for item in report.get("improvement_roadmap", [])
    )
    experience_jobs = [
        job for job in report["jobs"] if job.get("experience_gap_plan")
    ]
    experience_block = ""
    if experience_jobs:
        experience_job = max(
            experience_jobs,
            key=lambda job: job["experience_gap_plan"]["gap_years"],
        )
        experience_plan = experience_job["experience_gap_plan"]
        experience_summary = {
            language: _REPORT_TRANSLATIONS[language][
                "improvement.experience_summary"
            ].format(
                current=f'{experience_plan["profile_years"]:g}',
                required=experience_plan["required_years"],
                gap=f'{experience_plan["gap_years"]:g}',
            )
            for language in ("en", "zh", "de")
        }
        experience_block = f"""
        <article class="roadmap-card full">
          <h3 data-i18n="improvement.experience_title">
            {_e(_i18n_text("improvement.experience_title"))}
          </h3>
          <p class="snapshot"
             data-text-en="{_e(experience_summary["en"])}"
             data-text-zh="{_e(experience_summary["zh"])}"
             data-text-de="{_e(experience_summary["de"])}">
            {_e(experience_summary["en"])}
          </p>
          {_steps_html(experience_plan["steps_i18n"])}
        </article>
        """
    roadmap_content = (
        f"{roadmap_cards}{experience_block}"
        if roadmap_cards or experience_block
        else f'<p class="panel">{_i18n_span("improvement.no_gaps")}</p>'
    )
    profile_link = (
        f'<a href="{profile_url}">{profile_label}</a>'
        if profile_url != "#"
        else profile_label
    )
    translations_json = json.dumps(
        _REPORT_TRANSLATIONS,
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")
    initial_language = (
        initial_language if initial_language in _REPORT_TRANSLATIONS else "en"
    )

    return f"""<!doctype html>
<html lang="{_e(initial_language)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light dark">
  <title data-i18n-title="{query}">{_e(_REPORT_TRANSLATIONS["en"]["app.title_template"].format(query=report.get("query", "")))}</title>
  <style>{_REPORT_CSS}</style>
</head>
<body>
  <a class="skip-link" href="#main" data-i18n="app.skip">{_e(_i18n_text("app.skip"))}</a>
  <main class="shell" id="main">
    <header class="hero">
      <p class="eyebrow" data-i18n="app.kicker">{_e(_i18n_text("app.kicker"))}</p>
      <h1 data-i18n-title="{query}">
        {_e(_REPORT_TRANSLATIONS["en"]["app.title_template"].format(query=report.get("query", "")))}
      </h1>
      <div class="language-switcher" role="group" aria-label="{_e(_i18n_text("language.label"))}" data-i18n-aria="language.label">
        <button type="button" data-language="en" lang="en" aria-pressed="true">English</button>
        <button type="button" data-language="zh" lang="zh-CN" aria-pressed="false">中文</button>
        <button type="button" data-language="de" lang="de" aria-pressed="false">Deutsch</button>
      </div>
      <div class="hero-meta">
        <span><span data-i18n="app.generated">{_e(_i18n_text("app.generated"))}</span> {_e(generated_at)}</span>
        <span><span data-i18n="app.search_mode">{_e(_i18n_text("app.search_mode"))}</span>: <span data-i18n="{search_mode_key}">{_e(_i18n_text(search_mode_key))}</span></span>
        <span><span data-i18n="app.prepared_for">{_e(_i18n_text("app.prepared_for"))}</span>: {profile_name}</span>
        {f'<span><span data-i18n="app.current_role">{_e(_i18n_text("app.current_role"))}</span>: {_e(recent_role)}</span>' if recent_role else ''}
        <span><span data-i18n="app.profile">{_e(_i18n_text("app.profile"))}</span>: {profile_link}</span>
        <span>{_e(report['jobs_analyzed'])} <span data-i18n="app.jobs_analysed">{_e(_i18n_text("app.jobs_analysed"))}</span></span>
      </div>
      <p class="job-meta"><span data-i18n="app.queries_used">{_e(_i18n_text("app.queries_used"))}</span>: {_e(queries_used)}</p>
      <p class="job-meta"><span data-i18n="app.company_filter">{_e(_i18n_text("app.company_filter"))}</span>: {company_filter_html}</p>
      <p class="job-meta"><span data-i18n="app.location_radius">{_e(_i18n_text("app.location_radius"))}</span>: {location_radius_html}</p>
      <p class="job-meta"><span data-i18n="app.fallback_search">{_e(_i18n_text("app.fallback_search"))}</span>: <span data-i18n="{fallback_key}">{_e(_i18n_text(fallback_key))}</span></p>
      <p><strong data-i18n="overview.methodology_title">{_e(_i18n_text("overview.methodology_title"))}.</strong>
        <span data-i18n="overview.methodology">{_e(_i18n_text("overview.methodology"))}</span></p>
    </header>

    <section class="section" aria-labelledby="overview-heading">
      <h2 id="overview-heading" data-i18n="overview.title">{_e(_i18n_text("overview.title"))}</h2>
      <div class="stats">
        <div class="stat"><strong>{_e(counts['strong_match'])}</strong><span data-i18n="overview.strong">{_e(_i18n_text("overview.strong"))}</span></div>
        <div class="stat"><strong>{_e(counts['good_match'])}</strong><span data-i18n="overview.good">{_e(_i18n_text("overview.good"))}</span></div>
        <div class="stat"><strong>{_e(counts['possible_match'])}</strong><span data-i18n="overview.review">{_e(_i18n_text("overview.review"))}</span></div>
        <div class="stat"><strong>{_e(counts['stretch'])}</strong><span data-i18n="overview.stretch">{_e(_i18n_text("overview.stretch"))}</span></div>
      </div>
      <div class="signals" style="margin-top:16px">
        <section class="panel">
          <h3 data-i18n="overview.strengths">{_e(_i18n_text("overview.strengths"))}</h3>
          <div class="chips">{strengths or f'<span class="chip">{_i18n_span("overview.no_strengths")}</span>'}</div>
        </section>
        <section class="panel">
          <h3 data-i18n="overview.gaps">{_e(_i18n_text("overview.gaps"))}</h3>
          <div class="chips">{gaps or f'<span class="chip">{_i18n_span("overview.no_gaps")}</span>'}</div>
        </section>
      </div>
    </section>

    <section class="section" aria-labelledby="improvement-heading">
      <h2 id="improvement-heading" data-i18n="improvement.title">
        {_e(_i18n_text("improvement.title"))}
      </h2>
      <p data-i18n="improvement.subtitle">{_e(_i18n_text("improvement.subtitle"))}</p>
      <div class="roadmap-grid">{roadmap_content}</div>
    </section>

    <section class="section" aria-labelledby="comparison-heading">
      <h2 id="comparison-heading" data-i18n="comparison.title">{_e(_i18n_text("comparison.title"))}</h2>
      <div class="table-wrap">
        <table>
          <caption data-i18n="comparison.caption">{_e(_i18n_text("comparison.caption"))}</caption>
          <thead>
            <tr>
              <th scope="col" data-i18n="table.job">{_e(_i18n_text("table.job"))}</th>
              <th scope="col" data-i18n="table.company">{_e(_i18n_text("table.company"))}</th>
              <th scope="col" data-i18n="table.location">{_e(_i18n_text("table.location"))}</th>
              <th scope="col" data-i18n="table.score">{_e(_i18n_text("table.score"))}</th>
              <th scope="col" data-i18n="table.assessment">{_e(_i18n_text("table.assessment"))}</th>
              <th scope="col" data-i18n="table.matched">{_e(_i18n_text("table.matched"))}</th>
            </tr>
          </thead>
          <tbody>{summary_rows}</tbody>
        </table>
      </div>
    </section>

    <section class="section" aria-labelledby="details-heading">
      <h2 id="details-heading" data-i18n="details.title">{_e(_i18n_text("details.title"))}</h2>
      <div class="job-list">{''.join(job_cards) or f'<p class="panel">{_i18n_span("details.no_postings")}</p>'}</div>
    </section>

    <aside class="methodology">
      <strong data-i18n="methodology.title">{_e(_i18n_text("methodology.title"))}.</strong>
      <span data-i18n="methodology.body">{_e(_i18n_text("methodology.body"))}</span>
      <p data-i18n="footer.language_note">{_e(_i18n_text("footer.language_note"))}</p>
    </aside>
    <footer>
      <span data-i18n="footer.disclaimer">{_e(_i18n_text("footer.disclaimer"))}</span>
    </footer>
  </main>
  <script>
    const translations = {translations_json};
    const reportQuery = {json.dumps(report.get("query", ""), ensure_ascii=False)};
    function translate(language) {{
      const dictionary = translations[language] || translations.en;
      document.documentElement.lang = language === "zh" ? "zh-CN" : language;
      document.querySelectorAll("[data-i18n]").forEach((element) => {{
        const value = dictionary[element.dataset.i18n];
        if (value) element.textContent = value;
      }});
      document.querySelectorAll("[data-i18n-template]").forEach((element) => {{
        const value = dictionary[element.dataset.i18nTemplate];
        if (value) element.textContent = value.replace("{{count}}", element.dataset.count || "");
      }});
      document.querySelectorAll("[data-i18n-label]").forEach((element) => {{
        const value = dictionary[element.dataset.i18nLabel];
        if (value) element.dataset.label = value;
      }});
      document.querySelectorAll("[data-i18n-aria]").forEach((element) => {{
        const value = dictionary[element.dataset.i18nAria];
        if (value) element.setAttribute(
          "aria-label",
          value.replace("{{score}}", element.dataset.score || "")
        );
      }});
      document.querySelectorAll("[data-summary-en]").forEach((element) => {{
        element.textContent = element.dataset[
          language === "zh" ? "summaryZh" : language === "de" ? "summaryDe" : "summaryEn"
        ] || element.dataset.summaryEn;
      }});
      document.querySelectorAll("[data-text-en]").forEach((element) => {{
        element.textContent = element.dataset[
          language === "zh" ? "textZh" : language === "de" ? "textDe" : "textEn"
        ] || element.dataset.textEn;
      }});
      const titleTemplate = dictionary["app.title_template"];
      const title = titleTemplate.replace("{{query}}", reportQuery);
      document.title = title;
      document.querySelectorAll("[data-i18n-title]").forEach((element) => {{
        element.textContent = title;
      }});
      document.querySelectorAll("[data-language]").forEach((button) => {{
        button.setAttribute("aria-pressed", String(button.dataset.language === language));
      }});
    }}
    document.querySelectorAll("[data-language]").forEach((button) => {{
      button.addEventListener("click", () => translate(button.dataset.language));
    }});
    translate({json.dumps(initial_language)});
  </script>
</body>
</html>
"""
