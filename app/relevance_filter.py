"""
Used by app.ingest to skip embedding obviously irrelevant jobs from bulk
company pulls (Greenhouse/Lever/Ashby/Workday return EVERY open role at a
company — Sales, Legal, HR included — even though only a handful are ever
going to be relevant to anyone tracked in this instance).

Deliberately a UNION across every tracked person's role profile, not just
one — a title only gets dropped if it matches NOBODY's target, so adding
a new profile (a new person) never accidentally filters out jobs that
person actually wanted.

NOT applied to Adzuna/RemoteOK — those are already role-targeted at the
source (query-based), so a second filter pass would be redundant.
"""

from app.role_config import ROLE_PROFILES


def build_shared_relevance_markers() -> set[str]:
    """Union of every profile's role-specific AND generic-adjacent
    markers — a title matching ANY of these for ANY tracked person is
    worth keeping. Only titles matching NONE of them (Sales, Legal, HR,
    Marketing, Finance, etc, for everyone) get dropped."""
    markers = set()
    for profile in ROLE_PROFILES.values():
        markers |= set(profile["role_specific_markers"])
        markers |= set(profile["generic_adjacent_markers"])
    return markers


def is_relevant_title(title: str, markers: set[str]) -> bool:
    title_lower = f" {title.lower()} "
    return any(m in title_lower for m in markers)