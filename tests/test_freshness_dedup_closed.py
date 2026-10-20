"""
Regression tests for Task 2: freshness, dedupe, closed jobs.
"""

from datetime import datetime, timedelta, timezone

from app.closed_jobs import find_newly_closed_external_ids
from app.dedup import normalize_for_dedup, pick_canonical
from app.freshness import recency_score

NOW = datetime(2026, 10, 6, tzinfo=timezone.utc)


class TestRecencyScore:
    def test_brand_new_is_full_weight(self):
        assert recency_score(None, NOW, NOW) == 1.0

    def test_exactly_at_full_weight_boundary(self):
        assert recency_score(None, NOW - timedelta(days=3), NOW) == 1.0

    def test_just_past_boundary_starts_decaying(self):
        score = recency_score(None, NOW - timedelta(days=4), NOW)
        assert score < 1.0

    def test_midpoint_is_between_full_and_floor(self):
        score = recency_score(None, NOW - timedelta(days=15), NOW)
        assert 0.5 < score < 1.0

    def test_at_floor_boundary(self):
        assert recency_score(None, NOW - timedelta(days=30), NOW) == 0.5

    def test_past_floor_stays_at_floor_not_zero(self):
        """Critical: an old posting should never be fully zeroed out —
        it may still be genuinely open, just less urgent."""
        assert recency_score(None, NOW - timedelta(days=90), NOW) == 0.5

    def test_posted_at_preferred_over_scraped_at_when_available(self):
        posted = NOW - timedelta(days=1)
        scraped = NOW - timedelta(days=20)  # we found it late, but it's actually fresh
        assert recency_score(posted, scraped, NOW) == 1.0

    def test_no_timestamp_at_all_treated_as_stale(self):
        assert recency_score(None, None, NOW) == 0.5


class TestDedupNormalization:
    def test_remote_suffix_does_not_create_false_distinction(self):
        k1 = normalize_for_dedup("Snowflake", "Senior Data Engineer", None)
        k2 = normalize_for_dedup("Snowflake", "Senior Data Engineer (Remote)", "Remote")
        assert k1 == k2

    def test_genuinely_different_titles_do_not_collide(self):
        k1 = normalize_for_dedup("Snowflake", "Senior Data Engineer", None)
        k2 = normalize_for_dedup("Snowflake", "Senior Data Scientist", None)
        assert k1 != k2

    def test_genuinely_different_companies_do_not_collide(self):
        k1 = normalize_for_dedup("Snowflake", "Senior Data Engineer", None)
        k2 = normalize_for_dedup("Ramp", "Senior Data Engineer", None)
        assert k1 != k2


class TestDedupPrecedence:
    def test_direct_ats_wins_over_adzuna_regardless_of_scrape_order(self):
        """The core precedence rule from the spec: keep the direct-ATS
        record over Adzuna/RemoteOK duplicates — even if Adzuna's copy
        was scraped first."""
        group = [
            {"source": "adzuna", "scraped_at": NOW - timedelta(days=5), "id": "adzuna-1"},
            {"source": "ashby", "scraped_at": NOW, "id": "ashby-1"},
        ]
        assert pick_canonical(group)["id"] == "ashby-1"

    def test_direct_ats_wins_over_remoteok(self):
        group = [
            {"source": "remoteok", "scraped_at": NOW - timedelta(days=5), "id": "remoteok-1"},
            {"source": "greenhouse", "scraped_at": NOW, "id": "greenhouse-1"},
        ]
        assert pick_canonical(group)["id"] == "greenhouse-1"

    def test_same_priority_source_ties_broken_by_earliest_scrape(self):
        group = [
            {"source": "ashby", "scraped_at": NOW, "id": "ashby-later"},
            {"source": "ashby", "scraped_at": NOW - timedelta(days=1), "id": "ashby-earlier"},
        ]
        assert pick_canonical(group)["id"] == "ashby-earlier"


class TestClosedJobDetection:
    def test_job_missing_from_current_pull_is_newly_closed(self):
        previous = {"job-1", "job-2", "job-3"}
        current = {"job-1", "job-2"}
        assert find_newly_closed_external_ids(current, previous) == {"job-3"}

    def test_no_jobs_closed_when_all_still_present(self):
        previous = {"job-1", "job-2"}
        current = {"job-1", "job-2"}
        assert find_newly_closed_external_ids(current, previous) == set()

    def test_new_jobs_not_previously_known_are_not_closed(self):
        previous = {"job-1"}
        current = {"job-1", "job-2"}  # job-2 is new, not closed
        assert find_newly_closed_external_ids(current, previous) == set()


class _FakeRecord:
    def __init__(self, source, company_slug, external_id):
        self.source = source
        self.company_slug = company_slug
        self.external_id = external_id


class TestTrackPull:
    def setup_method(self):
        from app import closed_jobs
        closed_jobs._current_pulls.clear()

    def test_records_external_ids_per_company(self):
        from app import closed_jobs
        closed_jobs.track_pull([_FakeRecord("ashby", "ramp", "a"), _FakeRecord("ashby", "ramp", "b")])
        assert closed_jobs._current_pulls[("ashby", "ramp")] == {"a", "b"}

    def test_empty_pull_is_ignored_not_recorded(self):
        """THE critical guard: a failed fetch returns []. If that were
        recorded, every stored job at that company would look closed."""
        from app import closed_jobs
        closed_jobs.track_pull([])
        assert closed_jobs._current_pulls == {}

    def test_non_direct_ats_source_is_ignored(self):
        """Adzuna/RemoteOK are partial query-based pulls — absence from
        one search never means a listing closed."""
        from app import closed_jobs
        closed_jobs.track_pull([_FakeRecord("adzuna", "acme", "x")])
        assert closed_jobs._current_pulls == {}

    def test_separate_companies_tracked_separately(self):
        from app import closed_jobs
        closed_jobs.track_pull([_FakeRecord("lever", "hive", "1")])
        closed_jobs.track_pull([_FakeRecord("lever", "spotify", "2")])
        assert set(closed_jobs._current_pulls) == {("lever", "hive"), ("lever", "spotify")}


class TestCappedSourcesExcluded:
    def setup_method(self):
        from app import closed_jobs
        closed_jobs._current_pulls.clear()

    def test_workday_ignored_because_pull_is_capped(self):
        """Workday is capped at 100 of ~2000 jobs/company. A job rotating
        out of that window must never be treated as closed."""
        from app import closed_jobs
        closed_jobs.track_pull([_FakeRecord("workday", "nvidia-site", "w1")])
        assert closed_jobs._current_pulls == {}

    def test_smartrecruiters_ignored_because_single_page(self):
        from app import closed_jobs
        closed_jobs.track_pull([_FakeRecord("smartrecruiters", "acme", "s1")])
        assert closed_jobs._current_pulls == {}

    def test_complete_pull_sources_still_tracked(self):
        from app import closed_jobs
        for src in ("greenhouse", "lever", "ashby"):
            closed_jobs.track_pull([_FakeRecord(src, "co", "x")])
        assert len(closed_jobs._current_pulls) == 3