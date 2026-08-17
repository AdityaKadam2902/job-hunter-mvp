"""
Regression tests for app/normalize.py.

See README.md 'Engineering decisions' for the full bug history each of
these maps to.

Run with: pytest tests/
"""

from app.normalize import classify_engagement_type, classify_seniority


class TestSeniorityClassification:
    """Bug #1: the entry-level regex matched the bare word 'associate',
    which fired on non-technical titles like 'Business Operations
    Associate' just as often as genuine junior engineering roles."""

    def test_business_operations_associate_is_not_entry(self):
        # This exact title caused the original bug — it was wrongly
        # tagged 'entry' and floated to the top of rankings.
        assert classify_seniority("Business Operations Associate", "") != "entry"

    def test_client_solutions_associate_is_not_entry(self):
        assert classify_seniority("Client Solutions Associate", "") != "entry"

    def test_new_grad_role_is_still_correctly_entry(self):
        # Make sure fixing the false positive didn't break real detection
        assert classify_seniority("New Grad ML Engineer", "") == "entry"

    def test_internship_is_entry(self):
        assert classify_seniority("Machine Learning Internship", "") == "entry"


class TestManagementTitleSeniority:
    """A related bug: 'Engineering Manager' and 'Machine Learning Manager'
    were falling through to entry-pattern text matching on the description
    and getting wrongly tagged 'entry' — a management title should never
    be classified as entry-level regardless of description wording."""

    def test_engineering_manager_is_not_entry(self):
        result = classify_seniority("Engineering Manager", "looking for someone early in their journey")
        assert result != "entry"

    def test_ml_manager_is_not_entry(self):
        assert classify_seniority("Machine Learning Manager", "") != "entry"

    def test_head_of_role_is_senior(self):
        assert classify_seniority("Head of AI", "") == "senior"


class TestEngagementTypeClassification:
    """Bug #5: engagement_type was hardcoded to always return 'full_time'
    with no actual classification logic — freelance/contract listings
    (which started appearing once RemoteOK was added) were silently
    scored as if they were full-time roles."""

    def test_freelancer_title_detected(self):
        assert classify_engagement_type("LLM Engineer Freelancer", "") == "freelance"

    def test_contract_title_detected(self):
        result = classify_engagement_type("Software Integration Engineer (6 months Contract)", "")
        assert result == "contract"

    def test_normal_role_defaults_full_time(self):
        assert classify_engagement_type("Machine Learning Engineer", "") == "full_time"

    def test_senior_role_not_falsely_flagged_as_contract(self):
        # sanity check: 'Senior' shouldn't trigger any engagement pattern
        assert classify_engagement_type("Senior AI System Software Developer", "") == "full_time"