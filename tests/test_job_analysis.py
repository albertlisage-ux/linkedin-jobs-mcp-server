"""Job-fit reports expose their evidence and keep their ranking explainable."""

from linkedin_mcp_server.job_analysis import (
    analyze_job_fit,
    format_fit_report,
    render_fit_report_html,
)


def _search_result():
    return {
        "url": "https://www.linkedin.com/jobs/search/",
        "job_ids": ["101", "202"],
        "references": {
            "search_results": [
                {
                    "kind": "job",
                    "url": "/jobs/view/101/",
                    "text": "Senior Data Engineer",
                },
                {
                    "kind": "job",
                    "url": "/jobs/view/202/",
                    "text": "Product Manager",
                },
            ]
        },
    }


def _profile():
    return {
        "url": "https://www.linkedin.com/in/example/",
        "sections": {
            "main_profile": "Data platform professional",
            "experience": "Senior Data Engineer at Acme\n2021 - Present",
            "skills": "Python\nSQL\nAirflow\nAWS",
        },
    }


def _details():
    return [
        {
            "url": "https://www.linkedin.com/jobs/view/101/",
            "sections": {
                "job_posting": """Senior Data Engineer
Acme · Berlin · Hybrid
About the job
Build reliable pipelines with Python, SQL, Airflow and AWS.
Responsibilities
- Build and operate production data pipelines.
- Partner with analytics teams on data models.
Qualifications
- 5+ years of experience with Python and SQL.
- Experience deploying workloads on Kubernetes.
"""
            },
        },
        {
            "url": "https://www.linkedin.com/jobs/view/202/",
            "sections": {
                "job_posting": """Product Manager
Other Co · Munich · Full-time
About the job
Own a B2B analytics product.
Requirements
- Product management experience.
- Strong stakeholder management.
"""
            },
        },
    ]


def test_fit_report_ranks_by_observable_profile_evidence():
    report = analyze_job_fit(
        query="senior data engineer",
        search_result=_search_result(),
        profile=_profile(),
        job_details=_details(),
    )

    assert report["jobs_analyzed"] == 2
    first, second = report["jobs"]
    assert first["job_id"] == "101"
    assert first["fit_rating"] == "Strong match"
    assert first["fit_score"] > second["fit_score"]
    assert {"Python", "SQL", "Airflow", "AWS"} <= set(first["matched_skills"])
    assert "Kubernetes" in first["missing_skills"]
    assert first["company"] == "Acme"
    assert first["location"] == "Berlin"
    assert first["work_mode"] == "hybrid"
    assert first["job_level"] == "senior"
    assert first["profile_level"] == "senior"
    assert first["years_required"] == 5
    assert first["requirements"]
    assert first["responsibilities"]
    assert "Build reliable pipelines with Python" in first["full_description"]
    assert first["fit_summary_i18n"]["zh"]
    assert first["fit_summary_i18n"]["de"]


def test_overview_aggregates_strengths_and_gaps():
    report = analyze_job_fit(
        query="senior data engineer",
        search_result=_search_result(),
        profile=_profile(),
        job_details=_details(),
    )

    strengths = {item["skill"] for item in report["common_strengths"]}
    gaps = {item["skill"] for item in report["common_gaps"]}
    rendered = format_fit_report(report)

    assert {"Python", "SQL"} <= strengths
    assert "Kubernetes" in gaps
    assert "LINKEDIN JOB FIT OVERVIEW" in rendered
    assert "[Strong match] Senior Data Engineer" in rendered
    assert "Matched evidence: Airflow, AWS, Python, SQL" in rendered
    assert "Not found in profile: Kubernetes" in rendered
    assert "It is not a hiring probability" in rendered


def test_html_report_compares_overview_and_details_and_escapes_content():
    report = analyze_job_fit(
        query="data engineer",
        search_result=_search_result(),
        profile=_profile(),
        job_details=_details(),
    )
    report["jobs"][0]["title"] = "<script>alert('x')</script>"

    rendered = render_fit_report_html(
        report,
        generated_at="2026-11-16 12:00 CET",
        initial_language="zh",
    )

    assert "<!doctype html>" in rendered
    assert '<html lang="zh">' in rendered
    assert 'translate("zh");' in rendered
    assert "Job comparison" in rendered
    assert "Detailed assessment" in rendered
    assert "Matched profile evidence" in rendered
    assert "Skills not found in profile" in rendered
    assert 'data-language="zh"' in rendered
    assert 'data-language="de"' in rendered
    assert "中文" in rendered
    assert "Deutsch" in rendered
    assert "完整职位描述" in rendered
    assert "Vollständige Stellenbeschreibung" in rendered
    assert "Full job description" in rendered
    assert "&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt;" in rendered
    assert "<script>alert" not in rendered
    assert 'aria-label="Fit score 89 out of 100"' in rendered


def test_german_job_sections_are_extracted_with_details_and_benefits():
    search = {
        "url": "https://www.linkedin.com/jobs/search/",
        "job_ids": ["303"],
        "references": {
            "search_results": [
                {
                    "kind": "job",
                    "url": "/jobs/view/303/",
                    "text": "Senior Data Engineer",
                }
            ]
        },
    }
    profile = {
        "sections": {
            "experience": "Senior Data Engineer",
            "skills": "Python\nSQL\nDatenanalyse",
        }
    }
    details = [
        {
            "sections": {
                "job_posting": """Senior Data Engineer
Acme · Berlin · Hybrid
Über uns
Wir bauen eine Datenplattform.
Aufgaben
- Entwickle zuverlässige Datenpipelines mit Python und SQL.
- Verantworte Datenmodelle und Datenqualität.
Anforderungen
- Mehrjährige Erfahrung mit Python und SQL.
- Erfahrung mit Datenanalyse und Kubernetes.
Wir bieten
- Flexible Arbeitszeiten und Weiterbildung.
"""
            }
        }
    ]

    report = analyze_job_fit(
        query="data engineer",
        search_result=search,
        profile=profile,
        job_details=details,
    )
    job = report["jobs"][0]

    assert "Entwickle zuverlässige Datenpipelines" in job["responsibilities"][0]
    assert "Mehrjährige Erfahrung" in job["requirements"][0]
    assert job["benefits"] == ["Flexible Arbeitszeiten und Weiterbildung."]
    assert "Kubernetes" in job["missing_skills"]
