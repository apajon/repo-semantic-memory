"""Deterministic BM25 field-weighted lexical scoring utilities."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/:-]*")
_DELIMITER_PATTERN = re.compile(r"[._/:\-\\]+")
_CAMEL_PATTERN = re.compile(r"[A-Z]+(?=[A-Z][a-z]|\d|$)|[A-Z]?[a-z]+|\d+")

DEFAULT_FIELD_WEIGHTS: Mapping[str, float] = MappingProxyType(
    {
        "qualified_name": 3.0,
        "name": 2.5,
        "source_path": 2.0,
        "kind": 1.5,
        "semantic_components": 1.25,
        "relation_labels": 1.0,
        "metadata": 0.75,
        "id": 0.5,
    }
)


@dataclass(frozen=True)
class BM25Config:
    """Configurable BM25 constants and field weights."""

    k1: float = 1.2
    b: float = 0.75
    field_weights: Mapping[str, float] = field(default_factory=lambda: dict(DEFAULT_FIELD_WEIGHTS))

    def __post_init__(self) -> None:
        if self.k1 <= 0:
            raise ValueError("k1 must be > 0")
        if not 0 <= self.b <= 1:
            raise ValueError("b must be between 0 and 1")
        if not self.field_weights:
            raise ValueError("field_weights must not be empty")
        for field_name, weight in self.field_weights.items():
            if not field_name:
                raise ValueError("field_weights keys must be non-empty")
            if weight <= 0:
                raise ValueError("field_weights values must be > 0")


@dataclass(frozen=True)
class FieldedDocument:
    """Entity-like lexical document composed from weighted fields."""

    doc_id: str
    fields: Mapping[str, str]


@dataclass(frozen=True)
class BM25Score:
    """BM25 score payload with explainability helpers."""

    score: float
    matched_terms: tuple[str, ...]
    matched_fields: tuple[str, ...]


class FieldedBM25Index:
    """Deterministic BM25 index over fielded documents."""

    def __init__(
        self,
        documents: Sequence[FieldedDocument],
        *,
        config: BM25Config | None = None,
    ) -> None:
        self._config = config or BM25Config()
        self._field_order = tuple(self._config.field_weights.keys())
        self._documents = tuple(sorted(documents, key=lambda item: item.doc_id))
        self._document_ids = tuple(document.doc_id for document in self._documents)
        self._document_set = set(self._document_ids)
        self._doc_count = len(self._documents)

        self._field_term_freqs: dict[tuple[str, str], Counter[str]] = {}
        self._field_lengths: dict[tuple[str, str], int] = {}
        self._avg_field_length: dict[str, float] = {}
        self._doc_frequency: dict[tuple[str, str], int] = {}

        for field_name in self._field_order:
            total_length = 0
            for document in self._documents:
                field_text = document.fields.get(field_name, "")
                tokens = tokenize_text(field_text)
                term_freqs = Counter(tokens)
                key = (document.doc_id, field_name)
                self._field_term_freqs[key] = term_freqs
                length = len(tokens)
                self._field_lengths[key] = length
                total_length += length

                for token in term_freqs:
                    df_key = (field_name, token)
                    self._doc_frequency[df_key] = self._doc_frequency.get(df_key, 0) + 1

            if self._doc_count > 0:
                self._avg_field_length[field_name] = total_length / self._doc_count
            else:
                self._avg_field_length[field_name] = 0.0

    @property
    def config(self) -> BM25Config:
        return self._config

    def score(self, doc_id: str, query_tokens: Sequence[str]) -> BM25Score:
        if doc_id not in self._document_set:
            raise KeyError(f"Unknown doc_id: {doc_id}")
        if self._doc_count == 0:
            return BM25Score(score=0.0, matched_terms=(), matched_fields=())

        normalized_terms = tuple(dict.fromkeys(token.lower() for token in query_tokens if token))
        if not normalized_terms:
            return BM25Score(score=0.0, matched_terms=(), matched_fields=())

        total_score = 0.0
        matched_terms: list[str] = []
        matched_fields: list[str] = []

        for term in normalized_terms:
            term_matched = False
            for field_name in self._field_order:
                tf = self._field_term_freqs[(doc_id, field_name)].get(term, 0)
                if tf <= 0:
                    continue
                term_matched = True
                matched_fields.append(field_name)

                df = self._doc_frequency[(field_name, term)]
                idf = math.log1p((self._doc_count - df + 0.5) / (df + 0.5))
                avg_length = self._avg_field_length[field_name]
                field_length = self._field_lengths[(doc_id, field_name)]
                if avg_length <= 0:
                    normalized_tf = float(tf)
                else:
                    normalized_tf = (tf * (self._config.k1 + 1.0)) / (
                        tf
                        + self._config.k1
                        * (1.0 - self._config.b + self._config.b * (field_length / avg_length))
                    )
                total_score += self._config.field_weights[field_name] * idf * normalized_tf
            if term_matched:
                matched_terms.append(term)

        return BM25Score(
            score=total_score,
            matched_terms=tuple(dict.fromkeys(matched_terms)),
            matched_fields=tuple(dict.fromkeys(matched_fields)),
        )


def tokenize_text(text: str) -> tuple[str, ...]:
    """Tokenize deterministically with identifier/path aware splitting."""
    ordered: dict[str, None] = {}
    for raw_token in _TOKEN_PATTERN.findall(text):
        _append_token(ordered, raw_token.lower())
        for segment in _DELIMITER_PATTERN.split(raw_token):
            if not segment:
                continue
            _append_token(ordered, segment.lower())
            for piece in _CAMEL_PATTERN.findall(segment):
                _append_token(ordered, piece.lower())
    return tuple(ordered.keys())


def _append_token(tokens: dict[str, None], token: str) -> None:
    if token:
        tokens.setdefault(token, None)
