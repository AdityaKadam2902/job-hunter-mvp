import hashlib
import re
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel


class JobRecord(BaseModel):
    source: str
    company: str
    company_slug: str
    external_id: str
    title: str
    location: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    posted_at: Optional[datetime] = None
    engagement_type: str = "full_time"
    seniority: str = "unknown"
    content_hash: str = ""

    def finalize(self) -> "JobRecord":
        """Fill in derived fields. Call after construction."""
        self.seniority = classify_seniority(self.title, self.description or "")
        self.engagement_type = classify_engagement_type(self.title, self.description or "")
        self.content_hash = make_content_hash(self.company, self.title, self.description or "")
        return self


# --- Seniority tagging ---------------------------------------------------
# Deliberately simple and rule-based for the MVP. This is NOT the scoring
# engine — it's just a coarse tag so the ingest step gives you something
# queryable ("show me entry-level roles") before the real rubric exists.

_SENIOR_PATTERNS = re.compile(
    r"\b(senior|sr\.?|staff|principal|lead|architect|director|head of)\b", re.I
)
_MANAGEMENT_TITLE = re.compile(r"\b(manager|head)\b", re.I)
_ENTRY_PATTERNS = re.compile(
    r"\b(intern|internship|entry.level|entry level|new grad|graduate|junior|jr\.?|"
    r"0-2 years|0-1 year)\b",
    re.I,
)
# NOTE: deliberately removed bare "associate" — it was firing on non-technical
# titles like "Business Operations Associate" just as much as on genuine
# junior engineering roles, which was pushing irrelevant jobs to the top of
# the ranked list purely on a seniority-tag false positive.

_FREELANCE_PATTERNS = re.compile(
    r"\b(freelance|freelancer)\b", re.I
)
_CONTRACT_PATTERNS = re.compile(
    r"\b(contract|contractor|contract-to-hire|c2h|\d+\s*month[s]?\s*contract|"
    r"fixed.term|temporary|temp\b)\b", re.I
)


def classify_engagement_type(title: str, description: str) -> str:
    """Was previously hardcoded to always return 'full_time' — a real gap
    flagged once RemoteOK started surfacing genuine freelance/contract
    listings (e.g. 'LLM Engineer Freelancer', 'Software Integration
    Engineer (6 months Contract)') that were silently scored as if they
    were full-time roles. Checks title primarily — same lesson as the
    seniority/domain classifiers: title is a more reliable signal than
    description text, which often mentions unrelated contract terms
    (benefits, legal boilerplate) regardless of the role's actual type."""
    if _FREELANCE_PATTERNS.search(title):
        return "freelance"
    if _CONTRACT_PATTERNS.search(title):
        return "contract"
    return "full_time"


def classify_seniority(title: str, description: str) -> str:
    if _SENIOR_PATTERNS.search(title):
        # trust the title over the description for senior signal —
        # descriptions often mention "mentor senior engineers" etc.
        return "senior"
    if _MANAGEMENT_TITLE.search(title):
        # A "Manager" or "Head of X" title is never entry-level, regardless
        # of what wording the description happens to use. Treat as at least
        # mid rather than let entry-pattern text hits override the title.
        return "mid"

    text = f"{title} {description}"
    if _ENTRY_PATTERNS.search(text):
        return "entry"
    if _SENIOR_PATTERNS.search(text):
        return "senior"
    return "mid"


def make_content_hash(company: str, title: str, description: str) -> str:
    """Stable hash for dedup across sources/re-runs. Truncate description so
    minor formatting differences between scrapes don't create false-unique
    rows for the same posting."""
    basis = f"{company.strip().lower()}|{title.strip().lower()}|{(description or '')[:500].strip().lower()}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)