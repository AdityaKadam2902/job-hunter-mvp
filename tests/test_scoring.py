"""
Regression tests for app/scoring.py.

Each test here maps directly to a real bug found and fixed during
development — see README.md 'Engineering decisions' section for the full
story. The point of this file: none of these bugs should ever be able to
silently come back. If someone edits scoring.py next month and
reintroduces one of these, this suite catches it immediately instead of
relying on someone noticing weird-looking output by eye.

Run with: pytest tests/
"""

from app.scoring import (
    ai_specificity_score,
    domain_fit_score,
    keyword_overlap_score,
)


class TestKeywordOverlapSubstringSafety:
    """Bug #3: plain `in` substring checks let short skill terms match
    inside unrelated words ('agno' inside 'diagnostics', 'rag' inside
    'storage'), inflating scores on completely irrelevant jobs."""

    def test_agno_does_not_match_inside_diagnostics(self):
        resume_skills = {"agno"}
        job_text = "we run automated diagnostics on the vehicle sensor suite"
        assert keyword_overlap_score(resume_skills, job_text) == 0.0

    def test_rag_does_not_match_inside_storage(self):
        resume_skills = {"rag"}
        job_text = "experience with cloud storage systems required"
        assert keyword_overlap_score(resume_skills, job_text) == 0.0

    def test_agno_matches_as_real_whole_word(self):
        resume_skills = {"agno"}
        job_text = "we use agno as our agent framework"
        assert keyword_overlap_score(resume_skills, job_text) > 0.0

    def test_rag_matches_as_real_whole_word(self):
        resume_skills = {"rag"}
        job_text = "built a rag pipeline for retrieval augmented generation"
        assert keyword_overlap_score(resume_skills, job_text) > 0.0


class TestKeywordOverlapSaturation:
    """Bug #2: dividing by total resume skill count punished a deep,
    specific skillset — matching 7 of 51 real skills scored as low as
    0.14, even though 7 genuine matches is a strong signal on its own."""

    def test_large_skillset_does_not_dilute_strong_match(self):
        big_resume = {f"skill{i}" for i in range(51)} | {
            "rag", "langgraph", "pgvector", "fastapi", "docker", "python", "llm"
        }
        job_text = "looking for RAG, LangGraph, pgvector, FastAPI, Docker, Python, LLM experience"
        # 7 real matches should saturate close to 1.0, NOT be diluted to ~0.13 (7/51)
        assert keyword_overlap_score(big_resume, job_text) >= 0.9

    def test_score_is_capped_at_one(self):
        resume_skills = {"python", "docker", "fastapi", "rag", "llm", "postgresql", "redis", "git"}
        job_text = "python docker fastapi rag llm postgresql redis git"
        assert keyword_overlap_score(resume_skills, job_text) == 1.0


class TestDomainFit:
    """Bug #4a: a Legal/Compliance role scored high because its
    description happened to mention 'RAG' once, despite being a
    completely different department than hands-on engineering."""

    def test_legal_role_penalized_regardless_of_keyword_match(self):
        assert domain_fit_score("Principal, Applied AI Enablement, Legal") < 0.5

    def test_sales_role_penalized(self):
        assert domain_fit_score("Enterprise Account Executive") < 0.5

    def test_engineering_role_not_penalized(self):
        assert domain_fit_score("Machine Learning Engineer") == 1.0

    def test_hr_recruiting_role_penalized(self):
        assert domain_fit_score("Talent Acquisition Manager") < 0.5


class TestAiSpecificity:
    """Bug #4b: checking description text (not just title) caused every
    job at an AI-native company to score 1.0 regardless of actual role,
    because company boilerplate ('Abnormal AI is...') mentions AI on
    every posting. Title-only checking fixed this."""

    def test_generic_backend_role_deprioritized_even_with_ai_boilerplate_description(self):
        boilerplate = "Abnormal AI is a leading artificial intelligence company using AI to stop attacks."
        score = ai_specificity_score("Software Engineer - Backend", boilerplate)
        assert score < 1.0, "description boilerplate should not inflate a non-AI title's score"

    def test_devops_role_deprioritized(self):
        boilerplate = "We are an AI-first company building AI products with AI."
        score = ai_specificity_score("Systems Engineer / DevOps", boilerplate)
        assert score < 1.0

    def test_real_ml_role_scores_highest(self):
        assert ai_specificity_score("Machine Learning Engineer", "") == 1.0

    def test_ai_at_start_of_title_matches(self):
        # boundary case: 'AI Engineer' has no leading space before 'AI'
        assert ai_specificity_score("AI Engineer", "") == 1.0

    def test_fairness_engineer_does_not_false_match_on_ai_substring(self):
        # 'Fairness' contains 'ai' as a substring — must not false-positive
        score = ai_specificity_score("Fairness Engineer", "")
        assert score == 0.75  # ambiguous fallback, not a false AI match