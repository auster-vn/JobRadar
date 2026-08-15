import pytest

from nlp.title_normalizer import NormalizedTitle, normalize_title


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Senior Backend Engineer", NormalizedTitle("Senior Backend Developer", "senior")),
        ("Jr. Front-end Dev", NormalizedTitle("Junior Frontend Developer", "junior")),
        ("Data Engineer", NormalizedTitle("Data Engineer", "mid")),
        ("Tech Lead DevOps", NormalizedTitle("DevOps Engineer", "lead")),
        ("Senior Business Analyst", NormalizedTitle("Senior Business Analyst", "senior")),
        ("Chuyên Viên Phân Tích Nghiệp Vụ", NormalizedTitle("Business Analyst", "mid")),
        ("Nhà phân tích kinh doanh cao cấp", NormalizedTitle("Senior Business Analyst", "senior")),
        ("Trưởng Nhóm Lập Trình Backend", NormalizedTitle("Backend Developer", "lead")),
        ("Nhà phát triển phụ trợ cao cấp", NormalizedTitle("Senior Backend Developer", "senior")),
        ("Senior Java Developer", NormalizedTitle("Senior Backend Developer", "senior")),
        ("Nhà phát triển phía trước", NormalizedTitle("Frontend Developer", "mid")),
        ("Nhà phát triển Stack đầy đủ", NormalizedTitle("Fullstack Developer", "mid")),
        ("Kỹ sư dữ liệu cao cấp", NormalizedTitle("Senior Data Engineer", "senior")),
        ("Nhân Viên Data Scientits", NormalizedTitle("Data Scientist", "mid")),
        ("Trưởng Nhóm Tester", NormalizedTitle("QA Engineer", "lead")),
        ("Nhà phát triển Android cao cấp", NormalizedTitle("Senior Mobile Developer", "senior")),
        ("Kỹ Sư An Ninh Mạng", NormalizedTitle("Security Engineer", "mid")),
        ("Lead Penetration Tester", NormalizedTitle("Security Engineer", "lead")),
        ("Network Security Engineer", NormalizedTitle("Security Engineer", "mid")),
        ("Security Admin", NormalizedTitle("Security Engineer", "mid")),
        ("Kỹ Sư Lập Trình Nhúng", NormalizedTitle("Embedded Engineer", "mid")),
        (
            "Senior Embedded Software Engineer",
            NormalizedTitle("Senior Embedded Engineer", "senior"),
        ),
        ("Kỹ Sư Mạng", NormalizedTitle("Network Engineer", "mid")),
        ("Kỹ Sư Hệ Thống", NormalizedTitle("System Engineer", "mid")),
        ("Nhân Viên IT Helpdesk", NormalizedTitle("IT Support", "mid")),
        ("Cloud Engineer (Azure)", NormalizedTitle("Cloud Engineer", "mid")),
        ("IT Project Manager", NormalizedTitle("Project Manager", "manager")),
        ("Chủ sở hữu sản phẩm Junior", NormalizedTitle("Junior Product Owner", "junior")),
        ("Kỹ sư phần mềm", NormalizedTitle("Software Engineer", "mid")),
        ("Principal Software Engineer", NormalizedTitle("Senior Software Engineer", "senior")),
        ("Leader Unity Developer", NormalizedTitle("Game Developer", "lead")),
        ("Giám Đốc Công Nghệ CTO", NormalizedTitle("Giám Đốc Công Nghệ CTO", "director")),
    ],
)
def test_normalize_title(raw: str, expected: NormalizedTitle) -> None:
    assert normalize_title(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "Nhân Viên Kinh Doanh Phần Mềm",
        "Nhân Viên Lập Trình Máy CNC",
        "Kỹ Sư An Ninh, An Toàn",
        "Phần mềm quản lý dự án",
    ],
)
def test_normalize_title_does_not_promote_adjacent_roles(raw: str) -> None:
    assert normalize_title(raw).title == raw
