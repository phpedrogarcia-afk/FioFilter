"""Unit tests for the M05 Context Waste Census engine."""

import json
import pathlib
import pytest

from fiofilter.context_census import (
    CensusEvent,
    ContextWasteCensus,
    classify_tool_call,
    decode_tool_output,
)


def _make_call_payload(cmd: str, name: str = "exec") -> dict:
    return {
        "type": "custom_tool_call",
        "name": name,
        "input": {"cmd": cmd},
    }


def _make_session_line(payload: dict, ts: str = "2026-09-16T12:00:00Z") -> str:
    return json.dumps({"timestamp": ts, "payload": payload}) + "\n"


class TestToolCallClassification:
    def test_search_classification(self):
        payload = _make_call_payload("rg -n 'def test' tests/ -g '*.py'")
        fam, cmd, path, lr, is_mut, op = classify_tool_call(payload)
        assert fam == "SEARCH"
        assert op == "search"
        assert is_mut is False

    def test_file_read_get_content(self):
        payload = _make_call_payload(
            "$x=Get-Content -LiteralPath 'fio/core/gateway.py'; $x[45..100]"
        )
        fam, cmd, path, lr, is_mut, op = classify_tool_call(payload)
        assert fam == "FILE_READ"
        assert path == "fio\\core\\gateway.py"
        assert lr == (45, 100)
        assert is_mut is False

    def test_file_read_select_object(self):
        payload = _make_call_payload(
            "Get-Content -LiteralPath 'src/app.py' | Select-Object -Skip 10 -First 20"
        )
        fam, cmd, path, lr, is_mut, op = classify_tool_call(payload)
        assert fam == "FILE_READ"
        assert path == "src\\app.py"
        assert lr == (10, 30)

    def test_file_write_powershell(self):
        payload = _make_call_payload(
            "$code=@'hello'@; [System.IO.File]::WriteAllText('app.py', $code)"
        )
        fam, cmd, path, lr, is_mut, op = classify_tool_call(payload)
        assert fam == "WRITE_OR_EDIT"
        assert is_mut is True
        assert op == "write"

    def test_test_command(self):
        payload = _make_call_payload("python -m pytest tests/ -v")
        fam, cmd, path, lr, is_mut, op = classify_tool_call(payload)
        assert fam == "TEST"
        assert op == "test"

    def test_directory_list(self):
        payload = _make_call_payload("Get-ChildItem -Path 'src/'")
        fam, cmd, path, lr, is_mut, op = classify_tool_call(payload)
        assert fam == "DIRECTORY_LIST"

    def test_git_status(self):
        payload = _make_call_payload("git status --short")
        fam, cmd, path, lr, is_mut, op = classify_tool_call(payload)
        assert fam == "GIT"
        assert is_mut is False

    def test_unknown_producer_or_script(self):
        payload = {"type": "custom_tool_call", "name": "exec", "input": "const a = 1;"}
        fam, cmd, path, lr, is_mut, op = classify_tool_call(payload)
        assert fam in ("SCRIPT", "UNKNOWN")


class TestCensusSyntheticScenarios:
    def test_synthetic_reexposure_and_discovery(self, tmp_path):
        lines = []
        # Turn 1
        lines.append(
            _make_session_line({"type": "message", "role": "user", "id": "u1"})
        )
        # Search 1
        lines.append(
            _make_session_line(
                {
                    "type": "custom_tool_call",
                    "call_id": "c1",
                    "name": "exec",
                    "input": {"cmd": "rg -n target src"},
                }
            )
        )
        lines.append(
            _make_session_line(
                {
                    "type": "custom_tool_call_output",
                    "call_id": "c1",
                    "output": [{"text": "Script completed"}, {"text": "src/a.py:1:target\n"}],
                }
            )
        )
        # Search 1 duplicate
        lines.append(
            _make_session_line(
                {
                    "type": "custom_tool_call",
                    "call_id": "c2",
                    "name": "exec",
                    "input": {"cmd": "rg -n target src"},
                }
            )
        )
        lines.append(
            _make_session_line(
                {
                    "type": "custom_tool_call_output",
                    "call_id": "c2",
                    "output": [{"text": "Script completed"}, {"text": "src/a.py:1:target\n"}],
                }
            )
        )
        # Read 1
        lines.append(
            _make_session_line(
                {
                    "type": "custom_tool_call",
                    "call_id": "c3",
                    "name": "exec",
                    "input": {"cmd": "Get-Content -LiteralPath 'src/a.py'"},
                }
            )
        )
        lines.append(
            _make_session_line(
                {
                    "type": "custom_tool_call_output",
                    "call_id": "c3",
                    "output": [{"text": "Script completed"}, {"text": "line1\nline2\n"}],
                }
            )
        )
        # Write 1 (onset of mutation)
        lines.append(
            _make_session_line(
                {
                    "type": "custom_tool_call",
                    "call_id": "c4",
                    "name": "exec",
                    "input": {"cmd": "Set-Content -Path 'src/a.py' -Value 'line1\n'"},
                }
            )
        )
        lines.append(
            _make_session_line(
                {
                    "type": "custom_tool_call_output",
                    "call_id": "c4",
                    "output": [{"text": "Script completed"}, {"text": ""}],
                }
            )
        )

        session_file = tmp_path / "synthetic_session.jsonl"
        session_file.write_text("".join(lines), encoding="utf-8")

        analyzer = ContextWasteCensus(session_file)
        summary = analyzer.analyze()

        assert summary["denominator"]["total_tool_calls"] == 4
        assert summary["discovery_cost"]["total_episodes"] == 1
        assert summary["reexposure_waste"]["proven_reexposure_bytes"] > 0
        assert summary["discovery_cost"]["duplicate_search_calls"] == 1
        assert summary["deduplication"]["double_counting_prevented"] is True
