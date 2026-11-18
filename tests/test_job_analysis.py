"""Job-fit reports expose their evidence and keep their ranking explainable."""

from linkedin_mcp_server.job_analysis import (
    _profile_experience_years,
    analyze_job_fit,
    format_fit_report,
    generate_resume_search_queries,
    merge_job_search_results,
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
            "main_profile": "Alex Example\nData platform professional",
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
    assert report["profile_name"] == "Alex Example"
    assert report["recent_role"] == "Senior Data Engineer at Acme"
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
    assert first["improvement_plan"]
    assert first["improvement_plan"][0]["skill"] == "Kubernetes"
    assert len(first["improvement_plan"][0]["steps_i18n"]["en"]) == 4
    assert "existing" in first["improvement_plan"][0]["personal_context_i18n"]["en"]
    assert "Kubernetes" in first["improvement_plan"][0]["project_idea_i18n"]["en"]
    assert "Senior Data Engineer" in first["improvement_plan"][0]["project_idea_i18n"]["en"]
    assert report["improvement_roadmap"]


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
    assert "Improvement roadmap" in rendered
    assert "Verify that Kubernetes is genuinely missing" in rendered
    assert "Your personal bridge" in rendered
    assert "Recommended project" in rendered
    assert "Use your existing" in rendered
    assert "Alex Example" in rendered
    assert "data-text-zh=" in rendered
    assert "data-text-de=" in rendered
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


def test_experience_gap_generates_localized_improvement_steps():
    search = {
        "url": "https://www.linkedin.com/jobs/search/",
        "job_ids": ["404"],
        "references": {
            "search_results": [
                {
                    "kind": "job",
                    "url": "/jobs/view/404/",
                    "text": "Data Engineer",
                }
            ]
        },
    }
    profile = {
        "sections": {
            "experience": "Data Engineer\nJanuary 2019 - December 2021",
            "skills": "Python\nSQL",
        }
    }
    details = [
        {
            "sections": {
                "job_posting": """Data Engineer
Acme · Berlin
About the job
Build data pipelines.
Qualifications
- 5+ years of experience with Python and SQL.
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

    assert _profile_experience_years(profile["sections"]["experience"]) >= 2.9
    plan = report["jobs"][0]["experience_gap_plan"]
    assert plan is not None
    assert plan["required_years"] == 5
    assert plan["gap_years"] >= 2
    assert len(plan["steps_i18n"]["en"]) == 5
    assert len(plan["steps_i18n"]["zh"]) == 5
    assert len(plan["steps_i18n"]["de"]) == 5


def test_resume_search_uses_skills_without_requiring_a_job_title():
    resume = """Alex Example
Data and cloud professional
Experience
Python Python SQL Databricks Spark AWS
Built analytics pipelines and data products.
"""

    context = generate_resume_search_queries(resume, limit=3)
    queries = [item["query"] for item in context["queries"]]

    assert len(queries) == 3
    assert queries[0].startswith("Python")
    assert any("SQL" in query for query in queries)
    assert "Senior Data Engineer" not in queries
    assert {"Python", "SQL", "Databricks"} <= set(context["skills"])
    assert context["domains"]


def test_resume_search_results_are_merged_and_remember_their_query():
    first = {
        "job_ids": ["101", "202"],
        "references": {
            "search_results": [
                {
                    "kind": "job",
                    "url": "/jobs/view/101/",
                    "text": "Data Engineer",
                },
                {
                    "kind": "job",
                    "url": "/jobs/view/202/",
                    "text": "Analytics Engineer",
                },
            ]
        },
        "sections": {"search_results": "first results"},
    }
    second = {
        "job_ids": ["202", "303"],
        "references": {
            "search_results": [
                {
                    "kind": "job",
                    "url": "/jobs/view/202/",
                    "text": "Analytics Engineer",
                },
                {
                    "kind": "job",
                    "url": "/jobs/view/303/",
                    "text": "Cloud Data Engineer",
                },
            ]
        },
        "sections": {"search_results": "second results"},
        "promoted_job_ids": ["303"],
    }
    specs = [{"query": "Python SQL"}, {"query": "Databricks AWS"}]

    merged = merge_job_search_results([first, second], specs)

    assert merged["job_ids"] == ["101", "202", "303"]
    assert merged["search_queries"] == ["Python SQL", "Databricks AWS"]
    assert merged["promoted_job_ids"] == ["303"]
    references = {
        item["url"]: item["search_query"]
        for item in merged["references"]["search_results"]
    }
    assert references["/jobs/view/101/"] == "Python SQL"
    assert references["/jobs/view/202/"] == "Python SQL"
    assert references["/jobs/view/303/"] == "Databricks AWS"
