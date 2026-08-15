from datetime import UTC, datetime

from scrapers.itviec.parser import enrich_from_detail, parse_listing

HTML = """
<div class="job-card" data-job-key="abc-123"
 data-search--job-selection-job-url-value="/it-jobs/senior-python-engineer-acme-123/content?locale=en">
 <span>Posted 2 hours ago</span>
 <h3 data-search--job-selection-target="jobTitle"
   data-url="https://itviec.com/it-jobs/senior-python-engineer-acme-123">Senior Python Engineer</h3>
 <a class="logo-employer-card" href="/companies/acme"><img data-src="https://img.test/acme.png"></a>
 <a href="/companies/acme">ACME Vietnam</a>
 <div class="salary">30 - 45 triệu</div>
 <div title="Ho Chi Minh - Ha Noi">Ho Chi Minh - Ha Noi</div>
 <a data-responsive-tag-list-target="tag">Python</a>
 <a data-responsive-tag-list-target="tag">FastAPI</a>
 <ul><li>Build reliable APIs for millions of users</li></ul>
</div>
"""


def test_parse_current_itviec_card_contract() -> None:
    now = datetime(2026, 7, 14, 12, tzinfo=UTC)
    jobs = parse_listing(HTML, now=now)
    assert len(jobs) == 1
    job = jobs[0]
    assert job.platform_job_id == "abc-123"
    assert job.title == "Senior Python Engineer"
    assert job.company_name == "ACME Vietnam"
    assert job.location == ["Ho Chi Minh", "Ha Noi"]
    assert job.skills == ["Python", "FastAPI"]
    assert job.posted_at == datetime(2026, 7, 14, 10, tzinfo=UTC)


def test_enrich_from_json_ld_detail() -> None:
    job = parse_listing(HTML)[0]
    detail = """
    <script type="application/ld+json">
    {"@type":"JobPosting","description":"<p>Build APIs</p><p>Own production</p>",
     "skills":"Python, PostgreSQL", "validThrough":"2026-08-14",
     "experienceRequirements":{"monthsOfExperience":37}}
    </script>
    """

    enriched = enrich_from_detail(job, detail)

    assert enriched.description == "Build APIs\nOwn production"
    assert enriched.skills == ["FastAPI", "PostgreSQL", "Python"]
    assert enriched.expires_at == datetime(2026, 8, 14, tzinfo=UTC)
    assert enriched.experience_years_min == 3
