import re

from app.role_config import get_role_profile

_DEFAULT_PROFILE = get_role_profile(None)

FALLBACK_SKILL_VOCAB = ["python", "sql", "javascript", "docker", "git", "aws", "rest api", "machine learning", "llm", "rag"]

SENIORITY_FIT = {"entry": 1.0, "mid": 0.7, "unknown": 0.55, "senior": 0.2}

_SECTION_HEADING = re.compile(r"(?im)^\s*(technical\s+skills|skills\s*&?\s*tools|skills|technologies|tech\s+stack)\s*:?\s*$")
_NEXT_HEADING = re.compile(r"(?im)^\s*[A-Z][A-Z \-&/]{3,}\s*:?\s*$")
# Added ':' — resumes with sub-headers like "Programming: Python, SQL" were
# keeping "programming:  python" as one garbled fragment instead of
# splitting into separate terms, because ':' wasn't a recognized separator.
_SPLIT_CHARS = re.compile(r"[,|•·\u2022\n;/:]+")
# Category label words that survive splitting (the word before the colon)
# and aren't real skills themselves — drop these explicitly rather than
# let them pollute the extracted set.
_LABEL_NOISE = {
    "programming", "tools", "sql & databases", "visualization & bi",
    "sql databases", "visualization bi", "languages", "frameworks",
    "databases", "services", "software", "platforms",
}


def extract_resume_skills(resume_text: str) -> set[str]:
    heading_match = _SECTION_HEADING.search(resume_text)
    if heading_match:
        rest = resume_text[heading_match.end():]
        next_heading = _NEXT_HEADING.search(rest)
        section_text = rest[: next_heading.start()] if next_heading else rest[:800]
        # Strip parentheses characters (not their contents) BEFORE
        # splitting — otherwise "Microsoft Office (Excel, PowerPoint)"
        # splits into "Microsoft Office (Excel" and "PowerPoint)", leaving
        # stray '(' / ')' characters stuck to real skill names.
        section_text = section_text.replace("(", ",").replace(")", ",")
        raw_terms = _SPLIT_CHARS.split(section_text)
        skills = {t.strip().lower() for t in raw_terms if t.strip() and 1 < len(t.strip()) <= 40}
        skills = {s for s in skills if re.search(r"[a-z]", s)}
        skills = {s for s in skills if s not in _LABEL_NOISE}
        if skills:
            return skills
    resume_lower = resume_text.lower()
    return {s for s in FALLBACK_SKILL_VOCAB if s in resume_lower}


def _contains_skill(skill: str, text_lower: str) -> bool:
    pattern = r"\b" + re.escape(skill) + r"\b"
    return re.search(pattern, text_lower) is not None


def keyword_overlap_score(resume_skills: set[str], job_text: str, saturation: int = 6) -> float:
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


OFF_DOMAIN_TITLE_MARKERS = [
    "legal", "compliance", "recruiting", "talent acquisition", "hr ", "human resources",
    "sales", "account executive", "marketing", "finance", "accounting", "growth",
    "customer success", "business development", "sales engineer",
]


def domain_fit_score(title: str) -> float:
    title_lower = title.lower()
    if any(marker in title_lower for marker in OFF_DOMAIN_TITLE_MARKERS):
        return 0.1
    return 1.0


def role_specificity_score(title: str, description: str, role_specific_markers: list | None = None,
                            generic_adjacent_markers: list | None = None) -> float:
    """1.0 for a role matching the target field, 0.5 for adjacent-but-
    different engineering work, 0.75 for ambiguous. TITLE ONLY —
    description text is unreliable, since company boilerplate mentions
    buzzwords regardless of the actual role.

    Marker lists default to the AI/ML profile (backward-compatible with
    every existing caller/test) — pass explicit lists from a specific
    role profile (see app/role_config.py) to target a different field."""
    role_specific_markers = role_specific_markers or _DEFAULT_PROFILE["role_specific_markers"]
    generic_adjacent_markers = generic_adjacent_markers or _DEFAULT_PROFILE["generic_adjacent_markers"]

    title_lower = f" {title.lower()} "
    if any(marker in title_lower for marker in role_specific_markers):
        return 1.0
    if any(marker in title_lower for marker in generic_adjacent_markers):
        return 0.5
    return 0.75


# Backward-compatible alias — existing code (match.py, tailor.py, api.py,
# tests) calls this by its original name. New code can use either name;
# both point at the same function.
ai_specificity_score = role_specificity_score


def get_sub_role_tags(title: str, sub_role_tags: dict | None = None) -> list[str]:
    """Fine-grained badges for a job title. TITLE ONLY, same reasoning as
    role_specificity_score. Defaults to the AI/ML profile's tags —
    pass a specific profile's dict (see app/role_config.py) to target a
    different field. A job can match multiple tags, or none."""
    sub_role_tags = sub_role_tags or _DEFAULT_PROFILE["sub_role_tags"]
    title_lower = f" {title.lower()} "
    return [tag for tag, markers in sub_role_tags.items() if any(m in title_lower for m in markers)]


def final_score(similarity: float, keyword_score: float, seniority_score: float,
                 domain_score: float, ai_specificity: float) -> float:
    return ((0.3 * similarity) + (0.3 * keyword_score) + (0.15 * seniority_score)
            + (0.15 * domain_score) + (0.1 * ai_specificity))