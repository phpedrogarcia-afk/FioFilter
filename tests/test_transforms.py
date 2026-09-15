"""
tests/test_transforms.py — T01 duplicate-line folding tests.

Tests: determinism, no-expansion (I9), round-trip via RAW store, fail-open.
"""

import pytest

from fiofilter.transforms.t01_dup_fold import DuplicateLineFold, FOLD_THRESHOLD


@pytest.fixture
def t01():
    return DuplicateLineFold()


class TestT01DeterminismAndIdentity:
    def test_deterministic_with_duplicates(self, t01):
        content = b"line\nline\nline\ndifferent\n"
        assert t01.apply(content) == t01.apply(content)

    def test_deterministic_no_duplicates(self, t01):
        content = b"a\nb\nc\nd\n"
        assert t01.apply(content) == t01.apply(content)

    def test_no_duplicates_returns_none(self, t01):
        """No duplicates → None (engine returns RAW)."""
        content = b"a\nb\nc\nd\n"
        assert t01.apply(content) is None

    def test_single_duplicate_triggers_fold(self, t01):
        """Two identical consecutive long lines → fold fires (result < raw)."""
        # Line must be long enough that fold marker doesn't negate savings
        long_line = "same line content repeated here with enough data " * 4 + "\n"
        content = (long_line * 2 + "different\n").encode("utf-8")
        result = t01.apply(content)
        assert result is not None
        assert b"same line content" in result
        assert b"count=2 first=1 last=2" in result

    def test_many_duplicates_folded(self, t01):
        """20 duplicate lines fold to 1 + marker."""
        lines = ["repeated\n"] * 20
        content = "".join(lines).encode("utf-8")
        result = t01.apply(content)
        assert result is not None
        assert b"repeated" in result
        assert b"count=20 first=1 last=20" in result  # count includes first

    def test_mixed_content_preserved(self, t01):
        """Non-duplicate lines pass through unchanged; long dups get folded."""
        long_dup = "duplicated line content that is long enough to save space\n"
        content = ("unique1\n" + long_dup * 5 + "unique2\n").encode("utf-8")
        result = t01.apply(content)
        assert result is not None
        assert b"unique1" in result
        assert b"unique2" in result
        assert b"duplicated line" in result

    def test_transform_id(self, t01):
        assert t01.transform_id == "T01"


class TestT01NoExpansion:
    def test_result_smaller_than_raw(self, t01):
        """I9: Result must be strictly smaller than raw."""
        content = b"line\n" * 20
        result = t01.apply(content)
        assert result is not None
        assert len(result) < len(content)

    def test_tiny_fold_returns_none_if_no_savings(self, t01):
        """If fold marker is longer than saved lines, None is returned."""
        # Two identical lines but very short — fold marker may be longer
        content = b"a\na\n"
        result = t01.apply(content)
        # Result should be None OR smaller — not larger
        if result is not None:
            assert len(result) < len(content)


class TestT01RoundTripViaRawStore:
    def test_raw_store_always_has_original(self, t01, tmp_raw_store):
        """RAW store contains byte-exact original regardless of transform."""
        content = b"dup\n" * 10
        ref = tmp_raw_store.write(content)
        result = t01.apply(content)

        recovered = tmp_raw_store.read(ref, verify=True)
        assert recovered == content  # original unchanged in store

    def test_transform_does_not_affect_raw_store(self, t01, tmp_raw_store):
        """Applying transform does not modify RAW store entry."""
        content = b"line\n" * 5
        ref = tmp_raw_store.write(content)
        t01.apply(content)  # transform fires

        # Store still has original
        recovered = tmp_raw_store.read(ref)
        assert recovered == content


class TestT01FailOpen:
    def test_binary_content_returns_none(self, t01):
        """Binary content that can't be decoded → None (engine returns RAW)."""
        content = bytes(range(256))
        result = t01.apply(content)
        assert result is None  # transform gracefully declines

    def test_empty_content_returns_none(self, t01):
        """Empty content → None (no transform to apply)."""
        content = b""
        result = t01.apply(content)
        assert result is None
