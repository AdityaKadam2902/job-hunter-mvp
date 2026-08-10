"""
Deterministic scoring components, separate from vector similarity so each
part of the final score is inspectable — same philosophy as the HR Lens ATS
rubric (skills/experience/keyword weighting), just pointed at scoring jobs
against you instead of candidates against a role.

Skills are extracted dynamically from whatever resume is active (see
extract_resume_skills below) — not hardcoded — so swapping in a different
resume version changes the matching vocabulary automatically, no code edit
required. The static list below is only a safety-net fallback for resumes
where a Skills section can't be found.
"""

import re

# Fallback only — used if a resume has no parseable Skills section at all.
# Not meant to be your real vocabulary; that comes from your actual resume.
FALLBACK_SKILL_VOCAB = [
    "python", "sql", "javascript", "docker", "git", "aws", "rest api",
    "machine learning", "llm", "rag",
]

# Entry-level candidate: entry-tagged roles are the best fit, senior roles
# are a real stretch. Adjust these weights as your actual experience grows.
SENIORITY_FIT = {
    "entry": 1.0,
    "mid": 0.6,
    "unknown": 0.5,
    "senior": 0.15,
}

_SECTION_HEADING = re.compile(
    r"(?im)^\s*(technical\s+skills|skills\s*&?\s*tools|skills|technologies|tech\s+stack)\s*:?\s*$"
)
_NEXT_HEADING = re.compile(
    r"(?im)^\s*[A-Z][A-Z \-&/]{3,}\s*:?\s*$"  # ALL-CAPS-ish lines = likely next resume section
)
_SPLIT_CHARS = re.compile(r"[,|•·\u2022\n;/]+")


def extract_resume_skills(resume_text: str) -> set[str]:
    """Find the resume's own Skills section and parse it into a set of
    normalized skill terms. Falls back to FALLBACK_SKILL_VOCAB filtered by
    what actually appears in the resume text, if no section is found."""
    heading_match = _SECTION_HEADING.search(resume_text)
    if heading_match:
        rest = resume_text[heading_match.end():]
        next_heading = _NEXT_HEADING.search(rest)
        section_text = rest[: next_heading.start()] if next_heading else rest[:800]

        raw_terms = _SPLIT_CHARS.split(section_text)
        skills = {
            t.strip().lower()
            for t in raw_terms
            if t.strip() and 1 < len(t.strip()) <= 40
        }
        # Drop obvious non-skill noise (empty-ish fragments, stray colons/dashes)
        skills = {s for s in skills if re.search(r"[a-z]", s)}
        if skills:
            return skills

    # Fallback: no clean Skills section found — use the small safety-net
    # list, but only keep terms that actually appear in this resume, so we
    # don't claim a skill the person never wrote.
    resume_lower = resume_text.lower()
    return {s for s in FALLBACK_SKILL_VOCAB if s in resume_lower}


def keyword_overlap_score(resume_skills: set[str], job_text: str) -> float:
    """Fraction of the resume's own extracted skills that appear in the job
    text. Transparent on purpose — matched_skills() below shows exactly
    which ones matched."""
    if not resume_skills:
        return 0.0
    job_lower = job_text.lower()
    matched = {s for s in resume_skills if s in job_lower}
    return len(matched) / len(resume_skills)


def matched_skills(resume_skills: set[str], job_text: str) -> list[str]:
    job_lower = job_text.lower()
    return sorted(s for s in resume_skills if s in job_lower)


def seniority_fit_score(seniority: str) -> float:
    return SENIORITY_FIT.get(seniority, 0.5)


def final_score(similarity: float, keyword_score: float, seniority_score: float) -> float:
    """Weighted combination. Similarity carries the most weight since it
    captures semantic fit beyond exact keyword matches; keyword overlap is
    weighted second-highest since a real skill match is strong relevance
    signal. Seniority fit is intentionally the smallest weight — it's a
    tiebreaker, not something that should let a completely unrelated
    'entry-tagged' role outrank a genuinely skill-matched one."""
    return (0.5 * similarity) + (0.4 * keyword_score) + (0.1 * seniority_score)