"""Explicit local content-addressed storage, plus reference-owned ephemeral recovery.

Blobs and content-only metadata use unique same-directory temporary files and
atomic no-clobber hard-link publication. No index and no per-command sidecars.
A missing sidecar does not invalidate byte recovery; malformed metadata is an
explicit error. This is integrity checking, not protection against a hostile OS.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Optional

from fiofilter.sensitivity import contains_sensitive_material
from fiofilter.types import EvidenceClass, Mode, RawRef


class RawStore:
    def __init__(self, root: Optional[Path] = None):
        selected = root if root is not None else os.environ.get('FIOFILTER_RAW_STORE')
        self.root = (Path(selected) if selected else Path.home() / '.fiofilter' / 'raw').absolute()
        self._objects_dir = self.root / 'objects'
        self._meta_dir = self.root / 'meta'

    @staticmethod
    def _validate_sha(sha):
        if not isinstance(sha, str) or re.fullmatch('[0-9a-f]{64}', sha) is None:
            raise ValueError('Invalid SHA-256 address')

    def _object_path(self, sha):
        self._validate_sha(sha)
        return self._objects_dir / sha[:2] / sha

    def _meta_path(self, sha):
        self._validate_sha(sha)
        return self._meta_dir / sha[:2] / (sha + '.json')

    @staticmethod
    def ephemeral(content: bytes) -> RawRef:
        if not isinstance(content, bytes):
            raise TypeError('RAW content must be bytes')
        return RawRef(hashlib.sha256(content).hexdigest(), '', content)

    @staticmethod
    def _publish(path: Path, content: bytes):
        """No overwrite on POSIX or Windows/NTFS; unsupported FS raises safely.

        fsync flushes the temporary file. No claim of power-loss durability of
        directory entries. A killed process may leave a private temporary file.
        """
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, temporary = tempfile.mkstemp(prefix='.raw-', dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                pass  # The caller verifies the existing object before success.
        finally:
            Path(temporary).unlink(missing_ok=True)

    def write(self, content: bytes, source='unknown', command=None,
              evidence_class=EvidenceClass.UNKNOWN, mode=Mode.BUILD,
              session_id=None, inline_required_facts=None) -> RawRef:
        """Explicit disk-write API for caller-assessed non-sensitive input.

        Calling this low-level API is storage consent. Prefer engine.process,
        which defaults to EPHEMERAL. Legacy context arguments are checked but
        never persisted: identical bytes do not imply identical event context.
        Detection is a backstop, not a universal secret/PII detector.
        """
        if not isinstance(content, bytes):
            raise TypeError('RAW content must be bytes')
        context = '\n'.join(str(v) for v in (source, command, session_id, inline_required_facts) if v is not None).encode()
        if contains_sensitive_material(content) or contains_sensitive_material(context):
            raise ValueError('Sensitive material: disk persistence denied')
        sha = hashlib.sha256(content).hexdigest()
        path = self._object_path(sha)
        ref = RawRef(sha, str(path))
        if not path.exists():
            self._publish(path, content)
        recovered = self.read(ref)  # Verify even on dedup; never repair corrupt blobs.
        metadata = {'schema': 2, 'raw_sha256': sha, 'byte_length': len(recovered)}
        meta_path = self._meta_path(sha)
        if not meta_path.exists():
            self._publish(meta_path, json.dumps(metadata, sort_keys=True).encode())
        if self.read_meta(ref) != metadata:
            raise ValueError('Metadata inconsistent with content')
        return ref

    def read(self, ref: RawRef, verify: bool = True) -> bytes:
        """Byte-exact recovery; unchecked reads are deliberately unsupported."""
        if verify is not True:
            raise ValueError('SHA-256 verification cannot be disabled')
        self._validate_sha(ref.sha256)
        if ref.ephemeral_content is not None:
            content = ref.ephemeral_content
        else:
            path = self._object_path(ref.sha256)  # Never follow a caller-supplied path.
            if path.is_symlink():
                raise ValueError('Symlink RAW object rejected')
            content = path.read_bytes()
        if not isinstance(content, bytes) or hashlib.sha256(content).hexdigest() != ref.sha256:
            raise ValueError('RAW blob SHA-256 mismatch')
        return content

    def exists(self, sha256: str) -> bool:
        """Presence only; read() is the integrity oracle."""
        return self._object_path(sha256).exists()

    def read_meta(self, ref: RawRef):
        content = self.read(ref)
        if ref.ephemeral_content is not None:
            return None
        path = self._meta_path(ref.sha256)
        if path.is_symlink():
            raise ValueError('Symlink RAW metadata rejected')
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (ValueError, UnicodeError) as exc:
            raise ValueError('Corrupt RAW metadata') from exc
        expected = {'schema': 2, 'raw_sha256': ref.sha256, 'byte_length': len(content)}
        if (data != expected or type(data.get('schema')) is not int
                or type(data.get('byte_length')) is not int):
            raise ValueError('RAW metadata mismatch or unsupported legacy schema')
        return data


def get_default_store() -> RawStore:
    """Lazy handle only; construction/import never creates directories."""
    return RawStore()


def _get_root() -> Path:
    """Compatibility helper; still no filesystem writes."""
    return RawStore().root
