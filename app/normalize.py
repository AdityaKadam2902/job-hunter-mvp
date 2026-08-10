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
        self.content_hash = make_content_hash(self.company, self.title, self.description or "")
        return self


# --- Seniority tagging ---------------------------------------------------
# Deliberately simple and rule-based for the MVP. This is NOT the scoring
# engine — it's just a coarse tag so the ingest step gives you something
# queryable ("show me entry-level roles") before the real rubric exists.

_SENIOR_PATTERNS = re.compile(
    r"\b(senior|sr\.?|staff|principal|lead|architect|director|head of)\b", re.I
)
_ENTRY_PATTERNS = re.compile(
    r"\b(intern|internship|entry.level|entry level|new grad|graduate|junior|jr\.?|"
    r"0-2 years|0-1 year)\b",
    re.I,
)
# NOTE: deliberately removed bare "associate" — it was firing on non-technical
# titles like "Business Operations Associate" just as much as on genuine
# junior engineering roles, which was pushing irrelevant jobs to the top of
# the ranked list purely on a seniority-tag false positive.


def classify_seniority(title: str, description: str) -> str:
    text = f"{title} {description}"
    if _SENIOR_PATTERNS.search(title):
        # trust the title over the description for senior signal —
        # descriptions often mention "mentor senior engineers" etc.
        return "senior"
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