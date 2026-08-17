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

# You're a fresher with ~1 year of internship experience — senior roles are
# a genuine long shot, not just a "stretch." This value was softened to
# 0.35 earlier based on a small labeled sample where you marked a few
# senior roles relevant, but your direct, explicit correction here is a
# stronger signal than 9-19 sparse labels. Locked at 0.2: senior roles can
# still surface if everything else about them is an exceptional match, but
# they won't casually outrank realistic entry/mid roles anymore.
SENIORITY_FIT = {
    "entry": 1.0,
    "mid": 0.7,
    "unknown": 0.55,
    "senior": 0.2,
}

# Titles containing these are almost always a different functional domain
# than hands-on AI/ML engineering, even when the description mentions AI
# buzzwords in passing (e.g. "Applied AI Enablement, Legal" matches "RAG"
# as a keyword but is a legal/compliance role, not an engineering one).
# This is what actually separates "senior stretch role I still want to see"
# from "wrong field entirely" — two things the old rubric conflated.
OFF_DOMAIN_TITLE_MARKERS = [
    "legal", "compliance", "recruiting", "talent acquisition", "hr ",
    "human resources", "sales", "account executive", "marketing",
    "finance", "accounting", "growth", "customer success",
    "business development", "sales engineer",
]


def domain_fit_score(title: str) -> float:
    """1.0 if the role looks like it's in your actual field (hands-on
    engineering/ML/product-technical), penalized hard if the title signals
    a different department entirely — regardless of how many AI keywords
    the description happens to mention."""
    title_lower = title.lower()
    if any(marker in title_lower for marker in OFF_DOMAIN_TITLE_MARKERS):
        return 0.1
    return 1.0


# Distinguishes CORE AI/ML roles from generic software engineering roles
# that happen to exist at an AI company. Your originally scoped target was
# "AI/ML Engineer roles specifically" — not broad SWE — so a Backend
# Engineer or DevOps role at Abnormal shouldn't rank the same as an actual
# ML Engineer role there, even though both pass the domain_fit check above.
AI_SPECIFIC_MARKERS = [
    "machine learning", "ml engineer", " ai ", "ai engineer", "genai",
    "generative ai", "applied scientist", "research scientist",
    "data scientist", "nlp", "computer vision", "deep learning",
    "llm", "artificial intelligence",
]
# Generic technical titles that are NOT AI-specific, even at an AI company —
# deprioritized relative to core AI/ML roles, but not excluded (still real
# engineering work you could plausibly do).
GENERIC_SWE_TITLE_MARKERS = [
    "backend", "front end", "frontend", "devops", "site reliability",
    "systems engineer", "platform engineer", "integration engineer",
    "qa engineer", "security engineer", "infrastructure",
]


def ai_specificity_score(title: str, description: str) -> float:
    """1.0 for core AI/ML roles, 0.5 for generic SWE roles at an AI company
    (real work, just not your primary target), 0.75 for anything ambiguous.

    TITLE ONLY, deliberately — description is unreliable here. Companies
    like Abnormal, Hive, and Wayve mention 'AI' in their company boilerplate
    on EVERY job posting regardless of role, so checking description text
    made a DevOps or Backend role at an AI company score identically to an
    actual ML Engineer role. `description` param is kept for future use but
    intentionally unused right now."""
    title_lower = f" {title.lower()} "  # padded so ' ai ' matches even at start/end of title

    if any(marker in title_lower for marker in AI_SPECIFIC_MARKERS):
        return 1.0
    if any(marker in title_lower for marker in GENERIC_SWE_TITLE_MARKERS):
        return 0.5
    return 0.75

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


import re as _re


def _contains_skill(skill: str, text_lower: str) -> bool:
    """Whole-word/phrase match, not plain substring containment. Plain `in`
    checks let short skill terms falsely match inside unrelated words —
    e.g. 'agno' was matching inside 'diagnostics', inflating scores on
    completely unrelated jobs. \\b handles both single words and
    multi-word phrases like 'computer vision' correctly."""
    pattern = r"\b" + _re.escape(skill) + r"\b"
    return _re.search(pattern, text_lower) is not None


def keyword_overlap_score(resume_skills: set[str], job_text: str, saturation: int = 6) -> float:
    """Score based on ABSOLUTE count of matched skills, capped at
    `saturation`, not the fraction of your total resume vocabulary.

    Why: fraction-of-total punishes a deep, specific skillset. If your
    resume has 51 real extracted skills and a job matches 7 of them,
    that's a genuinely strong match — but 7/51 = 0.14 makes it look weak.
    Matching 6+ real skills on any single job posting is already an
    excellent signal regardless of how large your total skillset is."""
    if not resume_skills:
        return 0.0
    job_lower = job_text.lower()
    matched_count = sum(1 for s in resume_skills if _contains_skill(s, job_lower))
    return min(1.0, matched_count / saturation)


def matched_skills(resume_skills: set[str], job_text: str) -> list[str]:
    job_lower = job_text.lower()
    return sorted(s for s in resume_skills if _contains_skill(s, job_lower))


def seniority_fit_score(seniority: str) -> float:
    return SENIORITY_FIT.get(seniority, 0.5)


def final_score(similarity: float, keyword_score: float, seniority_score: float,
                 domain_score: float, ai_specificity: float) -> float:
    """Weighted combination. Seniority fit weight raised from 0.1 to 0.15 —
    with the value itself also lowered for senior roles, this makes
    seniority a genuinely decisive factor, matching the explicit correction
    that senior roles are a long shot for a fresher, not just a mild
    deprioritization."""
    return ((0.3 * similarity) + (0.3 * keyword_score) + (0.15 * seniority_score)
            + (0.15 * domain_score) + (0.1 * ai_specificity))