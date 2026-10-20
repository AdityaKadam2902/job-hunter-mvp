"""
Recency scoring for Task 2 of the gap-closing spec. Full weight under 3
days old, linearly decaying to a floor by 30 days — not a hard cutoff,
since an older posting can still be genuinely open and relevant, just
less urgent than something posted yesterday.

Uses posted_at when a source actually provides it; falls back to
scraped_at (our own first-seen timestamp) since most connectors don't
reliably populate posted_at yet — a real limitation, documented, not
silently papered over.
"""

from datetime import datetime, timezone

FULL_WEIGHT_DAYS = 3
DECAY_FLOOR_DAYS = 30
DECAY_FLOOR = 0.5  # never fully zero out an older posting


def recency_score(posted_at: datetime | None, scraped_at: datetime, now: datetime | None = None) -> float:
    """1.0 for anything <= FULL_WEIGHT_DAYS old, linearly decaying to
    DECAY_FLOOR by DECAY_FLOOR_DAYS, then flat at the floor beyond that."""
    now = now or datetime.now(timezone.utc)
    reference = posted_at or scraped_at
    if reference is None:
        return DECAY_FLOOR  # no timestamp at all — treat as stale, not fresh

    age_days = (now - reference).total_seconds() / 86400

    if age_days <= FULL_WEIGHT_DAYS:
        return 1.0
    if age_days >= DECAY_FLOOR_DAYS:
        return DECAY_FLOOR

    # Linear interpolation between (FULL_WEIGHT_DAYS, 1.0) and (DECAY_FLOOR_DAYS, DECAY_FLOOR)
    span_days = DECAY_FLOOR_DAYS - FULL_WEIGHT_DAYS
    progress = (age_days - FULL_WEIGHT_DAYS) / span_days
    return round(1.0 - progress * (1.0 - DECAY_FLOOR), 3)