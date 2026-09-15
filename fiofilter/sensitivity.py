"""Storage safety is orthogonal to evidence class (M02-D001).

Detection is a backstop, never proof that arbitrary data is non-sensitive.
Default engine recovery is ephemeral. Disk storage requires caller assessment.
"""
import re
import unicodedata

# Inspect both original and display-normalized text; never change evidence bytes.
_ANSI = re.compile(r'\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\))')
_SECRET = re.compile(
    r'BEGIN\s+(?:(?:RSA|EC|DSA|OPENSSH|ENCRYPTED)\s+)?PRIVATE\s+KEY'
    r'|\b(?:bearer|basic)\s+\S+'
    r'|\b(?:gh[pousr]_|github_pat_|sk-)[A-Za-z0-9_-]{8,}'
    r'|\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'
    r'|\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+'
    r'|\b(?:api[_-]?key|access[_-]?key|secret(?:[_-]?access[_-]?key)?'
    r'|AWS_SECRET_ACCESS_KEY|password|passwd|credential|token|authorization'
    r'|cookie|set-cookie|client[_-]?secret|private[_-]?key)\b[\s\"\']*[:=]'
    r'|://[^\s/:]+:[^\s/@]+@', re.IGNORECASE)


def scan_text(content: bytes) -> str:
    text = content.decode('utf-8', errors='replace')
    return unicodedata.normalize('NFKC', _ANSI.sub('', text))


def contains_sensitive_material(content: bytes) -> bool:
    return bool(_SECRET.search(scan_text(content)))
