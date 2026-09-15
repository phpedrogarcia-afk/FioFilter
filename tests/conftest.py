"""
tests/conftest.py — Shared fixtures for FioFilter tests.
"""

import pathlib
import pytest
from fiofilter.raw_store import RawStore
from fiofilter.types import EvidenceClass, Mode, ToolResult


@pytest.fixture
def tmp_raw_store(tmp_path: pathlib.Path) -> RawStore:
    """A temporary RAW store isolated from the real default store."""
    return RawStore(root=tmp_path / "raw_store")


@pytest.fixture
def tmp_metrics_log(tmp_path: pathlib.Path) -> pathlib.Path:
    """A temporary metrics log path."""
    return tmp_path / "metrics.jsonl"


@pytest.fixture
def noise_tool_result() -> ToolResult:
    """A ToolResult with obvious noise content (duplicate lines)."""
    lines = ["Building... [   OK   ]\n"] * 20
    content = "".join(lines).encode("utf-8")
    return ToolResult(content=content, source="shell", command="make")


@pytest.fixture
def canonical_tool_result() -> ToolResult:
    """A ToolResult with canonical Git evidence."""
    content = (
        "commit abc1234def5678\n"
        "Author: Dev <dev@example.com>\n"
        "Date:   Mon Sep 15 12:00:00 2026\n\n"
        "    Fix bug\n\n"
        "On branch main\n"
        "nothing to commit, working tree clean\n"
    ).encode("utf-8")
    return ToolResult(content=content, source="shell", command="git log --oneline")


@pytest.fixture
def failure_tool_result() -> ToolResult:
    """A ToolResult with a failure (non-zero exit code)."""
    content = b"Traceback (most recent call last):\n  File 'foo.py', line 1\nAssertionError\n"
    return ToolResult(content=content, source="shell", command="python test.py", exit_code=1)


@pytest.fixture
def unknown_tool_result() -> ToolResult:
    """A ToolResult with completely unclassifiable content."""
    content = b"xyzzy frobnicator quux\nplugh\n"
    return ToolResult(content=content, source="shell")


@pytest.fixture
def authority_content() -> bytes:
    """Content that triggers AUTHORITY classification."""
    return b"IAM policy granted to arn:aws:iam::123456789012:role/MyRole\nPermission granted\n"


@pytest.fixture
def security_content() -> bytes:
    """Content that triggers SECURITY classification."""
    return b"-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----\n"
