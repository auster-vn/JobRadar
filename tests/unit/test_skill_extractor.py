from nlp.skill_extractor import extract_skills


def test_extracts_canonical_skills_and_optional_context() -> None:
    result = extract_skills(
        "Required: Python, FastAPI and PostgreSQL. Nice to have: Docker and Kubernetes."
    )
    assert result.required == ["FastAPI", "PostgreSQL", "Python"]
    assert result.nice_to_have == ["Docker", "Kubernetes"]


def test_does_not_match_short_alias_inside_word() -> None:
    result = extract_skills("We use Golang and write tests with Jest.")
    assert result.required == ["Go", "Jest"]
