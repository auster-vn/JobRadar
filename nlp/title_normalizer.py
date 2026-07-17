import hashlib
import json
import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NormalizedTitle:
    title: str
    level: str | None


LEVEL_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\b(intern(?:ship)?|thực tập)\b", "intern"),
    (r"\b(fresher|graduate|mới tốt nghiệp)\b", "fresher"),
    (r"\b(jr\.?|junior|sơ cấp)\b", "junior"),
    (r"\b(sr\.?|senior|principal|staff|expert|cao cấp|chuyên gia)\b", "senior"),
    (
        r"\b(tech(?:nical)? lead|team lead|lead|leader|trưởng nhóm|lãnh đạo kỹ thuật)\b",
        "lead",
    ),
    (r"\b(manager|head of|quản lý|trưởng phòng|phó phòng)\b", "manager"),
    (
        r"\b(director|vp of|vice president|giám đốc|cto|cio|ciso|"
        r"chief (?:technology|information|security) officer)\b",
        "director",
    ),
)

ROLE_PATTERNS: tuple[tuple[str, str], ...] = (
    (
        r"\b(front[ -]?end|fe|nhà phát triển phía trước)\b|"
        r"\b(react(?:\.?js)?|angular) developer\b",
        "Frontend Developer",
    ),
    (
        r"\b(back[ -]?end|be|nhà phát triển phụ trợ|phát triển back[ -]?end)\b|"
        r"(?<!\w)(java|\.net|php|python|golang|node(?:\.js)?|odoo|wordpress|sql|server) "
        r"(developer|engineer)\b|"
        r"\b(lập trình viên|chuyên viên lập trình) "
        r"(java|\.net|php|python|golang|node(?:\.js)?|odoo)\b",
        "Backend Developer",
    ),
    (
        r"\bfull[ -]?stack\b|\bnhà phát triển (stack đầy đủ|đầy đủ)\b",
        "Fullstack Developer",
    ),
    (r"\b(devops|platform engineer)\b", "DevOps Engineer"),
    (r"\b(site reliability|sre)\b", "SRE"),
    (r"\b(data engineer|kỹ sư dữ liệu)\b", "Data Engineer"),
    (r"\b(data scient(?:ist|its)|nhà khoa học dữ liệu)\b", "Data Scientist"),
    (r"\bdata analyst\b|\bphân tích dữ liệu\b", "Data Analyst"),
    (
        r"\bbusiness analyst\b|\bphân tích nghiệp vụ\b|"
        r"\bnhà phân tích kinh doanh\b",
        "Business Analyst",
    ),
    (
        r"\b(machine learning|ml) engineer\b|\bkỹ sư (máy học|học máy)\b",
        "ML Engineer",
    ),
    (
        r"\b(ai|artificial intelligence) engineer\b|\bkỹ sư (ai|trí tuệ nhân tạo)\b",
        "AI Engineer",
    ),
    (r"\bflutter (developer|engineer)\b", "Mobile Developer (Flutter)"),
    (r"\breact[ .-]?native (developer|engineer)\b", "Mobile Developer (React Native)"),
    (
        r"\b(android|ios|mobile) (developer|engineer)\b|"
        r"\bnhà phát triển (android|ios)\b|\bkỹ sư di động\b|"
        r"\b(lập trình|lập trình viên) (mobile|android|ios)\b",
        "Mobile Developer",
    ),
    (
        r"\b(security|cybersecurity) engineer\b|\bcyber ?security\b|"
        r"\b(network security|security admin|penetration tester|pentester)\b|"
        r"\bkỹ sư (an ninh mạng|bảo mật)\b|\bmạng (&|và) bảo mật\b|"
        r"\bquản trị hệ thống bảo mật\b",
        "Security Engineer",
    ),
    (
        r"\b(qa|quality assurance|software tester|tester|test engineer|manual tester)\b|"
        r"\bkiểm thử( phần mềm)?\b",
        "QA Engineer",
    ),
    (r"\b(solution|software|cloud) architect\b", "Solution Architect"),
    (r"\bproduct manager\b", "Product Manager"),
    (r"\b(product owner|chủ sở hữu sản phẩm)\b", "Product Owner"),
    (r"\b(quản lý sản phẩm|giám đốc sản phẩm)\b", "Product Manager"),
    (r"\b(scrum master|agile coach)\b", "Scrum Master"),
    (
        r"\b(game developer|game programmer|unity developer)\b|"
        r"\b(phát triển game|phát triển trò chơi|nhà phát triển trò chơi|lập trình game)\b|"
        r"\bunreal engine\b",
        "Game Developer",
    ),
    (
        r"\bembedded(?: software| systems| linux)? (developer|engineer)\b|"
        r"\bfirmware (developer|engineer)\b|"
        r"\b(lập trình nhúng|phần mềm nhúng|kỹ sư nhúng)\b",
        "Embedded Engineer",
    ),
    (r"\b(database administrator|dba|quản trị cơ sở dữ liệu)\b", "Database Administrator"),
    (r"\b(network engineer|kỹ sư mạng|quản trị mạng)\b", "Network Engineer"),
    (
        r"\b(system engineer|system administrator|kỹ sư hệ thống|"
        r"quản trị(?: viên)? hệ thống)\b",
        "System Engineer",
    ),
    (r"\b(it helpdesk|it support|hỗ trợ cntt|hỗ trợ kỹ thuật helpdesk)\b", "IT Support"),
    (r"\b(cloud engineer|kỹ sư (điện toán )?đám mây)\b", "Cloud Engineer"),
    (
        r"\b(project manager|it project manager|trình quản lý dự án|quản trị dự án)\b|"
        r"^quản lý dự án\b|"
        r"\b(nhân viên|chuyên viên|kỹ sư|giám đốc) quản lý dự án\b",
        "Project Manager",
    ),
    (
        r"\b(software developer|software engineer|web developer|kỹ sư phần mềm|"
        r"phát triển phần mềm|lập trình web(?:site)?)\b|"
        r"^(developer|lập trình viên)\b",
        "Software Engineer",
    ),
)

TITLE_NORMALIZER_REVISION = hashlib.sha256(
    json.dumps(
        {"levels": LEVEL_PATTERNS, "roles": ROLE_PATTERNS},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
).hexdigest()
CANONICAL_ROLES = tuple(dict.fromkeys(role for _, role in ROLE_PATTERNS))


def canonical_role(value: object) -> str | None:
    """Return the canonical role contained in a normalized title."""
    title = str(value or "").strip().casefold()
    for role in sorted(CANONICAL_ROLES, key=len, reverse=True):
        canonical = role.casefold()
        if title == canonical or title.endswith(f" {canonical}"):
            return role
    return None


def normalize_title(raw_title: str) -> NormalizedTitle:
    cleaned = re.sub(r"[\[\](){}]", " ", raw_title.strip())
    cleaned = re.sub(r"\s+", " ", cleaned)
    lowered = cleaned.lower()
    level = next((value for pattern, value in LEVEL_PATTERNS if re.search(pattern, lowered)), None)
    role = next((value for pattern, value in ROLE_PATTERNS if re.search(pattern, lowered)), cleaned)
    if level in {"senior", "junior"} and not role.lower().startswith(level):
        role = f"{level.title()} {role}"
    return NormalizedTitle(role, level or "mid")
