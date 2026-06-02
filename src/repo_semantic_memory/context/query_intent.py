"""Deterministic query intent parser for context-pack ranking.

Classifies what a natural-language task is asking for and separates generic
phrase tokens (that should not contribute to BM25 lexical scoring) from
meaningful domain tokens.

This is the Ranking v2 Step 1 (Prompt 58.1) implementation.
No NLP models are used; all classification is deterministic pure-Python logic.
"""

from __future__ import annotations

from dataclasses import dataclass

from repo_semantic_memory.context.bm25 import tokenize_text

# ---------------------------------------------------------------------------
# Intent token sets
# ---------------------------------------------------------------------------

_TESTS_TOKENS: frozenset[str] = frozenset(
    {"test", "tests", "coverage", "regression", "pytest", "spec", "specs"}
)
_PUBLIC_API_TOKENS: frozenset[str] = frozenset(
    {"public", "api", "export", "exports", "__init__", "init", "interface", "interfaces"}
)
_IMPLEMENTATION_TOKENS: frozenset[str] = frozenset(
    {
        "implementation",
        "implemented",
        "implements",
        "logic",
        "source",
        "core",
        "ownership",
        "cleanup",
        "refactor",
        "fix",
        "bug",
    }
)
_CONFIG_BUILD_TOKENS: frozenset[str] = frozenset(
    {
        "config",
        "configuration",
        "pyproject",
        "setup",
        "build",
        "release",
        "packaging",
        "ci",
        "workflow",
    }
)
_ERROR_HANDLING_TOKENS: frozenset[str] = frozenset(
    {
        "error",
        "errors",
        "exception",
        "exceptions",
        "raise",
        "raises",
        "failure",
        "failures",
        "handling",
    }
)
_ARCHITECTURE_FLOW_TOKENS: frozenset[str] = frozenset(
    {
        "flow",
        "dispatch",
        "pipeline",
        "routing",
        "lifecycle",
        "architecture",
        "request",
        "response",
        "middleware",
    }
)

# ---------------------------------------------------------------------------
# Generic phrase / token stop-set
# ---------------------------------------------------------------------------
# Tokens that are generic task-phrasing words and must NOT contribute positive
# lexical mass to BM25 source_path / name scoring.  They are removed from the
# lexical query while still being available for intent detection.
#
# The stop-set is an explicit allowlist-guarded set: only words that are
# clearly task-phrasing function words or fully generic nouns belong here.
# Domain tokens (loader, resolve, handler, …) are never added to this set.

_GENERIC_STOP_TOKENS: frozenset[str] = frozenset(
    {
        # Task-phrasing verbs / interrogatives
        "find",
        "how",
        "where",
        "show",
        "list",
        "get",
        "give",
        "check",
        "look",
        # Generic nouns that collide with real file/path tokens
        "files",
        "file",
        "code",
        "work",
        "works",
        "behavior",
        "including",
        "relevant",
        # Function words
        "the",
        "a",
        "an",
        "of",
        "to",
        "in",
        "for",
        "with",
        "and",
        "or",
        "at",
        "on",
        "by",
        "from",
        "that",
        "this",
        "it",
        "its",
        "is",
        "are",
        "be",
        "which",
        "what",
        "when",
        "all",
        "any",
    }
)

# Tokens in the generic stop-set that ALSO appear in intent token sets are
# handled as follows: they still contribute to intent detection (via the raw
# tokenized task text) but are stripped from lexical_tokens so they cannot
# boost a file literally named `test`, `files`, etc.
#
# "test" / "tests" are deliberately NOT in _GENERIC_STOP_TOKENS — they are
# domain-meaningful (test files) — but their intent role is handled via the
# `tests` intent rather than as a raw lexical term that would boost runtime
# paths named "test".  See _build_lexical_tokens for the special handling.

# Tokens that are meaningful intent signals but should be downweighted in
# lexical scoring to avoid boosting unrelated runtime paths.
# "test"/"tests" match runtime dirs like lib/ansible/plugins/test/*; routing them
# through the intent model rather than raw BM25 reduces this false-positive.
_INTENT_ONLY_TOKENS: frozenset[str] = frozenset(
    {
        "test",
        "tests",
        "behavior",  # also generic-ish; covered in _GENERIC_STOP_TOKENS as well
        "implementation",  # covered in intent but also noisy for path matching
    }
)

# ---------------------------------------------------------------------------
# Domain-token allowlist (never stripped, for documentation / audit)
# ---------------------------------------------------------------------------
# These tokens are explicitly meaningful domain terms.  They are listed here
# only as documentation; the filtering logic never removes them because they
# are absent from _GENERIC_STOP_TOKENS and _INTENT_ONLY_TOKENS.
_DOMAIN_TOKEN_ALLOWLIST: frozenset[str] = frozenset(
    {
        "loader",
        "resolve",
        "resolver",
        "handler",
        "dispatch",
        "router",
        "route",
        "url",
        "pattern",
        "plugin",
        "command",
        "callback",
        "timeout",
        "transport",
        "middleware",
    }
)


# ---------------------------------------------------------------------------
# Public dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QueryIntent:
    """Deterministic query intent classification result.

    Attributes:
        intents: Set of detected intent labels for this task.  Possible values:
            ``tests``, ``public_api``, ``implementation``, ``config_build_release``,
            ``error_handling``, ``architecture_flow``.
        domain_tokens: Meaningful tokens extracted after removing generic phrases.
            These are used for intent detection and could also be used for logging.
        downweighted_tokens: Generic tokens that were removed from lexical scoring.
        lexical_tokens: Filtered tokens suitable for BM25 entity scoring.
            Generic task-phrasing words and intent-only tokens are excluded so
            they do not boost unrelated files via ``source_path`` field matching.
    """

    intents: frozenset[str]
    domain_tokens: tuple[str, ...]
    downweighted_tokens: tuple[str, ...]
    lexical_tokens: tuple[str, ...]


# ---------------------------------------------------------------------------
# Public parser
# ---------------------------------------------------------------------------


def parse_query_intent(task: str) -> QueryIntent:
    """Parse a task description into a deterministic :class:`QueryIntent`.

    Tokenization reuses :func:`~repo_semantic_memory.context.bm25.tokenize_text`
    for consistency with the existing BM25 index.  All classification is purely
    deterministic; no NLP models are used.

    Args:
        task: Natural-language task description (e.g. ``"Find how URL resolver
            implementation files work"``).

    Returns:
        A :class:`QueryIntent` with intents, domain tokens, downweighted tokens,
        and a ``lexical_tokens`` tuple ready for BM25 scoring.
    """
    raw_tokens = tokenize_text(task)
    intents = _detect_intents(raw_tokens)
    lexical_tokens, downweighted = _build_lexical_tokens(raw_tokens)
    domain_tokens = tuple(t for t in raw_tokens if t not in downweighted)
    return QueryIntent(
        intents=intents,
        domain_tokens=domain_tokens,
        downweighted_tokens=downweighted,
        lexical_tokens=lexical_tokens,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _detect_intents(tokens: tuple[str, ...]) -> frozenset[str]:
    """Detect active intents from the full (unfiltered) token set."""
    token_set = frozenset(tokens)
    intents: set[str] = set()

    if token_set & _TESTS_TOKENS:
        intents.add("tests")
    if token_set & _PUBLIC_API_TOKENS:
        intents.add("public_api")
    # "implementation" intent: from implementation tokens OR the co-occurrence
    # of "core" + "logic" (matches existing _IMPLEMENTATION_CORE_LOGIC_TOKENS).
    if token_set & _IMPLEMENTATION_TOKENS or ("core" in token_set and "logic" in token_set):
        intents.add("implementation")
    if token_set & _CONFIG_BUILD_TOKENS:
        intents.add("config_build_release")
    if token_set & _ERROR_HANDLING_TOKENS:
        intents.add("error_handling")
    if token_set & _ARCHITECTURE_FLOW_TOKENS:
        intents.add("architecture_flow")

    return frozenset(intents)


def _build_lexical_tokens(
    raw_tokens: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return (lexical_tokens, downweighted_tokens).

    Removes generic stop-tokens and intent-only tokens from lexical_tokens so
    they cannot boost unrelated files via BM25 ``source_path`` matching.

    Domain tokens (loader, resolve, handler, …) are never stripped.
    """
    stop = _GENERIC_STOP_TOKENS | _INTENT_ONLY_TOKENS
    lexical: list[str] = []
    downweighted: list[str] = []
    seen_downweighted: set[str] = set()

    for token in raw_tokens:
        if token in stop:
            if token not in seen_downweighted:
                downweighted.append(token)
                seen_downweighted.add(token)
        else:
            lexical.append(token)

    return tuple(lexical), tuple(downweighted)
