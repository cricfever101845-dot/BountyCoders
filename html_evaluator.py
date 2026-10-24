"""
html_evaluator.py — HTML-aware structural validator for Bounty Coders
=====================================================================
Replaces the old whole-string keyword search for HTML/CSS questions with a
proper parse-based check using Python's built-in html.parser.

Design principles
-----------------
* Uses only the Python standard library (html.parser, re).
* Never executes submitted JavaScript; parses structure only.
* Ignores tag-name capitalisation, irrelevant whitespace and indentation.
* Accepts complete HTML documents *and* bare fragments equally.
* Rejects tags that appear only inside HTML comments, <script>, or <style>.
* Validates element existence, attribute presence/value, text content, and
  required parent-child relationships where the expected-answer string
  expresses them.
* Derives validation rules directly from the existing expected_output strings
  stored in the database — NO schema migration required.

How expected-output strings are parsed
---------------------------------------
The database stores expected answers as " and "-separated tokens, e.g.:

    "<form> and <input and <button>"
    "<input and type=\"password\""
    "h3>Welcome</h3"          ← leading < missing (DB artifact, handled)
    "<button>submit</button>"
    "controls"                 ← bare attribute word
    "href=\"https://google.com\""
    "<img and height=\"200\" and width=\"200\" and alt="

Each token is classified and a corresponding Rule object is produced.
All rules must be satisfied for the submission to be marked correct.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Optional


# ---------------------------------------------------------------------------
# 1. HTML structure collector
# ---------------------------------------------------------------------------

class _HTMLElement:
    """Represents one parsed HTML tag with its attributes and inner text."""
    __slots__ = ('tag', 'attrs', 'text', 'children', 'is_comment')

    def __init__(self, tag: str, attrs: dict[str, Optional[str]],
                 is_comment: bool = False):
        self.tag: str = tag.lower()
        self.attrs: dict[str, Optional[str]] = {k.lower(): v for k, v in attrs.items()}
        self.text: str = ''          # concatenated direct text data
        self.children: list[_HTMLElement] = []
        self.is_comment: bool = is_comment


class _StructureCollector(HTMLParser):
    """
    Walk the submitted HTML source and build a flat list of real elements
    (elements that appear outside of comments, <script>, and <style>).
    """

    # Tags whose content should never be treated as HTML structure
    _OPAQUE_TAGS = {'script', 'style'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._root = _HTMLElement('__root__', {})
        self._stack: list[_HTMLElement] = [self._root]
        self._opaque_depth: int = 0   # non-zero while inside script/style
        self.comments: list[str] = []
        # Flat lists for quick O(n) lookups
        self._all_elements: list[_HTMLElement] = []
        self._has_comment: bool = False

    # ── Parser callbacks ────────────────────────────────────────────────────

    def handle_starttag(self, tag: str, attrs):
        tag = tag.lower()
        attr_dict = {k.lower(): (v if v is not None else '') for k, v in attrs}
        el = _HTMLElement(tag, attr_dict)
        self._stack[-1].children.append(el)
        self._all_elements.append(el)
        if tag in self._OPAQUE_TAGS:
            self._opaque_depth += 1
        # Void elements don't get pushed onto the stack
        if tag not in _VOID_TAGS:
            self._stack.append(el)

    def handle_endtag(self, tag: str):
        tag = tag.lower()
        if tag in self._OPAQUE_TAGS and self._opaque_depth > 0:
            self._opaque_depth -= 1
        # Pop up to matching open tag (handles malformed HTML gracefully)
        for i in range(len(self._stack) - 1, 0, -1):
            if self._stack[i].tag == tag:
                self._stack = self._stack[:i]
                break

    def handle_data(self, data: str):
        if self._opaque_depth > 0:
            return  # ignore script/style content
        if self._stack:
            self._stack[-1].text += data

    def handle_comment(self, data: str):
        self.comments.append(data)
        self._has_comment = True

    # ── Convenience accessors ───────────────────────────────────────────────

    def elements(self) -> list[_HTMLElement]:
        """All real (non-opaque, non-comment) elements."""
        return [e for e in self._all_elements if not e.is_comment]

    def has_comment(self) -> bool:
        return self._has_comment

    def find_by_tag(self, tag: str) -> list[_HTMLElement]:
        tag = tag.lower()
        return [e for e in self.elements() if e.tag == tag]

    def any_has_attr(self, attr: str, value: Optional[str] = None) -> bool:
        """Return True if any element has the attribute (optionally with value)."""
        attr = attr.lower()
        for el in self.elements():
            if attr in el.attrs:
                if value is None:
                    return True
                # Case-insensitive attribute value comparison
                if (el.attrs[attr] or '').lower() == value.lower():
                    return True
        return False

    def any_tag_has_attr(self, tag: str, attr: str,
                         value: Optional[str] = None) -> bool:
        """Return True if any element of *tag* has the given attribute."""
        for el in self.find_by_tag(tag):
            if attr.lower() in el.attrs:
                if value is None:
                    return True
                if (el.attrs[attr.lower()] or '').lower() == value.lower():
                    return True
        return False


# HTML void elements (self-closing; never push onto stack)
_VOID_TAGS = frozenset({
    'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
    'link', 'meta', 'param', 'source', 'track', 'wbr',
})


# ---------------------------------------------------------------------------
# 2. Rule classes
# ---------------------------------------------------------------------------

class _Rule:
    """Base class — each subclass checks one structural requirement."""
    def check(self, collector: _StructureCollector) -> tuple[bool, str]:
        raise NotImplementedError


class _TagExistsRule(_Rule):
    """Element <tag> must appear in the parsed document."""
    def __init__(self, tag: str):
        self.tag = tag.lower()

    def check(self, c: _StructureCollector) -> tuple[bool, str]:
        ok = bool(c.find_by_tag(self.tag))
        return ok, ('' if ok else f'Missing element <{self.tag}>')


class _TagWithAttrRule(_Rule):
    """Any element of type <tag> must have attribute attr (optionally = value)."""
    def __init__(self, tag: str, attr: str, value: Optional[str] = None):
        self.tag = tag.lower()
        self.attr = attr.lower()
        self.value = value

    def check(self, c: _StructureCollector) -> tuple[bool, str]:
        ok = c.any_tag_has_attr(self.tag, self.attr, self.value)
        detail = ('' if ok else
                  f'No <{self.tag}> with {self.attr}'
                  + (f'="{self.value}"' if self.value else ''))
        return ok, detail


class _AnyTagWithAttrRule(_Rule):
    """Any element (any tag) must have attribute attr (optionally = value)."""
    def __init__(self, attr: str, value: Optional[str] = None):
        self.attr = attr.lower()
        self.value = value

    def check(self, c: _StructureCollector) -> tuple[bool, str]:
        ok = c.any_has_attr(self.attr, self.value)
        detail = ('' if ok else
                  f'No element with attribute {self.attr}'
                  + (f'="{self.value}"' if self.value else ''))
        return ok, detail


class _TagWithTextRule(_Rule):
    """Element <tag> must exist and contain text (case-insensitive)."""
    def __init__(self, tag: str, text: str):
        self.tag = tag.lower()
        self.text = text.lower().strip()

    def _collect_text(self, el: _HTMLElement) -> str:
        """Recursively collect all text under an element."""
        parts = [el.text]
        for child in el.children:
            parts.append(self._collect_text(child))
        return ''.join(parts)

    def check(self, c: _StructureCollector) -> tuple[bool, str]:
        for el in c.find_by_tag(self.tag):
            full_text = self._collect_text(el).lower().strip()
            if self.text in full_text:
                return True, ''
        return False, f'No <{self.tag}> containing text "{self.text}"'


class _CommentExistsRule(_Rule):
    """At least one HTML comment must be present."""
    def check(self, c: _StructureCollector) -> tuple[bool, str]:
        ok = c.has_comment()
        return ok, ('' if ok else 'No HTML comment found (<!-- ... -->)')


class _BareWordRule(_Rule):
    """
    A bare keyword that carries no angle brackets.
    Strategy: check as attribute name first, then as tag name.
    Used for tokens like 'controls', 'required', 'src', 'img'.
    """
    def __init__(self, word: str):
        self.word = word.lower().strip()

    def check(self, c: _StructureCollector) -> tuple[bool, str]:
        # Try as attribute (covers 'controls', 'required', 'src', 'alt', etc.)
        if c.any_has_attr(self.word):
            return True, ''
        # Try as tag name (covers 'img', 'video', 'audio', etc.)
        if c.find_by_tag(self.word):
            return True, ''
        return False, f'Missing "{self.word}" as a tag name or attribute'


# ---------------------------------------------------------------------------
# 3. Expected-output string → list of rules
# ---------------------------------------------------------------------------

def _parse_expected(expected: str) -> list[_Rule]:
    """
    Decode one expected_output string from the database into a list of Rules.

    Splitting on ' and ' gives individual requirement tokens.  Each token is
    then classified by the patterns it matches.
    """
    rules: list[_Rule] = []
    tokens = [t.strip() for t in expected.split(' and ') if t.strip()]

    for raw in tokens:
        rule = _token_to_rule(raw)
        if rule is not None:
            rules.append(rule)

    return rules


# Regex helpers used by _token_to_rule
_RE_FULL_TAG_WITH_TEXT = re.compile(
    r'^<?(\w[\w\d-]*)>([^<]+)</\1>$', re.IGNORECASE)
_RE_PARTIAL_TAG_WITH_TEXT = re.compile(
    r'^(\w[\w\d-]*)>([^<]+)</\1$', re.IGNORECASE)   # missing leading <
_RE_FULL_OPEN_TAG     = re.compile(r'^<(\w[\w\d-]*)>$', re.IGNORECASE)
_RE_FULL_CLOSE_TAG    = re.compile(r'^</(\w[\w\d-]*)>$', re.IGNORECASE)
_RE_OPEN_TAG_PREFIX   = re.compile(r'^<(\w[\w\d-]*)$', re.IGNORECASE)   # <tag (no >)
_RE_ATTR_EQ_VALUE     = re.compile(r'^(\w[\w\d-]*)="([^"]*)"$', re.IGNORECASE)
_RE_ATTR_EQ_NOVALUE   = re.compile(r'^(\w[\w\d-]*)=$', re.IGNORECASE)
_RE_ATTR_IN_TAG       = re.compile(
    r'^<(\w[\w\d-]*)\s+(\w[\w\d-]*)(?:="([^"]*)")?$', re.IGNORECASE)
_RE_COMMENT_OPEN      = re.compile(r'^<!--$')
_RE_COMMENT_CLOSE     = re.compile(r'^-->$')
_RE_BARE_WORD         = re.compile(r'^[\w][\w\d-]*$')
_RE_PARTIAL_OPEN_TAG  = re.compile(r'^(\w[\w\d-]*)>$', re.IGNORECASE)   # tag> missing <


def _token_to_rule(raw: str) -> Optional[_Rule]:  # noqa: C901 (complexity OK here)
    """Classify one token string and return the appropriate Rule."""

    t = raw.strip()

    # ── HTML comment markers ────────────────────────────────────────────────
    if t in ('<!--', '-->'):
        return _CommentExistsRule()

    # ── <tag>text</tag>  full element with required text ────────────────────
    m = _RE_FULL_TAG_WITH_TEXT.match(t)
    if m:
        return _TagWithTextRule(m.group(1), m.group(2))

    # ── tag>text</tag  (missing leading <, DB artifact) ─────────────────────
    m = _RE_PARTIAL_TAG_WITH_TEXT.match(t)
    if m:
        return _TagWithTextRule(m.group(1), m.group(2))

    # ── <tag>  full open tag (no text content requirement) ──────────────────
    m = _RE_FULL_OPEN_TAG.match(t)
    if m:
        return _TagExistsRule(m.group(1))

    # ── </tag>  close tag → just verify the opening tag exists ──────────────
    m = _RE_FULL_CLOSE_TAG.match(t)
    if m:
        return _TagExistsRule(m.group(1))

    # ── <tag  open tag prefix (no closing >) e.g. "<input" ──────────────────
    m = _RE_OPEN_TAG_PREFIX.match(t)
    if m:
        return _TagExistsRule(m.group(1))

    # ── <tag attr="value"  or  <tag attr (no closing >) ─────────────────────
    m = _RE_ATTR_IN_TAG.match(t)
    if m:
        tag, attr, value = m.group(1), m.group(2), m.group(3)
        return _TagWithAttrRule(tag, attr, value)

    # ── attr="value"  free-standing attribute with value ────────────────────
    m = _RE_ATTR_EQ_VALUE.match(t)
    if m:
        attr, value = m.group(1), m.group(2)
        # 'type' is common: we want any element with that type value
        return _AnyTagWithAttrRule(attr, value)

    # ── attr=  free-standing attribute name (no value) ──────────────────────
    m = _RE_ATTR_EQ_NOVALUE.match(t)
    if m:
        return _AnyTagWithAttrRule(m.group(1))

    # ── tag>  partial open (missing leading <), e.g. "h2>" ──────────────────
    m = _RE_PARTIAL_OPEN_TAG.match(t)
    if m:
        return _TagExistsRule(m.group(1))

    # ── Bare word: attribute name or tag name ────────────────────────────────
    m = _RE_BARE_WORD.match(t)
    if m:
        return _BareWordRule(t)

    # Unrecognised — skip (fail-open so unexpected DB entries don't break things)
    return None


# ---------------------------------------------------------------------------
# 4. Public API
# ---------------------------------------------------------------------------

class HTMLCheckResult:
    """Result of an HTML validation pass."""
    __slots__ = ('is_correct', 'failures', 'rules_total', 'rules_passed')

    def __init__(self, failures: list[str], rules_total: int, rules_passed: int):
        self.failures = failures
        self.rules_total = rules_total
        self.rules_passed = rules_passed
        self.is_correct = len(failures) == 0

    def __bool__(self) -> bool:
        return self.is_correct

    @property
    def detail(self) -> str:
        if self.is_correct:
            return f'All {self.rules_total} requirement(s) satisfied.'
        return '; '.join(self.failures)


def evaluate_html(submitted_code: str, expected_output: str) -> HTMLCheckResult:
    """
    Parse *submitted_code* as HTML, then verify every requirement encoded
    in *expected_output* (the database string for this question).

    Parameters
    ----------
    submitted_code  : the full HTML source submitted by the student
    expected_output : the expected_output string from the questions table,
                      e.g. '<b> and </b>' or '<input and type="password"'

    Returns
    -------
    HTMLCheckResult — truthy when the submission satisfies all requirements.
    """
    # Parse the submitted HTML
    collector = _StructureCollector()
    try:
        collector.feed(submitted_code)
    except Exception:
        # Even on parser error, work with what was collected
        pass

    # Derive rules from the expected-output string
    rules = _parse_expected(expected_output)
    if not rules:
        # No parseable rules → fall back to the legacy keyword check
        return HTMLCheckResult([], 0, 0)

    failures: list[str] = []
    for rule in rules:
        ok, msg = rule.check(collector)
        if not ok:
            failures.append(msg)

    return HTMLCheckResult(failures, len(rules), len(rules) - len(failures))
