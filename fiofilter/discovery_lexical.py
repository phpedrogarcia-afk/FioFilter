from __future__ import annotations

import math
import re
import string
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Set, Tuple


_STOPWORDS = frozenset([
    "a", "an", "the", "and", "or", "not", "is", "are", "was", "were",
    "be", "been", "being", "have", "has", "had", "do", "does", "did",
    "will", "would", "could", "should", "may", "might", "shall", "can",
    "this", "that", "these", "those", "for", "in", "on", "at", "to",
    "of", "with", "from", "by", "as", "it", "its", "if", "but", "so",
    "up", "out", "all", "no", "into", "than", "then", "over", "more",
    "also", "about", "any", "each", "which", "when", "what", "where",
    "how", "who", "use", "used", "using", "new", "get", "set", "add",
    "run", "via", "per", "see", "now", "fix",
])

_BM25_K1 = 1.2  # frozen V1 - DO NOT change without M10-D001 supersession
_BM25_B = 0.75  # frozen V1 - DO NOT change without M10-D001 supersession

# Separator: path separators, whitespace, punctuation, dots
_SEP_RE = re.compile(r'[\\/.\s,;:\'\"()\[\]{}<>=!|&^%$#@~`+\-*]+')


def _split_camel_case(text):
    """Split camelCase and PascalCase into lowercase tokens."""
    s = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', text)
    s = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', s)
    return [t.lower() for t in s.split('_') if t]


def _split_snake_case(text):
    """Split snake_case and SCREAMING_SNAKE into lowercase tokens."""
    return [t.lower() for t in text.split('_') if t]


def _chunk_to_tokens(chunk, seen=None, dedup=True):
    """Convert identifier chunk to token list with camel/snake normalization."""
    if '_' in chunk:
        parts = _split_snake_case(chunk)
        raw_toks = []
        for part in parts:
            raw_toks.extend(_split_camel_case(part))
    else:
        raw_toks = _split_camel_case(chunk)
    result = []
    for tok in raw_toks:
        tok = tok.strip()
        if len(tok) < 2 or tok in _STOPWORDS:
            continue
        if dedup and seen is not None:
            if tok in seen:
                continue
            seen.add(tok)
        result.append(tok)
    return result


def tokenize_v2(text):
    """
    Tokenization V2: normalize snake_case, camelCase, PascalCase into atomic
    lowercase tokens, deduplicated, stopwords filtered.

    Used for both query and code tokenization (parity).
    """
    if not text:
        return []
    raw_chunks = _SEP_RE.split(text)
    seen = set()
    tokens = []
    for chunk in raw_chunks:
        if not chunk:
            continue
        tokens.extend(_chunk_to_tokens(chunk, seen=seen, dedup=True))
    return tokens


def tokenize_v2_multiset(text):
    """
    Tokenization V2 multiset: token -> occurrence count.
    Used for BM25 TF calculation (repeated occurrences counted).
    """
    if not text:
        return {}
    raw_chunks = _SEP_RE.split(text)
    counts = {}
    for chunk in raw_chunks:
        if not chunk:
            continue
        for tok in _chunk_to_tokens(chunk, seen=None, dedup=False):
            counts[tok] = counts.get(tok, 0) + 1
    return counts


def _stem_simple(token):
    """Minimal suffix-stripping stem for legacy M09 mode."""
    for suffix in ("ing", "ion", "ed", "er", "ly", "tion", "ness", "ment"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: len(token) - len(suffix)]
    return token


def legacy_tokenize(text):
    """M09 legacy tokenizer: lowercase, word-boundary split, simple stem, filter."""
    if not text:
        return set()
    raw = re.split(r'[\W_]+', text.lower())
    result = set()
    for tok in raw:
        tok = tok.strip()
        if len(tok) < 3 or tok in _STOPWORDS:
            continue
        result.add(_stem_simple(tok))
    return result


class LexicalDocument:
    """A repository file as a document for lexical ranking."""
    __slots__ = ('path', 'tokens', 'token_counts', 'doc_length')

    def __init__(self, path, tokens, token_counts, doc_length):
        self.path = path
        self.tokens = tokens
        self.token_counts = token_counts
        self.doc_length = doc_length

    def __repr__(self):
        return f'LexicalDocument(path={self.path!r}, doc_length={self.doc_length})'


def build_document_from_path_and_symbols(path, symbol_names=None):
    """Build a LexicalDocument from a file path and optional symbol names."""
    text_parts = [path]
    if symbol_names:
        text_parts.extend(symbol_names)
    combined = ' '.join(text_parts)
    counts = tokenize_v2_multiset(combined)
    unique_tokens = list(counts.keys())
    doc_length = sum(counts.values())
    return LexicalDocument(
        path=path,
        tokens=unique_tokens,
        token_counts=counts,
        doc_length=doc_length,
    )


class BM25Index:
    """
    BM25 index over a collection of LexicalDocuments.

    IDF: Robertson-Sparck Jones variant.
    TF: length-normalized with k1=1.2, b=0.75 (frozen V1 weights).
    """

    def __init__(self, documents):
        self.documents = list(documents)
        self.idf = {}
        self.avg_doc_length = 0.0
        self._built = False

    def build(self):
        """Build IDF table and average document length."""
        n = len(self.documents)
        if n == 0:
            self._built = True
            return self
        df = {}
        total_length = 0
        for doc in self.documents:
            total_length += doc.doc_length
            for tok in set(doc.tokens):
                df[tok] = df.get(tok, 0) + 1
        self.avg_doc_length = total_length / n
        for tok, freq in df.items():
            self.idf[tok] = math.log((n - freq + 0.5) / (freq + 0.5) + 1.0)
        self._built = True
        return self

    def score(self, doc, query_tokens):
        """Compute BM25 score for a document. Uses frozen V1 weights."""
        if not self._built:
            raise RuntimeError('BM25Index.build() must be called before scoring.')
        if self.avg_doc_length == 0:
            return 0.0
        score = 0.0
        dl = doc.doc_length
        avdl = self.avg_doc_length
        for tok in query_tokens:
            tf = doc.token_counts.get(tok, 0)
            if tf == 0:
                continue
            idf = self.idf.get(tok, 0.0)
            numerator = tf * (_BM25_K1 + 1.0)
            denominator = tf + _BM25_K1 * (1.0 - _BM25_B + _BM25_B * dl / avdl)
            score += idf * numerator / denominator
        return score

    def rank(self, query_tokens, top_k=None):
        """Rank all documents by BM25 score. Returns [(path, score)] descending."""
        if not self._built:
            raise RuntimeError('BM25Index.build() must be called before ranking.')
        results = []
        for doc in self.documents:
            s = self.score(doc, query_tokens)
            if s > 0.0:
                results.append((doc.path, s))
        results.sort(key=lambda x: x[1], reverse=True)
        if top_k is not None:
            results = results[:top_k]
        return results


class LegacyLexicalScore:
    """Score result from legacy lexical ranker (M09 LEGACY_LEXICAL ablation mode)."""
    __slots__ = ('path', 'score', 'matched_tokens')

    def __init__(self, path, score, matched_tokens):
        self.path = path
        self.score = score
        self.matched_tokens = matched_tokens

    def __repr__(self):
        return f'LegacyLexicalScore(path={self.path!r}, score={self.score})'


def legacy_rank(query, file_paths, symbol_names_by_path=None, top_k=None):
    """
    Legacy lexical ranker (M09 mode, LEGACY_LEXICAL ablation baseline).

    Scores files by overlapping stems between query tokens and
    path + symbol name tokens. Preserved exactly from M09 for ablation parity.
    """
    query_tokens = legacy_tokenize(query)
    results = []
    for path in file_paths:
        doc_tokens = legacy_tokenize(path)
        if symbol_names_by_path and path in symbol_names_by_path:
            for sym in symbol_names_by_path[path]:
                doc_tokens |= legacy_tokenize(sym)
        matched = [t for t in query_tokens if t in doc_tokens]
        if matched:
            results.append(LegacyLexicalScore(
                path=path,
                score=float(len(matched)),
                matched_tokens=matched,
            ))
    results.sort(key=lambda x: x.score, reverse=True)
    if top_k is not None:
        results = results[:top_k]
    return results


def build_bm25_index_from_paths(file_paths, symbol_names_by_path=None):
    """Build a BM25Index from file paths and optional symbol name map."""
    docs = []
    for path in file_paths:
        symbols = symbol_names_by_path.get(path, []) if symbol_names_by_path else []
        doc = build_document_from_path_and_symbols(path, symbols)
        docs.append(doc)
    index = BM25Index(documents=docs)
    index.build()
    return index