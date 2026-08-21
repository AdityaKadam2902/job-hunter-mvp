"""
Regression tests for app/track.py's pure-logic pieces.

Only the UUID-detection function is tested here — everything else in
track.py requires a real database connection, which isn't something this
suite runs against (see README: 'Regression tests' section on why the
scoring/normalize tests stay database-free by design).
"""

from app.track import is_uuid_like


class TestUuidDetection:
    def test_real_uuid_detected(self):
        assert is_uuid_like("3f9a2b1c-4d5e-6f7a-8b9c-0d1e2f3a4b5c") is True

    def test_single_digit_rank_not_uuid(self):
        assert is_uuid_like("4") is False

    def test_two_digit_rank_not_uuid(self):
        assert is_uuid_like("42") is False

    def test_plain_text_not_uuid(self):
        assert is_uuid_like("not-a-uuid") is False