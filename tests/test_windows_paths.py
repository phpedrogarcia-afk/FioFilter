"""
tests/test_windows_paths.py — Windows path and RAW store behavior tests.

Tests: safe Windows paths, long paths, store outside repo.
"""

import pathlib
import pytest

from fiofilter.raw_store import RawStore


class TestWindowsPaths:
    def test_store_in_temp_path(self, tmp_path: pathlib.Path):
        """RAW store works in a standard temp path."""
        store = RawStore(root=tmp_path / "raw")
        content = b"Windows path test"
        ref = store.write(content)
        recovered = store.read(ref, verify=True)
        assert recovered == content

    def test_store_path_with_spaces(self, tmp_path: pathlib.Path):
        """RAW store works in paths containing spaces."""
        store_path = tmp_path / "my raw store"
        store = RawStore(root=store_path)
        content = b"path with spaces"
        ref = store.write(content)
        recovered = store.read(ref)
        assert recovered == content

    def test_store_root_is_outside_fiofilter_repo(self):
        """Default store root is outside the FioFilter repo directory."""
        from fiofilter.raw_store import _get_root
        root = _get_root()
        fiofilter_repo = pathlib.Path(__file__).parent.parent.resolve()
        # Default store should NOT be inside the repo
        # (may be overridden by env var in tests — check only default)
        import os
        if os.environ.get("FIOFILTER_RAW_STORE") is None:
            assert not str(root).startswith(str(fiofilter_repo)), \
                f"Default raw store {root} is inside repo {fiofilter_repo}"

    def test_sha256_prefix_subdirs(self, tmp_path: pathlib.Path):
        """Objects are stored in 2-char prefix subdirectories."""
        store = RawStore(root=tmp_path / "raw")
        content = b"prefix test"
        ref = store.write(content)
        sha = ref.sha256
        obj_path = pathlib.Path(ref.store_path)
        assert obj_path.parent.name == sha[:2]

    def test_multiple_entries_coexist(self, tmp_path: pathlib.Path):
        """Multiple different entries coexist in the same store."""
        store = RawStore(root=tmp_path / "raw")
        refs = []
        for i in range(10):
            content = f"entry {i}".encode("utf-8")
            ref = store.write(content)
            refs.append((ref, content))

        for ref, original in refs:
            assert store.read(ref, verify=True) == original
