from app.scoring import resolve_resume_skills


def test_cached_llm_skills_are_used_not_regex():
    resume = {"skills": ["pgvector", "langgraph", "CI/CD"], "raw_text": "CI/CD, Prompt Engineering"}
    assert resolve_resume_skills(resume) == {"pgvector", "langgraph", "ci/cd"}


def test_ci_cd_is_not_split_into_junk_tokens():
    resume = {"skills": ["ci/cd"], "raw_text": "CI/CD"}
    skills = resolve_resume_skills(resume)
    assert "ci" not in skills and "cd" not in skills


def test_falls_back_to_regex_when_nothing_cached():
    resume = {"skills": None, "raw_text": "Python, Docker"}
    assert {"python", "docker"} <= resolve_resume_skills(resume)


def test_empty_cached_list_falls_back_to_regex():
    resume = {"skills": [], "raw_text": "Python"}
    assert "python" in resolve_resume_skills(resume)