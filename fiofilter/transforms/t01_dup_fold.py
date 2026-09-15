"""T01 v2 mechanical encoding. Engine eligibility is NOISE/PROGRESS only.

Literal reserved markers reject transformation. Consecutive byte-identical
LF/CRLF lines fold to one unchanged source line followed by a distinct marker.
Count includes the first line. First/last are 1-based original line positions.
Decoded visible bytes must equal RAW; RAW store recovery is a separate oracle.
"""
import re
from typing import Optional
from fiofilter.transforms.base import Transform

FOLD_THRESHOLD = 2
RESERVED = b'[[FIOFILTER:'
_HEADER = b'[[FIOFILTER:T01:v2]]\n'
_MARKER = re.compile(rb'\[\[FIOFILTER:T01 count=([1-9][0-9]*) first=([1-9][0-9]*) last=([1-9][0-9]*)\]\]\n')


def _lines(content):
    # Split only LF; unlike str.splitlines, NEL/U+2028 are literal source text.
    return content.splitlines(keepends=True)


class DuplicateLineFold(Transform):
    @property
    def transform_id(self):
        return 'T01'

    @property
    def description(self):
        return 'Exact consecutive-line folding with versioned count and boundaries'

    def apply(self, content: bytes) -> Optional[bytes]:
        try:
            text = content.decode('utf-8')
        except (UnicodeError, AttributeError):
            return None
        if (RESERVED in content or b'\x00' in content
                or any(ord(c) < 32 and c not in '\t\n\r' for c in text)
                or b'\r' in content.replace(b'\r\n', b'')):
            return None
        lines = _lines(content)
        output = [_HEADER]
        folded = False
        i = 0
        while i < len(lines):
            j = i + 1
            while j < len(lines) and lines[j] == lines[i]:
                j += 1
            count = j - i
            output.append(lines[i])
            if count >= FOLD_THRESHOLD:
                output.append(f'[[FIOFILTER:T01 count={count} first={i+1} last={j}]]\n'.encode())
                folded = True
            i = j
        result = b''.join(output)
        if not folded or len(result) >= len(content):
            return None
        return result


def decode_visible(content: bytes, max_output_bytes: int = 16 * 1024 * 1024) -> bytes:
    """Strict, bounded decoder. Does not read the RAW store.

    Engine supplies the original byte length as bound; standalone callers may
    override the default explicitly for larger known data.
    """
    if not content.startswith(_HEADER):
        raise ValueError('Missing T01 v2 header')
    out = []
    size = 0
    line_number = 0
    previous = None
    for line in _lines(content[len(_HEADER):]):
        if RESERVED in line:
            match = _MARKER.fullmatch(line)
            if not match or previous is None:
                raise ValueError('Invalid or ambiguous T01 marker')
            count, first, last = map(int, match.groups())
            if count < 2 or first != line_number or last != first + count - 1:
                raise ValueError('Invalid T01 count/boundaries')
            extra = len(previous) * (count - 1)
            if size + extra > max_output_bytes:
                raise ValueError('T01 recovery bound exceeded')
            out.append(previous * (count - 1))
            size += extra
            line_number = last
            previous = None
        else:
            size += len(line)
            if size > max_output_bytes:
                raise ValueError('T01 recovery bound exceeded')
            out.append(line)
            line_number += 1
            previous = line
    return b''.join(out)
