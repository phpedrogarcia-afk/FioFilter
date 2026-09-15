"""Full-input deterministic evidence signals, with bounded low-risk eligibility.

A matching line is not proof that the remainder is noise. Only a complete
allowlisted noise/progress grammar can authorize T01. No prefix sampling.
"""
from dataclasses import dataclass, field
import json
import re
from typing import List, Optional

from fiofilter.sensitivity import contains_sensitive_material, scan_text
from fiofilter.types import EvidenceClass as EC

MIN_CONFIDENCE = 0.6


@dataclass
class ClassifyResult:
    evidence_class: EC
    confidence: float
    inline_required_facts: List[str] = field(default_factory=list)
    classifier_notes: str = ''


_FAILURE = re.compile(r'\b(?:error|fatal|fail(?:ed|ure)?|failures|exception|panic|crash(?:ed)?|AssertionError)\b|Traceback \(most recent call last', re.I)
_WARNING = re.compile(r'\b(?:warn(?:ing)?|deprecated|DeprecationWarning|truncat(?:ed|ion)|incomplete)\b', re.I)
_AUTHORITY = re.compile(r'\bIAM\b.*\bpolicy\b|\bpermissions?\s+(?:denied|granted)\b|\bsigned\s+by\b|\baudit\s+log\b', re.I)
_SECURITY = re.compile(r'\b(?:CVE-\d{4}-\d+|vulnerabilit\w*|security\s+(?:finding|policy|scan)|adversarial\s+test)\b|BEGIN\s+(?:PUBLIC|CERTIFICATE)', re.I)
_CANONICAL = re.compile(r'^commit [0-9a-f]{7,40}|^On branch \S+|^HEAD detached|^nothing to commit|\bSHA-?(?:256|1)\s*[:=]\s*[0-9a-f]{40,64}\b', re.M | re.I)
_BENCHMARK = re.compile(r'\bbenchmark\b|\b\d+\.\d+\s*ms\b.*\b(?:mean|median|p50|p95|p99)\b', re.I)
_SUCCESS = re.compile(r'\b\d+\s+passed\b|\ball\s+tests?\s+pass(?:ed)?\b|\bOK\s*\(\s*\d+\s+test|^\d+ tests?, 0 failures?$', re.M | re.I)
_DISCOVERY = re.compile(r'^(?:total\s+\d+|drwx|lrwx|-rw)|^\s*(?:├──|└──|│)|\bDirectory of\b', re.M | re.I)
# Deliberately finite V0 grammar, not arbitrary repeated sentences or log prefixes.
_NOISE_LINE = re.compile(r'(?:Building\.\.\.\s*\[\s*OK\s*\]|[.]{1,80}|\[#+ *\])')
_PROGRESS_LINE = re.compile(r'(?:Downloading\s+(?:100|[1-9]?\d)%|(?:100|[1-9]?\d)%\|[ #=|.> -]*)', re.I)


def _is_binary(data: bytes) -> bool:
    if b'\x00' in data:
        return True
    try:
        data.decode('utf-8')
    except UnicodeDecodeError:
        return True
    return False


def classify(tool_result_content: bytes, exit_code: Optional[int] = None) -> ClassifyResult:
    def result(cls, note, facts=None):
        return ClassifyResult(cls, 1.0, facts or [], note)

    if exit_code is not None and exit_code != 0:
        return result(EC.FAILURE, 'Non-zero exit')
    if not tool_result_content:
        return result(EC.UNKNOWN, 'Empty input')
    text = scan_text(tool_result_content)
    if contains_sensitive_material(tool_result_content):
        return result(EC.SECURITY, 'Sensitive material signal; storage policy is separate')
    # A zero failure count is not itself failure evidence. Other errors still win.
    failure_text = re.sub(r'\b0\s+(?:failures?|failed|errors?)\b', '', text, flags=re.I)
    if _FAILURE.search(failure_text):
        return result(EC.FAILURE, 'Failure evidence anywhere in input')
    if _SECURITY.search(text):
        return result(EC.SECURITY, 'Security evidence')
    if _AUTHORITY.search(text):
        return result(EC.AUTHORITY, 'Authority evidence')
    if _WARNING.search(text):
        return result(EC.DIAGNOSTIC, 'Diagnostic evidence anywhere in input')
    if _CANONICAL.search(text):
        facts = re.findall(r'^(?:commit [0-9a-f]{7,40}|On branch \S+)', text, re.M)
        return result(EC.CANONICAL_STATE, 'Canonical evidence', facts)
    if _BENCHMARK.search(text):
        return result(EC.BENCHMARK, 'Measurement evidence')
    if _is_binary(tool_result_content):
        return result(EC.MACHINE_DATA, 'Invalid UTF-8 or NUL bytes')
    stripped = text.strip()
    if stripped.startswith(('{', '[')):
        try:
            json.loads(stripped)
            return result(EC.MACHINE_DATA, 'Structured JSON')
        except (ValueError, RecursionError):
            # Malformed structured input cannot acquire noise eligibility.
            if not all(_NOISE_LINE.fullmatch(line) for line in text.splitlines() if line):
                return result(EC.UNKNOWN, 'Malformed structured candidate')
    if _SUCCESS.search(text):
        return result(EC.SUCCESS_SUMMARY, 'Success signal, no diagnostic signal')
    if _DISCOVERY.search(text):
        return result(EC.DISCOVERY, 'Discovery signal, no protected signal')
    # Terminal controls are inspected for danger above, never normalized in a transform.
    if any(ord(c) < 32 and c not in '\r\n\t' for c in text) or b'\x1b' in tool_result_content:
        return result(EC.UNKNOWN, 'Terminal/control representation')
    lines = text.splitlines()
    if lines and all(_NOISE_LINE.fullmatch(line) for line in lines):
        return result(EC.NOISE, 'Complete known boilerplate grammar')
    if lines and all(_NOISE_LINE.fullmatch(line) or _PROGRESS_LINE.fullmatch(line) for line in lines):
        return result(EC.PROGRESS, 'Complete known progress grammar')
    return result(EC.UNKNOWN, 'No complete safe reduction grammar')
