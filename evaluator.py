"""
evaluator.py — Output Evaluation Engine for Bounty Coders
==========================================================
Central output comparison logic. All supported languages run through
the same normalisation pipeline after execution, before comparison.

Comparison modes
----------------
normalized  (default) : case-insensitive, whitespace-normalised comparison
strict                 : exact match (only \r\n → \n normalisation)
numeric                : parse & compare numeric values with configurable tolerance
custom                 : apply configured wording aliases in addition to 'normalized'

Semantic validation (built into normalized/custom modes)
---------------------------------------------------------
When an expected answer is a simple semantic keyword (e.g. 'odd', 'even',
'positive', 'prime', …) and the actual output is a longer explanatory phrase
that contains that keyword as a complete word, the answer is accepted —
provided no negation or contradiction is present.

Rules applied in order (single-line outputs only):
  1. Exact normalised match → PASS
  2. Numeric equivalence → PASS
  3. Static alias lookup (whitelist of known equivalent phrases) → PASS/FAIL
  4. Semantic word-boundary check:
       a. Expected keyword must appear as a whole word in actual output.
       b. Negation patterns (not <keyword>, isn't <keyword>, no <keyword>, …)
          anywhere in the output → FAIL regardless of step (a).
       c. Contradictory answer keyword present (e.g. 'even' when expected
          is 'odd') → FAIL.
       d. Substring trap: keyword must not be found only inside another word
          (e.g. 'oddball' must not satisfy 'odd').
"""

from __future__ import annotations

import math
import re
from typing import Optional


# ---------------------------------------------------------------------------
# Wording alias table
# ---------------------------------------------------------------------------
# Each entry is a frozenset of phrases that should all be treated as
# equivalent when the expected output matches *any* member of the set.
# Keys are the canonical (lowercased, stripped) forms of expected values.
#
# IMPORTANT: only add aliases that are genuinely interchangeable in meaning.
# "palindrome" and "not palindrome" are NOT aliases — they mean opposite things.
# ---------------------------------------------------------------------------

_ALIAS_GROUPS: list[frozenset[str]] = [
    # palindrome variations
    frozenset({"palindrome", "is palindrome", "it is a palindrome",
               "the string is a palindrome", "the number is a palindrome",
               "yes it is palindrome", "yes, it is a palindrome"}),

    # not palindrome variations
    frozenset({"not palindrome", "not a palindrome", "is not palindrome",
               "is not a palindrome", "it is not a palindrome",
               "the string is not a palindrome",
               "the number is not a palindrome",
               "no it is not palindrome", "no, it is not a palindrome"}),

    # armstrong variations
    frozenset({"armstrong", "is armstrong", "armstrong number",
               "it is an armstrong number", "yes it is armstrong",
               "yes, it is an armstrong number"}),

    # not armstrong variations
    frozenset({"not armstrong", "not an armstrong", "not an armstrong number",
               "is not armstrong", "is not an armstrong number",
               "it is not an armstrong number"}),

    # prime variations
    frozenset({"prime", "is prime", "prime number", "it is a prime number",
               "yes it is prime", "yes, it is a prime number"}),

    # not prime variations
    frozenset({"not prime", "not a prime", "not a prime number",
               "is not prime", "is not a prime number",
               "it is not a prime number"}),

    # even / odd
    frozenset({"even", "it is even", "the number is even", "number is even"}),
    frozenset({"odd", "it is odd", "the number is odd", "number is odd"}),

    # positive / negative / zero
    frozenset({"positive", "it is positive", "the number is positive",
               "number is positive"}),
    frozenset({"negative", "it is negative", "the number is negative",
               "number is negative"}),
    frozenset({"zero", "it is zero", "the number is zero", "number is zero"}),

    # yes / no — only when the *entire* output is a yes/no verdict
    frozenset({"yes", "yes.", "yeah", "true", "1", "correct"}),
    frozenset({"no", "no.", "nope", "false", "0", "incorrect"}),

    # hello world capitalisation
    frozenset({"hello world", "hello, world", "hello, world!",
               "hello world!", "hi world", "hi, world"}),
]


def _build_alias_map(groups: list[frozenset[str]]) -> dict[str, frozenset[str]]:
    """Return a dict mapping every alias → its full group of equivalents."""
    mapping: dict[str, frozenset[str]] = {}
    for group in groups:
        for member in group:
            mapping[member] = group
    return mapping


_ALIAS_MAP: dict[str, frozenset[str]] = _build_alias_map(_ALIAS_GROUPS)


# ---------------------------------------------------------------------------
# Text normalisation helpers
# ---------------------------------------------------------------------------

def _normalise_line(line: str) -> str:
    """Strip a single line and collapse internal whitespace."""
    return re.sub(r'[ \t]+', ' ', line.strip())


def _normalise_text(text: str) -> str:
    """
    Full text normalisation:
    1. Unify line endings  (\r\n → \n, lone \r → \n)
    2. Strip each line and collapse internal whitespace
    3. Remove blank lines at start / end
    4. Lowercase
    """
    # Unify line endings
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    lines = text.split('\n')
    # Strip each line & collapse internal spaces/tabs
    lines = [_normalise_line(ln) for ln in lines]
    # Drop leading/trailing blank lines
    while lines and lines[0] == '':
        lines.pop(0)
    while lines and lines[-1] == '':
        lines.pop()
    return '\n'.join(lines).lower()


def _parse_number(text: str) -> Optional[float]:
    """Try to parse *text* as a single float. Return None on failure."""
    try:
        return float(text.strip())
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Semantic keyword validation
# ---------------------------------------------------------------------------
#
# This section implements context-aware matching for simple semantic answers
# (e.g. "odd", "even", "positive", "prime").  It is only invoked when:
#   - The expected output is a *single-line* keyword-style answer.
#   - The actual output is a *single-line* longer phrase.
#   - The exact-match and alias checks have already failed.
#
# Strategy
# --------
# 1. Contradiction check: does the actual contain an *opposite* keyword?
#    e.g. actual contains "even" when expected is "odd" → FAIL immediately.
# 2. Negation check: does the actual contain "not <keyword>", "isn't <keyword>",
#    "no <keyword>", "never <keyword>", etc.?  → FAIL immediately.
# 3. Word-boundary presence check: does the expected keyword appear as a whole
#    word in the actual?  → PASS.
#
# Contradiction pairs ensure that even if the keyword appears after a negation
# that the validator missed, the contradictory answer term is still caught.
# ---------------------------------------------------------------------------

# Pairs of mutually exclusive semantic answers.  If one is expected, the other
# appearing in the actual output triggers a FAIL (contradiction).
_CONTRADICTION_PAIRS: list[tuple[frozenset[str], frozenset[str]]] = [
    (frozenset({'odd'}),           frozenset({'even'})),
    (frozenset({'even'}),          frozenset({'odd'})),
    (frozenset({'positive'}),      frozenset({'negative', 'zero'})),
    (frozenset({'negative'}),      frozenset({'positive', 'zero'})),
    (frozenset({'zero'}),          frozenset({'positive', 'negative'})),
    (frozenset({'prime'}),         frozenset({'not prime', 'composite'})),
    (frozenset({'not prime', 'composite'}), frozenset({'prime'})),
    (frozenset({'palindrome'}),    frozenset({'not palindrome'})),
    (frozenset({'not palindrome'}), frozenset({'palindrome'})),
    (frozenset({'armstrong'}),     frozenset({'not armstrong'})),
    (frozenset({'not armstrong'}), frozenset({'armstrong'})),
    (frozenset({'true', 'yes'}),   frozenset({'false', 'no'})),
    (frozenset({'false', 'no'}),   frozenset({'true', 'yes'})),
]

# Pre-built mapping: expected_keyword → set of contradictory keywords
_CONTRADICTS: dict[str, frozenset[str]] = {}
for _exp_set, _contra_set in _CONTRADICTION_PAIRS:
    for _exp_word in _exp_set:
        _CONTRADICTS[_exp_word] = _contra_set


def _whole_word_present(keyword: str, text: str) -> bool:
    """
    Return True if *keyword* (which may be a multi-word phrase) appears in
    *text* as a complete word sequence, not as part of a longer word.

    Uses \\b word-boundary anchors for single words; for multi-word phrases,
    surrounds the phrase with \\b on each end token.
    """
    # Escape regex special chars in keyword
    escaped = re.escape(keyword)
    pattern = r'(?<![a-z0-9])' + escaped + r'(?![a-z0-9])'
    return bool(re.search(pattern, text, re.IGNORECASE))


def _has_negation_of(keyword: str, text: str) -> bool:
    """
    Return True if *text* contains an unambiguous negation of *keyword*.

    Patterns checked (case-insensitive):
      - not <keyword>
      - isn't <keyword>  / is not <keyword>
      - aren't <keyword> / are not <keyword>
      - never <keyword>
      - no <keyword>
      - <keyword> is not / <keyword> isn't  (postfix)
      - <keyword>... not  (e.g. "it is not" following keyword)
    """
    kw = re.escape(keyword)
    negation_patterns = [
        r'\bnot\s+' + kw,
        r"\bisn't\s+" + kw,
        r'\bis\s+not\s+' + kw,
        r"\baren't\s+" + kw,
        r'\bare\s+not\s+' + kw,
        r'\bnever\s+' + kw,
        r'\bno\s+' + kw,
        # Postfix: "keyword is not", "keyword isn't"
        kw + r"\s+is\s+not\b",
        kw + r"\s+isn't\b",
        # General "not" anywhere before or touching the keyword on the same line
        # (already covered above, but also handle: "it is not an odd number")
        r'\bnot\s+\w+\s+' + kw,          # "not a odd", "not an odd"
        r'\bnot\s+\w+\s+\w+\s+' + kw,   # "not a prime number"
    ]
    text_l = text.lower()
    kw_l = keyword.lower()
    for pat in negation_patterns:
        if re.search(pat, text_l, re.IGNORECASE):
            return True
    return False


def _has_contradiction(expected_norm: str, actual_norm: str) -> bool:
    """
    Return True if *actual_norm* contains a keyword that directly contradicts
    *expected_norm* (e.g. expected='odd', actual contains 'even').

    Special care is taken for 'not X' expected answers: when expected is
    'not prime', the word 'prime' will naturally appear in the actual text
    "the number is not prime" — that must NOT be flagged as a contradiction.
    The contradictory signal is only 'prime' appearing WITHOUT a preceding 'not'.
    """
    contra_set = _CONTRADICTS.get(expected_norm)
    if not contra_set:
        return False
    for contra_word in contra_set:
        if not _whole_word_present(contra_word, actual_norm):
            continue
        # Found the contradictory word.  If expected starts with 'not ',
        # the actual correct answer will naturally contain the base word
        # (e.g. expected='not prime', actual='not prime' contains 'prime').
        # Only count as contradiction if it appears WITHOUT a preceding 'not '.
        if expected_norm.startswith('not '):
            # Verify the contra_word appears standalone (not negated in actual)
            # i.e. it must not be immediately preceded by 'not '
            pattern = r'(?<!\bnot\s)(?<![a-z0-9])' + re.escape(contra_word) + r'(?![a-z0-9])'
            # Simpler: look for the contra_word NOT preceded by 'not'
            neg_guarded = r'\bnot\s+' + re.escape(contra_word) + r'(?![a-z0-9])'
            # Find all occurrences of contra_word as whole word
            all_occ = list(re.finditer(r'(?<![a-z0-9])' + re.escape(contra_word) + r'(?![a-z0-9])',
                                       actual_norm, re.IGNORECASE))
            neg_occ = list(re.finditer(neg_guarded, actual_norm, re.IGNORECASE))
            # If every occurrence of contra_word is covered by a negated occurrence, no contradiction
            if len(all_occ) > len(neg_occ):
                return True  # at least one unnegated standalone occurrence
        else:
            return True
    return False


# Semantic keywords that qualify for the word-boundary semantic check.
# Only simple, single-word (or short-phrase) semantic answers use this path.
# Longer multi-line or purely numeric expected outputs do NOT.
_SEMANTIC_KEYWORDS: frozenset[str] = frozenset({
    'odd', 'even',
    'positive', 'negative', 'zero',
    'prime', 'not prime', 'composite',
    'palindrome', 'not palindrome',
    'armstrong', 'not armstrong',
    'true', 'false',
    'yes', 'no',
    'correct', 'incorrect',
})


def _semantic_match(actual_norm: str, expected_norm: str) -> Optional[bool]:
    """
    Attempt a semantic word-boundary match when the expected answer is a
    simple keyword and the actual contains more text.

    Returns
    -------
    True  – semantic match confirmed (PASS)
    False – semantic check definitively rules out a match (FAIL)
    None  – semantic check is not applicable; caller should fall through
            to the default FAIL
    """
    # Only applicable for single-line comparisons
    if '\n' in expected_norm or '\n' in actual_norm:
        return None

    # Only applicable if expected is a recognised semantic keyword
    if expected_norm not in _SEMANTIC_KEYWORDS:
        return None

    # If actual equals expected already, the caller would have caught it earlier
    # (defensive: if we reach here it didn't match exactly).

    # ── Step 1: Contradiction check ──────────────────────────────────────────
    if _has_contradiction(expected_norm, actual_norm):
        return False

    # ── Step 2: Negation check ───────────────────────────────────────────────
    if _has_negation_of(expected_norm, actual_norm):
        return False

    # ── Step 3: Word-boundary presence check ────────────────────────────────
    if _whole_word_present(expected_norm, actual_norm):
        return True

    # Expected keyword not present as a whole word
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class CompareResult:
    """Holds the outcome of a single comparison."""

    __slots__ = ('is_correct', 'mode_used', 'actual_norm', 'expected_norm',
                 'detail')

    def __init__(self, is_correct: bool, mode_used: str,
                 actual_norm: str, expected_norm: str, detail: str = ''):
        self.is_correct = is_correct
        self.mode_used = mode_used
        self.actual_norm = actual_norm
        self.expected_norm = expected_norm
        self.detail = detail

    def __bool__(self) -> bool:
        return self.is_correct


def compare_outputs(
    actual: str,
    expected: str,
    mode: str = 'normalized',
    float_tolerance: float = 1e-9,
    aliases: Optional[list[frozenset[str]]] = None,
) -> CompareResult:
    """
    Compare *actual* program output against *expected* output.

    Parameters
    ----------
    actual          : raw captured stdout (may include trailing newline etc.)
    expected        : expected output string from the database
    mode            : 'normalized' | 'strict' | 'numeric' | 'custom'
    float_tolerance : absolute tolerance for numeric mode
    aliases         : additional alias groups for 'custom' mode
                      (merged with the built-in table)

    Returns
    -------
    CompareResult – truthy when the answer should be marked correct.
    """
    mode = mode.lower().strip()
    if mode not in ('normalized', 'strict', 'numeric', 'custom'):
        mode = 'normalized'

    # ── Strict mode ─────────────────────────────────────────────────────────
    if mode == 'strict':
        # Only normalise CRLF → LF; nothing else.
        a = actual.replace('\r\n', '\n').replace('\r', '\n')
        e = expected.replace('\r\n', '\n').replace('\r', '\n')
        ok = (a == e)
        return CompareResult(ok, 'strict', a, e,
                             '' if ok else 'strict comparison failed')

    # ── Numeric mode ────────────────────────────────────────────────────────
    if mode == 'numeric':
        a_norm = _normalise_text(actual)
        e_norm = _normalise_text(expected)

        # Try single-value numeric comparison first
        a_num = _parse_number(a_norm)
        e_num = _parse_number(e_norm)

        if a_num is not None and e_num is not None:
            ok = math.isclose(a_num, e_num, abs_tol=float_tolerance, rel_tol=0)
            detail = '' if ok else (
                f'numeric mismatch: got {a_num}, expected {e_num}'
            )
            return CompareResult(ok, 'numeric', a_norm, e_norm, detail)

        # Multi-line numeric comparison: compare line by line
        a_lines = a_norm.split('\n')
        e_lines = e_norm.split('\n')
        if len(a_lines) != len(e_lines):
            return CompareResult(
                False, 'numeric', a_norm, e_norm,
                f'line count mismatch: got {len(a_lines)}, '
                f'expected {len(e_lines)}'
            )
        for i, (al, el) in enumerate(zip(a_lines, e_lines)):
            an = _parse_number(al)
            en = _parse_number(el)
            if an is not None and en is not None:
                if not math.isclose(an, en, abs_tol=float_tolerance, rel_tol=0):
                    return CompareResult(
                        False, 'numeric', a_norm, e_norm,
                        f'line {i+1}: numeric mismatch: got {an}, expected {en}'
                    )
            else:
                # Fall back to string comparison for non-numeric lines
                if al != el:
                    return CompareResult(
                        False, 'numeric', a_norm, e_norm,
                        f'line {i+1}: string mismatch'
                    )
        return CompareResult(True, 'numeric', a_norm, e_norm)

    # ── Normalized (default) and Custom modes ────────────────────────────────
    a_norm = _normalise_text(actual)
    e_norm = _normalise_text(expected)

    # Direct match after normalisation
    if a_norm == e_norm:
        return CompareResult(True, mode, a_norm, e_norm)

    # Numeric shortcut: if both parse to equal numbers, accept
    a_num = _parse_number(a_norm)
    e_num = _parse_number(e_norm)
    if a_num is not None and e_num is not None:
        if math.isclose(a_num, e_num, abs_tol=1e-9, rel_tol=0):
            return CompareResult(True, mode, a_norm, e_norm,
                                 'numeric equivalence')

    # Alias lookup (only when output is a single logical unit)
    if mode in ('normalized', 'custom'):
        # Build effective alias map
        effective_map = dict(_ALIAS_MAP)
        if mode == 'custom' and aliases:
            extra_map = _build_alias_map(aliases)
            effective_map.update(extra_map)

        # Single-line alias check
        if '\n' not in e_norm and '\n' not in a_norm:
            e_group = effective_map.get(e_norm)
            if e_group and a_norm in e_group:
                return CompareResult(True, mode, a_norm, e_norm,
                                     'alias match')

        # Multi-line: check each line pair for aliases
        a_lines = a_norm.split('\n')
        e_lines = e_norm.split('\n')
        if len(a_lines) == len(e_lines):
            all_match = True
            for al, el in zip(a_lines, e_lines):
                if al == el:
                    continue
                e_grp = effective_map.get(el)
                if e_grp and al in e_grp:
                    continue
                all_match = False
                break
            if all_match:
                return CompareResult(True, mode, a_norm, e_norm,
                                     'alias match (multi-line)')

    # ── Semantic word-boundary match (normalized / custom only) ─────────────
    # Applied after the alias table so it handles free-form explanatory phrases
    # like "n is a odd number" when expected is "odd".  Only fires for single-
    # line simple-keyword expected answers; never weakens multi-line or numeric
    # task requirements.
    if mode in ('normalized', 'custom'):
        sem = _semantic_match(a_norm, e_norm)
        if sem is True:
            return CompareResult(True, mode, a_norm, e_norm,
                                 'semantic match')
        if sem is False:
            return CompareResult(False, mode, a_norm, e_norm,
                                 f'semantic check failed: '
                                 f'got: {repr(a_norm)!s}  expected: {repr(e_norm)!s}')

    return CompareResult(
        False, mode, a_norm, e_norm,
        f'got: {repr(a_norm)!s}  expected: {repr(e_norm)!s}'
    )


def classify_error(result: dict) -> str:
    """
    Classify a run_code() result dict into one of:
      'compilation_error' | 'runtime_error' | 'timeout' |
      'unsupported_language' | 'unknown'

    Prefers the structured 'error_type' key returned by run_code().
    Falls back to heuristic string parsing when not present.
    """
    # Prefer the structured key set by run_code()
    if result.get('error_type'):
        return result['error_type']

    error_msg = (result.get('error') or '').lower()

    if 'timed out' in error_msg or 'timeout' in error_msg:
        return 'timeout'

    if 'error:' in error_msg or 'exception' in error_msg:
        if ('traceback' in error_msg
                or 'exception in thread' in error_msg
                or 'segmentation fault' in error_msg
                or 'sigsegv' in error_msg
                or 'runtime' in error_msg):
            return 'runtime_error'
        return 'compilation_error'

    if error_msg:
        return 'runtime_error'

    return 'unknown'

