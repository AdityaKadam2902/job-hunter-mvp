"""
Eligibility filtering — a separate dimension from role-fit scoring.
Answers "could this person realistically even apply here" (years required,
location, visa sponsorship), not "is this the right kind of role."

Hard exclusions get a reason stored on the job row and are dropped from
ranking entirely. Soft penalties (years required moderately over the
limit) reduce score but don't exclude — matches the established pattern
from seniority/domain scoring (soft demotion over hard filtering, except
where genuinely impossible).
"""

import re

# Matches "3+ years", "5-7 years", "minimum 4 years", "at least 2 years",
# "3 to 5 years" — the common real-world phrasings. Returns the LOWEST
# number in a range, since that's the actual minimum bar to clear.
_YEARS_PATTERNS = [
    re.compile(r"\b(\d+)\s*\+\s*years?\b", re.I),                          # "3+ years"
    re.compile(r"\bminimum\s+(?:of\s+)?(\d+)\s*years?\b", re.I),           # "minimum 4 years"
    re.compile(r"\bat least\s+(\d+)\s*years?\b", re.I),                    # "at least 2 years"
    re.compile(r"\b(\d+)\s*(?:-|to)\s*\d+\s*years?\b", re.I),              # "5-7 years" / "5 to 7 years"
    re.compile(r"\b(\d+)\s*years?\s+of\s+experience\b", re.I),             # "3 years of experience"
]


def parse_years_required(text: str) -> int | None:
    """Returns the minimum years of experience mentioned, or None if no
    clear pattern is found (absence is NOT treated as 0 — an unparseable
    description should never silently become 'entry level accepted')."""
    if not text:
        return None
    for pattern in _YEARS_PATTERNS:
        match = pattern.search(text)
        if match:
            return int(match.group(1))
    return None


def has_blocked_phrase(text: str, blocked_phrases: list[str]) -> str | None:
    """Returns the matching phrase if found, else None. Case-insensitive
    substring match — these are typically full legal/HR phrases
    ("must be authorized to work in the US"), not short terms prone to
    false positives the way single-word skill matching was."""
    if not text:
        return None
    text_lower = text.lower()
    for phrase in blocked_phrases:
        if phrase.lower() in text_lower:
            return phrase
    return None


def compute_eligibility(
    description: str,
    location: str | None,
    person_config: dict,
) -> dict:
    """Returns {'excluded': bool, 'reason': str|None, 'multiplier': float,
    'years_required': int|None}. person_config comes from role_config.py's
    per-person eligibility settings (see ROLE_PROFILES extension below).

    Hard exclusion (multiplier irrelevant, job dropped from ranking):
      - a blocked phrase is found
      - years_required exceeds max_years_required + the soft-penalty band entirely
        (i.e. genuinely impossible, not just a stretch)

    Soft penalty (multiplier < 1.0, job still ranked, just demoted):
      - years_required is over max_years_required but within the soft band
    """
    text = description or ""

    blocked = has_blocked_phrase(text, person_config.get("blocked_phrases", []))
    if blocked:
        return {"excluded": True, "reason": f"blocked phrase: '{blocked}'", "multiplier": 0.0, "years_required": None}

    years = parse_years_required(text)
    max_years = person_config.get("max_years_required")
    soft_band_top = person_config.get("max_years_soft_limit", max_years)

    if years is not None and max_years is not None:
        if years > soft_band_top:
            return {
                "excluded": True,
                "reason": f"requires {years}+ years, hard limit is {soft_band_top}",
                "multiplier": 0.0,
                "years_required": years,
            }
        if years > max_years:
            # Linear soft penalty across the band between max_years and soft_band_top.
            band_width = max(soft_band_top - max_years, 1)
            over_by = years - max_years
            multiplier = max(0.5, 1.0 - (0.5 * over_by / band_width))
            return {
                "excluded": False,
                "reason": f"requires {years} years, {over_by} over your target ({max_years})",
                "multiplier": round(multiplier, 2),
                "years_required": years,
            }

    return {"excluded": False, "reason": None, "multiplier": 1.0, "years_required": years}