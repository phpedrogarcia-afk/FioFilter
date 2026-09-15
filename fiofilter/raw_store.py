"""
fiofilter.raw_store — Immutable, content-addressable local RAW store.

Design (per ARCHITECTURE.md):
  - SHA-256 content-addressable
  - Atomic writes (write to .tmp, rename — same volume)
  - Metadata sidecar separate from content blob
  - Append-only index.jsonl
  - No network, no external DB
  - No deletion in V0
  - Windows-safe paths
  - Default location: ~/.fiofilter/raw/ (outside repo)
  - Configurable via FIOFILTER_RAW_STORE env var

Layout:
  {root}/
    objects/
      {sha256[0:2]}/
        {sha256}          ← immutable content blob
    meta/
      {sha256[0:2]}/
        {sha256}.json     ← metadata sidecar
    index.jsonl           ← append-only reference log

Invariants enforced:
  I1: Content blobs are never modified after write.
  I3: sha256(read(ref)) == ref.sha256 (verified on read if check=True).
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import time
from dataclasses import asdict, dataclass
from typing import Optional

from fiofilter.types import EvidenceClass, Mode, RawRef

# Default raw store location (outside repo, per architecture)
_DEFAULT_RAW_STORE = pathlib.Path.home() / ".fiofilter" / "raw"

# Environment variable override
_ENV_VAR = "FIOFILTER_RAW_STORE"


def _get_root() -> pathlib.Path:
    """Resolve the RAW store root directory."""
    env_val = os.environ.get(_ENV_VAR)
    if env_val:
        return pathlib.Path(env_val)
    return _DEFAULT_RAW_STORE


@dataclass
class RawMeta:
    """Metadata sidecar for a RAW store entry."""

    raw_sha256: str
    stored_at_utc: str
    source: str
    command: Optional[str]
    evidence_class: str
    mode: str
    byte_length: int
    session_id: Optional[str] = None
    inline_required_facts: Optional[list] = None


class RawStore:
    """
    Immutable, content-addressable local RAW store.

    Usage:
        store = RawStore()                    # uses default/env location
        store = RawStore(root="/custom/path") # override location
        ref = store.write(content_bytes, ...)
        recovered = store.read(ref)
        assert recovered == content_bytes
    """

    def __init__(self, root: Optional[pathlib.Path] = None) -> None:
        if root is None:
            root = _get_root()
        self.root = pathlib.Path(root)
        self._objects_dir = self.root / "objects"
        self._meta_dir = self.root / "meta"
        self._index_path = self.root / "index.jsonl"

    def _ensure_dirs(self) -> None:
        """Create required directory structure if not present."""
        self._objects_dir.mkdir(parents=True, exist_ok=True)
        self._meta_dir.mkdir(parents=True, exist_ok=True)
        self.root.mkdir(parents=True, exist_ok=True)

    def _object_path(self, sha256: str) -> pathlib.Path:
        prefix = sha256[:2]
        return self._objects_dir / prefix / sha256

    def _meta_path(self, sha256: str) -> pathlib.Path:
        prefix = sha256[:2]
        return self._meta_dir / prefix / f"{sha256}.json"

    def write(
        self,
        content: bytes,
        source: str = "unknown",
        command: Optional[str] = None,
        evidence_class: EvidenceClass = EvidenceClass.UNKNOWN,
        mode: Mode = Mode.BUILD,
        session_id: Optional[str] = None,
        inline_required_facts: Optional[list] = None,
    ) -> RawRef:
        """
        Write content to the RAW store.

        Content-addressable: if content with this SHA-256 already exists,
        the existing entry is returned without re-writing (dedup).

        Atomic write protocol:
          1. Compute SHA-256
          2. Check existence (dedup)
          3. Write to .tmp file
          4. Rename to final path (atomic on same volume)
          5. Write metadata sidecar
          6. Append to index.jsonl

        Returns:
            RawRef with sha256 and store_path.
        """
        self._ensure_dirs()

        # Step 1: Compute SHA-256
        sha256 = hashlib.sha256(content).hexdigest()
        obj_path = self._object_path(sha256)
        meta_path = self._meta_path(sha256)

        # Step 2: Dedup — if already stored, return existing ref
        if obj_path.exists():
            return RawRef(sha256=sha256, store_path=str(obj_path))

        # Step 3–4: Atomic write (write to .tmp, rename)
        obj_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = obj_path.with_suffix(".tmp")
        try:
            tmp_path.write_bytes(content)
            tmp_path.rename(obj_path)  # atomic on same volume (I1)
        except Exception:
            # If rename fails, clean up temp file
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
            raise

        # Step 5: Write metadata sidecar
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta = RawMeta(
            raw_sha256=sha256,
            stored_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            source=source,
            command=command,
            evidence_class=evidence_class.value,
            mode=mode.value,
            byte_length=len(content),
            session_id=session_id,
            inline_required_facts=inline_required_facts or [],
        )
        meta_path.write_text(
            json.dumps(asdict(meta), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # Step 6: Append to index.jsonl
        index_record = {
            "sha256": sha256,
            "stored_at_utc": meta.stored_at_utc,
            "byte_length": len(content),
            "evidence_class": evidence_class.value,
            "source": source,
        }
        with open(self._index_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(index_record) + "\n")

        return RawRef(sha256=sha256, store_path=str(obj_path))

    def read(self, ref: RawRef, verify: bool = True) -> bytes:
        """
        Read content from the RAW store.

        Args:
            ref: RawRef to retrieve.
            verify: If True, verify SHA-256 after read (I3). Default: True.

        Returns:
            Content bytes — byte-exact (I3).

        Raises:
            FileNotFoundError: If the entry does not exist.
            ValueError: If SHA-256 verification fails (I3 violation).
        """
        obj_path = pathlib.Path(ref.store_path)
        if not obj_path.exists():
            # Try resolving by sha256 in case store_path is stale
            obj_path = self._object_path(ref.sha256)
        content = obj_path.read_bytes()

        if verify:
            actual_sha256 = hashlib.sha256(content).hexdigest()
            if actual_sha256 != ref.sha256:
                raise ValueError(
                    f"I3 VIOLATION: SHA-256 mismatch for {ref.sha256}. "
                    f"Expected {ref.sha256}, got {actual_sha256}. "
                    "RAW store entry may be corrupted."
                )

        return content

    def exists(self, sha256: str) -> bool:
        """Check if an entry with the given SHA-256 exists."""
        return self._object_path(sha256).exists()

    def read_meta(self, ref: RawRef) -> Optional[dict]:
        """Read metadata sidecar for a RAW store entry."""
        meta_path = self._meta_path(ref.sha256)
        if not meta_path.exists():
            return None
        return json.loads(meta_path.read_text(encoding="utf-8"))


# Module-level convenience instance using default location.
# Tests should use RawStore(root=tmp_path) to avoid polluting the real store.
_default_store: Optional[RawStore] = None


def get_default_store() -> RawStore:
    """Get or create the default RAW store instance."""
    global _default_store
    if _default_store is None:
        _default_store = RawStore()
    return _default_store
