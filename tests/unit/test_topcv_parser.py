from datetime import UTC, datetime

from scrapers.topcv.parser import listing_page_count, parse_listing

HTML = """
<div class="job-item-search-result" data-job-id="2224804">
  <div class="avatar"><img data-src="https://img.test/company.png"></div>
  <h3 class="title"><a href="https://www.topcv.vn/viec-lam/ml-engineer/2224804.html?tracking=1">
    <span>Machine Learning Engineer Fresher</span></a></h3>
  <span class="company-name">Example Technology</span>
  <label class="salary"><span>12.5 - 19.5 triệu</span></label>
  <label class="address"><span class="city-text">Đà Nẵng (mới)</span></label>
  <label class="exp"><span>Dưới 1 năm</span></label>
  <div class="box-icon"><label class="address">Đăng 1 tuần trước</label></div>
</div>
<span id="job-listing-paginate-text"><span>1</span> / 7 trang</span>
"""


def test_parse_current_topcv_card_contract() -> None:
    now = datetime(2026, 7, 16, 12, tzinfo=UTC)
    jobs = parse_listing(HTML, now=now)

    assert len(jobs) == 1
    job = jobs[0]
    assert job.platform == "topcv"
    assert job.platform_job_id == "2224804"
    assert str(job.source_url) == "https://www.topcv.vn/viec-lam/ml-engineer/2224804.html"
    assert job.title == "Machine Learning Engineer Fresher"
    assert job.company_name == "Example Technology"
    assert job.salary_text == "12.5 - 19.5 triệu"
    assert job.location == ["Đà Nẵng"]
    assert job.experience_years_min == 0
    assert job.experience_years_max == 1
    assert job.posted_at == datetime(2026, 7, 9, 12, tzinfo=UTC)


def test_parse_topcv_page_count() -> None:
    assert listing_page_count(HTML) == 7
    assert listing_page_count("<html></html>") == 1
