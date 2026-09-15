"""
tests/test_machine_data.py — Machine data validity tests (I8, stub).

V0: T04 JSON minification is not implemented. Tests verify that
MACHINE_DATA content defaults to RAW (no transform applied in V0).

T04 remains DEFERRED. Parse equality alone is not consumer equivalence.
"""

import json
import pytest

from fiofilter.engine import process
from fiofilter.types import Disposition, EvidenceClass, Mode, ToolResult


class TestMachineDataV0RAWDefault:
    def test_valid_json_defaults_to_raw_in_v0(self, tmp_raw_store, tmp_metrics_log):
        """V0: JSON content → MACHINE_DATA → RAW (no lossless transforms yet)."""
        content = json.dumps({"key": "value", "count": 42}).encode("utf-8")
        tr = ToolResult(content=content, source="shell")
        result = process(tr, mode=Mode.BUILD, raw_store=tmp_raw_store,
                         metrics_log_path=tmp_metrics_log)
        # V0: MACHINE_DATA → RAW (T04 not implemented)
        assert result.evidence_class == EvidenceClass.MACHINE_DATA
        assert result.disposition in (Disposition.RAW, Disposition.ESCALATE_TO_RAW)

    def test_json_content_raw_is_byte_exact(self, tmp_raw_store, tmp_metrics_log):
        """When MACHINE_DATA is RAW, content == original bytes."""
        original = json.dumps({"important": "data"}).encode("utf-8")
        tr = ToolResult(content=original, source="shell")
        result = process(tr, mode=Mode.BUILD, raw_store=tmp_raw_store,
                         metrics_log_path=tmp_metrics_log)
        assert result.content == original

    def test_json_machine_data_recoverable(self, tmp_raw_store, tmp_metrics_log):
        """MACHINE_DATA content always recoverable from RAW store (I3)."""
        original = json.dumps({"list": [1, 2, 3]}).encode("utf-8")
        tr = ToolResult(content=original, source="shell")
        result = process(tr, raw_store=tmp_raw_store, metrics_log_path=tmp_metrics_log)
        recovered = tmp_raw_store.read(result.raw_ref, verify=True)
        assert recovered == original
