"""
tests/test_raw_store.py — RAW store byte-exact recovery and invariant tests.

Tests: I1 (immutability), I3 (byte-exact recovery)
Quality gate: RAW_RECOVERY_SHA_MATCH = 100%
"""

import hashlib
import pathlib

import pytest

from fiofilter.raw_store import RawStore
from fiofilter.types import EvidenceClass, Mode, RawRef


class TestRawStoreWriteRead:
    def test_round_trip_exact(self, tmp_raw_store: RawStore):
        """I3: sha256(read(ref)) == ref.sha256 and read(ref) == original."""
        content = b"Hello, FioFilter! Evidence must survive.\n"
        ref = tmp_raw_store.write(content, evidence_class=EvidenceClass.NOISE, mode=Mode.BUILD)
        recovered = tmp_raw_store.read(ref, verify=True)

        assert recovered == content
        assert ref.sha256 == hashlib.sha256(content).hexdigest()

    def test_sha256_verification_passes(self, tmp_raw_store: RawStore):
        """I3: verify=True does not raise for uncorrupted content."""
        content = b"test content"
        ref = tmp_raw_store.write(content)
        # Should not raise
        tmp_raw_store.read(ref, verify=True)

    def test_dedup_same_content(self, tmp_raw_store: RawStore):
        """I1: Identical content is stored once; same ref returned."""
        content = b"identical content"
        ref1 = tmp_raw_store.write(content)
        ref2 = tmp_raw_store.write(content)

        assert ref1.sha256 == ref2.sha256
        assert ref1.store_path == ref2.store_path

    def test_different_content_different_ref(self, tmp_raw_store: RawStore):
        """Different content produces different refs."""
        ref1 = tmp_raw_store.write(b"content A")
        ref2 = tmp_raw_store.write(b"content B")

        assert ref1.sha256 != ref2.sha256

    def test_empty_content(self, tmp_raw_store: RawStore):
        """Empty bytes stored and recovered correctly."""
        content = b""
        ref = tmp_raw_store.write(content)
        recovered = tmp_raw_store.read(ref, verify=True)
        assert recovered == content

    def test_large_content(self, tmp_raw_store: RawStore):
        """Content > 64KB stored and recovered correctly."""
        content = b"X" * 100_000
        ref = tmp_raw_store.write(content)
        recovered = tmp_raw_store.read(ref, verify=True)
        assert recovered == content
        assert len(recovered) == 100_000

    def test_unicode_content(self, tmp_raw_store: RawStore):
        """Arbitrary UTF-8 bytes stored and recovered correctly."""
        content = "FioFilter — filtro de evidências 🔬\n".encode("utf-8")
        ref = tmp_raw_store.write(content)
        recovered = tmp_raw_store.read(ref, verify=True)
        assert recovered == content

    def test_binary_content(self, tmp_raw_store: RawStore):
        """Binary bytes stored and recovered correctly."""
        content = bytes(range(256))
        ref = tmp_raw_store.write(content)
        recovered = tmp_raw_store.read(ref, verify=True)
        assert recovered == content

    def test_directory_structure_created(self, tmp_path: pathlib.Path):
        """Store creates correct directory structure."""
        store = RawStore(root=tmp_path / "store")
        content = b"structure test"
        ref = store.write(content)

        sha = ref.sha256
        expected_obj = tmp_path / "store" / "objects" / sha[:2] / sha
        expected_meta = tmp_path / "store" / "meta" / sha[:2] / f"{sha}.json"
        expected_index = tmp_path / "store" / "index.jsonl"

        assert expected_obj.exists()
        assert expected_meta.exists()
        assert expected_index.exists()

    def test_index_jsonl_appended(self, tmp_raw_store: RawStore):
        """index.jsonl gets one line per unique write."""
        tmp_raw_store.write(b"entry 1")
        tmp_raw_store.write(b"entry 2")
        tmp_raw_store.write(b"entry 1")  # dedup — should NOT add a new line

        index_path = tmp_raw_store.root / "index.jsonl"
        lines = index_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2  # only two unique entries

    def test_missing_entry_raises(self, tmp_raw_store: RawStore):
        """Reading a non-existent entry raises FileNotFoundError."""
        fake_sha = "a" * 64
        fake_ref = RawRef(
            sha256=fake_sha,
            store_path=str(tmp_raw_store.root / "objects" / fake_sha[:2] / fake_sha),
        )
        with pytest.raises(FileNotFoundError):
            tmp_raw_store.read(fake_ref)

    def test_i1_blob_is_immutable_by_design(self, tmp_raw_store: RawStore):
        """I1: After write, the blob file should not be modified by write()."""
        content = b"original content"
        ref = tmp_raw_store.write(content)

        blob_path = pathlib.Path(ref.store_path)
        mtime_before = blob_path.stat().st_mtime

        # Write same content again (dedup path — no re-write)
        tmp_raw_store.write(content)
        mtime_after = blob_path.stat().st_mtime

        assert mtime_before == mtime_after  # file was not touched

    def test_exists(self, tmp_raw_store: RawStore):
        """exists() returns True after write, False before."""
        content = b"check existence"
        sha = hashlib.sha256(content).hexdigest()

        assert not tmp_raw_store.exists(sha)
        tmp_raw_store.write(content)
        assert tmp_raw_store.exists(sha)
