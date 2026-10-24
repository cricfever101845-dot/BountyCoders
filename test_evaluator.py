"""
test_evaluator.py — Regression tests for the Bounty Coders output evaluator.

Run with:  python -m pytest test_evaluator.py -v
or:        python test_evaluator.py
"""

import sys
import os
import unittest

# Make sure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from evaluator import compare_outputs, classify_error, CompareResult


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

def ok(actual, expected, mode='normalized', tol=1e-9):
    """Assert that compare_outputs returns True."""
    result = compare_outputs(actual, expected, mode=mode, float_tolerance=tol)
    return result.is_correct


def fail(actual, expected, mode='normalized', tol=1e-9):
    """Assert that compare_outputs returns False."""
    return not ok(actual, expected, mode=mode, tol=tol)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Case-insensitive comparison
# ─────────────────────────────────────────────────────────────────────────────

class TestCaseInsensitive(unittest.TestCase):

    def test_palindrome_vs_PALINDROME(self):
        self.assertTrue(ok('Palindrome\n', 'palindrome'))

    def test_PALINDROME_vs_palindrome(self):
        self.assertTrue(ok('PALINDROME', 'palindrome'))

    def test_hello_world_case(self):
        self.assertTrue(ok('HELLO WORLD\n', 'hello world'))

    def test_hello_world_mixed(self):
        self.assertTrue(ok('Hello World  ', 'hello world'))

    def test_yes_vs_YES(self):
        self.assertTrue(ok('YES', 'yes'))

    def test_yes_vs_Yes(self):
        self.assertTrue(ok('Yes', 'yes'))


# ─────────────────────────────────────────────────────────────────────────────
# 2. Whitespace normalisation
# ─────────────────────────────────────────────────────────────────────────────

class TestWhitespace(unittest.TestCase):

    def test_leading_trailing_spaces(self):
        self.assertTrue(ok('  hello world  ', 'hello world'))

    def test_trailing_newline(self):
        self.assertTrue(ok('hello world\n', 'hello world'))

    def test_multiple_trailing_newlines(self):
        self.assertTrue(ok('hello world\n\n\n', 'hello world'))

    def test_crlf_line_endings(self):
        self.assertTrue(ok('hello world\r\n', 'hello world'))

    def test_mixed_line_endings(self):
        self.assertTrue(ok('First\r\nSecond\r\n', 'First\nSecond'))

    def test_extra_spaces_between_words(self):
        self.assertTrue(ok('hello   world', 'hello world'))

    def test_tab_between_words(self):
        self.assertTrue(ok('hello\tworld', 'hello world'))

    def test_blank_lines_around(self):
        self.assertTrue(ok('\n\nhello world\n\n', 'hello world'))

    def test_inner_blank_line_matters(self):
        # Two meaningful lines with a blank in between should NOT match one line
        self.assertFalse(ok('hello\n\nworld', 'hello world'))


# ─────────────────────────────────────────────────────────────────────────────
# 3. Alias / wording variations
# ─────────────────────────────────────────────────────────────────────────────

class TestAliases(unittest.TestCase):

    def test_not_palindrome_alias(self):
        # "not palindrome" and "not a palindrome" are aliases
        self.assertTrue(ok('not a palindrome', 'not palindrome'))

    def test_palindrome_alias(self):
        self.assertTrue(ok('is palindrome', 'palindrome'))

    def test_prime_alias(self):
        self.assertTrue(ok('it is a prime number', 'prime'))

    def test_not_prime_alias(self):
        self.assertTrue(ok('not a prime number', 'not prime'))

    def test_armstrong_alias(self):
        self.assertTrue(ok('armstrong number', 'armstrong'))

    def test_not_armstrong_alias(self):
        self.assertTrue(ok('not an armstrong number', 'not armstrong'))

    def test_even_alias(self):
        self.assertTrue(ok('the number is even', 'even'))

    def test_odd_alias(self):
        self.assertTrue(ok('the number is odd', 'odd'))

    def test_positive_alias(self):
        self.assertTrue(ok('number is positive', 'positive'))

    def test_negative_alias(self):
        self.assertTrue(ok('it is negative', 'negative'))

    def test_yes_true_alias(self):
        self.assertTrue(ok('true', 'yes'))

    def test_no_false_alias(self):
        self.assertTrue(ok('false', 'no'))


# ─────────────────────────────────────────────────────────────────────────────
# 4. Preserve meaningful differences
# ─────────────────────────────────────────────────────────────────────────────

class TestMeaningfulDifferences(unittest.TestCase):

    def test_palindrome_vs_not_palindrome(self):
        self.assertFalse(ok('Not Palindrome', 'palindrome'))

    def test_not_palindrome_vs_palindrome(self):
        self.assertFalse(ok('palindrome', 'not palindrome'))

    def test_true_vs_false(self):
        self.assertFalse(ok('False', 'True'))

    def test_10_vs_100(self):
        self.assertFalse(ok('100', '10'))

    def test_abc_vs_abcd(self):
        self.assertFalse(ok('ABCD', 'ABC'))

    def test_prime_vs_not_prime(self):
        self.assertFalse(ok('not prime', 'prime'))

    def test_armstrong_vs_not_armstrong(self):
        self.assertFalse(ok('not armstrong', 'armstrong'))

    def test_yes_vs_no_different(self):
        self.assertFalse(ok('no', 'yes'))

    def test_positive_vs_negative_different(self):
        self.assertFalse(ok('negative', 'positive'))

    def test_even_vs_odd_different(self):
        self.assertFalse(ok('odd', 'even'))


# ─────────────────────────────────────────────────────────────────────────────
# 5. Numeric mode
# ─────────────────────────────────────────────────────────────────────────────

class TestNumericMode(unittest.TestCase):

    def test_1_0_vs_1_000(self):
        self.assertTrue(ok('1.000', '1.0', mode='numeric'))

    def test_20_vs_20_0(self):
        self.assertTrue(ok('20.0', '20', mode='numeric'))

    def test_integer_equal(self):
        self.assertTrue(ok('10', '10', mode='numeric'))

    def test_10_vs_100_numeric(self):
        self.assertFalse(ok('100', '10', mode='numeric'))

    def test_float_close_within_tol(self):
        self.assertTrue(ok('3.14159', '3.14159', mode='numeric'))

    def test_float_outside_tol(self):
        self.assertFalse(ok('3.15', '3.14', mode='numeric', tol=1e-9))

    def test_float_within_custom_tol(self):
        # With a tolerance of 0.1, 3.15 ≈ 3.14 is False (diff = 0.01)
        # but with 0.02 tolerance, should pass
        self.assertTrue(ok('3.15', '3.14', mode='numeric', tol=0.02))

    def test_multiline_numeric(self):
        self.assertTrue(ok('1.0\n2.0\n3.0', '1\n2\n3', mode='numeric'))

    def test_multiline_numeric_mismatch(self):
        self.assertFalse(ok('1\n2\n4', '1\n2\n3', mode='numeric'))

    # Integer 20 vs float string 20.0 should pass in normalized mode too
    def test_20_vs_20_0_normalized(self):
        self.assertTrue(ok('20.0', '20', mode='normalized'))


# ─────────────────────────────────────────────────────────────────────────────
# 6. Multi-line output — order matters
# ─────────────────────────────────────────────────────────────────────────────

class TestMultiLine(unittest.TestCase):

    def test_correct_order(self):
        self.assertTrue(ok('First\nSecond', 'First\nSecond'))

    def test_wrong_order(self):
        self.assertFalse(ok('Second\nFirst', 'First\nSecond'))

    def test_multiline_case_insensitive(self):
        self.assertTrue(ok('FIRST\nSECOND', 'first\nsecond'))

    def test_multiline_trailing_newline(self):
        self.assertTrue(ok('first\nsecond\n', 'first\nsecond'))

    def test_multiline_crlf(self):
        self.assertTrue(ok('first\r\nsecond\r\n', 'first\nsecond'))

    def test_multiplication_table(self):
        actual   = '6x1=6\n6x2=12\n6x3=18\n6x4=24\n6x5=30\n6x6=36\n'
        expected = '6x1=6\n6x2=12\n6x3=18\n6x4=24\n6x5=30\n6x6=36'
        self.assertTrue(ok(actual, expected))

    def test_even_numbers_list(self):
        actual   = '2\n4\n6\n8\n10\n12\n14\n16\n18\n20\n'
        expected = '2\n4\n6\n8\n10\n12\n14\n16\n18\n20'
        self.assertTrue(ok(actual, expected))


# ─────────────────────────────────────────────────────────────────────────────
# 7. Strict mode
# ─────────────────────────────────────────────────────────────────────────────

class TestStrictMode(unittest.TestCase):

    def test_exact_match(self):
        self.assertTrue(ok('hello world', 'hello world', mode='strict'))

    def test_case_sensitive_strict(self):
        self.assertFalse(ok('Hello World', 'hello world', mode='strict'))

    def test_trailing_newline_strict(self):
        # Only CRLF→LF is normalised; trailing \n differs from no trailing \n
        self.assertFalse(ok('hello world\n', 'hello world', mode='strict'))

    def test_crlf_normalised_in_strict(self):
        self.assertTrue(ok('hello world\r\n', 'hello world\n', mode='strict'))


# ─────────────────────────────────────────────────────────────────────────────
# 8. Edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases(unittest.TestCase):

    def test_empty_actual_empty_expected(self):
        self.assertTrue(ok('', ''))

    def test_empty_actual_nonempty_expected(self):
        self.assertFalse(ok('', 'hello'))

    def test_nonempty_actual_empty_expected(self):
        self.assertFalse(ok('hello', ''))

    def test_whitespace_only_vs_empty(self):
        # "   \n\n  " normalises to empty → matches empty expected
        self.assertTrue(ok('   \n\n  ', ''))

    def test_unicode_text(self):
        self.assertTrue(ok('こんにちは', 'こんにちは'))

    def test_unicode_case(self):
        # Python lowercases ASCII only for non-ASCII chars
        self.assertTrue(ok('CAFÉ', 'café'))

    def test_single_integer(self):
        self.assertTrue(ok('42\n', '42'))

    def test_negative_number_preserved(self):
        self.assertFalse(ok('-5', '5'))

    def test_negative_number_correct(self):
        self.assertTrue(ok('-5\n', '-5'))


# ─────────────────────────────────────────────────────────────────────────────
# 9. classify_error
# ─────────────────────────────────────────────────────────────────────────────

class TestClassifyError(unittest.TestCase):

    def test_structured_timeout(self):
        r = {'error': 'timed out', 'error_type': 'timeout', 'output': ''}
        self.assertEqual(classify_error(r), 'timeout')

    def test_structured_compilation_error(self):
        r = {'error': 'main.c:3:1: error: ...', 'error_type': 'compilation_error', 'output': ''}
        self.assertEqual(classify_error(r), 'compilation_error')

    def test_structured_runtime_error(self):
        r = {'error': 'Segmentation fault', 'error_type': 'runtime_error', 'output': ''}
        self.assertEqual(classify_error(r), 'runtime_error')

    def test_heuristic_timeout(self):
        r = {'error': 'Code execution timed out (10s limit)', 'output': ''}
        self.assertEqual(classify_error(r), 'timeout')

    def test_heuristic_compilation(self):
        r = {'error': 'main.java:5: error: ; expected', 'output': ''}
        self.assertEqual(classify_error(r), 'compilation_error')

    def test_heuristic_runtime_traceback(self):
        r = {'error': 'Traceback (most recent call last): ...', 'output': ''}
        self.assertEqual(classify_error(r), 'runtime_error')

    def test_no_error(self):
        r = {'error': None, 'output': 'hello'}
        self.assertEqual(classify_error(r), 'unknown')


# ─────────────────────────────────────────────────────────────────────────────
# 10. Real question samples from the database
# ─────────────────────────────────────────────────────────────────────────────

class TestRealQuestionSamples(unittest.TestCase):
    """Spot-check with the exact expected_output values from seed_questions.py"""

    def test_hello_world(self):
        self.assertTrue(ok('hello world\n', 'hello world'))

    def test_odd(self):
        self.assertTrue(ok('Odd\n', 'odd'))

    def test_even(self):
        self.assertTrue(ok('Even\n', 'even'))

    def test_palindrome_number(self):
        self.assertTrue(ok('Palindrome\n', 'palindrome'))

    def test_not_palindrome_variation(self):
        # Some programs print "Not a Palindrome"
        self.assertTrue(ok('Not a Palindrome\n', 'not palindrome'))

    def test_armstrong(self):
        self.assertTrue(ok('Armstrong\n', 'armstrong'))

    def test_prime(self):
        self.assertTrue(ok('Prime\n', 'prime'))

    def test_multiplication_table_6(self):
        actual = '6x1=6\n6x2=12\n6x3=18\n6x4=24\n6x5=30\n6x6=36\n'
        expected = '6x1=6\n6x2=12\n6x3=18\n6x4=24\n6x5=30\n6x6=36'
        self.assertTrue(ok(actual, expected))

    def test_reversed_string(self):
        self.assertTrue(ok('nohtyp\n', 'nohtyp'))

    def test_positive(self):
        self.assertTrue(ok('Positive\n', 'positive'))

    def test_negative(self):
        self.assertTrue(ok('Negative\n', 'negative'))

    def test_sum_50(self):
        self.assertTrue(ok('1275\n', '1275'))

    def test_common_elements_multiline(self):
        self.assertTrue(ok('2\n6\n', '2\n6'))

    def test_second_smallest(self):
        self.assertTrue(ok('2\n', '2'))


# ─────────────────────────────────────────────────────────────────────────────
# Run directly
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# 11. Semantic word-boundary validation (the bug-fix regression suite)
#     Covers the exact scenarios from the bug report.
#     All languages share compare_outputs(), so these tests cover Python,
#     C and Java output equally.
# ─────────────────────────────────────────────────────────────────────────────

class TestSemanticWordBoundary(unittest.TestCase):
    """
    Verify the new semantic matching layer.
    Expected 'odd': correct w/ explanatory text → PASS
                    negated / contradicted       → FAIL
                    substring-only ('oddball')   → FAIL
                    empty                        → FAIL
    Same principles apply symmetrically for 'even'.
    """

    # ── 'odd' as expected ────────────────────────────────────────────────────

    def test_odd_exact(self):
        """Exact answer must pass."""
        self.assertTrue(ok('odd', 'odd'))

    def test_odd_with_trailing_newline(self):
        """Trailing newline normalised away → pass."""
        self.assertTrue(ok('odd\n', 'odd'))

    def test_odd_sentence_n_is_a_odd_number(self):
        """'n is a odd number' — the bug-report case — must pass."""
        self.assertTrue(ok('n is a odd number', 'odd'))

    def test_odd_sentence_the_number_is_odd(self):
        """'The number is odd' — extra context, correct."""
        self.assertTrue(ok('The number is odd', 'odd'))

    def test_odd_sentence_number_is_odd_caps(self):
        """Mixed-case explanatory sentence."""
        self.assertTrue(ok('Number Is Odd', 'odd'))

    def test_odd_rejected_when_even(self):
        """'even' contradicts 'odd' → FAIL."""
        self.assertFalse(ok('even', 'odd'))

    def test_odd_rejected_not_odd(self):
        """'not odd' negates the answer → FAIL."""
        self.assertFalse(ok('not odd', 'odd'))

    def test_odd_rejected_sentence_not_odd(self):
        """'the number is not odd' → FAIL."""
        self.assertFalse(ok('the number is not odd', 'odd'))

    def test_odd_rejected_not_odd_it_is_even(self):
        """'not odd, it is even' — negation AND contradiction → FAIL."""
        self.assertFalse(ok('not odd, it is even', 'odd'))

    def test_odd_rejected_oddball_substring(self):
        """'oddball' — 'odd' is only a prefix, not a whole word → FAIL."""
        self.assertFalse(ok('oddball', 'odd'))

    def test_odd_rejected_empty(self):
        """Empty output → FAIL."""
        self.assertFalse(ok('', 'odd'))

    # ── 'even' as expected ───────────────────────────────────────────────────

    def test_even_exact(self):
        self.assertTrue(ok('even', 'even'))

    def test_even_sentence_the_number_is_even(self):
        self.assertTrue(ok('The number is even', 'even'))

    def test_even_sentence_n_is_a_even_number(self):
        self.assertTrue(ok('n is a even number', 'even'))

    def test_even_rejected_odd(self):
        """'odd' contradicts 'even' → FAIL."""
        self.assertFalse(ok('odd', 'even'))

    def test_even_rejected_not_even(self):
        self.assertFalse(ok('not even', 'even'))

    def test_even_rejected_the_number_is_not_even(self):
        self.assertFalse(ok('the number is not even', 'even'))

    def test_even_rejected_n_is_a_odd_number(self):
        """Actual says 'odd', expected is 'even' → FAIL."""
        self.assertFalse(ok('n is a odd number', 'even'))

    # ── 'positive' / 'negative' / 'zero' ────────────────────────────────────

    def test_positive_sentence(self):
        self.assertTrue(ok('the answer is positive', 'positive'))

    def test_positive_rejected_negative(self):
        self.assertFalse(ok('negative', 'positive'))

    def test_positive_rejected_not_positive(self):
        self.assertFalse(ok('not positive', 'positive'))

    def test_positive_substring_rejected(self):
        """'positively' — 'positive' not a whole word → FAIL."""
        self.assertFalse(ok('positively', 'positive'))

    def test_negative_sentence(self):
        self.assertTrue(ok('the number is negative', 'negative'))

    def test_negative_rejected_positive(self):
        self.assertFalse(ok('positive', 'negative'))

    # ── 'prime' / 'not prime' ────────────────────────────────────────────────

    def test_prime_sentence(self):
        self.assertTrue(ok('the number is prime', 'prime'))

    def test_prime_rejected_not_prime(self):
        self.assertFalse(ok('not prime', 'prime'))

    def test_prime_rejected_not_a_prime(self):
        self.assertFalse(ok('it is not a prime number', 'prime'))

    def test_not_prime_sentence(self):
        self.assertTrue(ok('the number is not prime', 'not prime'))

    def test_not_prime_rejected_prime(self):
        self.assertFalse(ok('prime', 'not prime'))

    # ── 'palindrome' / 'not palindrome' ─────────────────────────────────────

    def test_palindrome_sentence(self):
        self.assertTrue(ok('the string is a palindrome', 'palindrome'))

    def test_palindrome_rejected_not_palindrome(self):
        self.assertFalse(ok('not palindrome', 'palindrome'))

    def test_not_palindrome_sentence(self):
        self.assertTrue(ok('the string is not a palindrome', 'not palindrome'))

    # ── 'yes' / 'no' / 'true' / 'false' ────────────────────────────────────

    def test_true_sentence(self):
        self.assertTrue(ok('the answer is true', 'true'))

    def test_true_rejected_false(self):
        self.assertFalse(ok('false', 'true'))

    def test_false_sentence(self):
        self.assertTrue(ok('the answer is false', 'false'))

    def test_false_rejected_true(self):
        self.assertFalse(ok('true', 'false'))

    # ── Numeric values must remain strict ───────────────────────────────────

    def test_numeric_10_vs_100(self):
        """Numeric outputs are NOT subject to semantic relaxation → FAIL."""
        self.assertFalse(ok('100', '10'))

    def test_numeric_with_sentence_fails(self):
        """'the answer is 10' for expected '10' is NOT accepted semantically."""
        self.assertFalse(ok('the answer is 10', '10'))

    # ── Multi-line outputs are NOT subject to semantic relaxation ────────────

    def test_multiline_not_semantically_relaxed(self):
        """5\n10\n15 must not be accepted with extra text."""
        self.assertFalse(ok('the numbers are 5\n10\n15', '5\n10\n15'))

    def test_multiline_order_matters(self):
        self.assertFalse(ok('5\n15\n10', '5\n10\n15'))

    # ── Whitespace / case around semantic keywords ───────────────────────────

    def test_odd_uppercase_sentence(self):
        """'N IS A ODD NUMBER' → PASS (case-normalised before check)."""
        self.assertTrue(ok('N IS A ODD NUMBER', 'odd'))

    def test_odd_leading_trailing_whitespace(self):
        self.assertTrue(ok('  odd  ', 'odd'))

    def test_odd_crlf_sentence(self):
        self.assertTrue(ok('n is a odd number\r\n', 'odd'))


# ─────────────────────────────────────────────────────────────────────────────
# 12. Cross-language execution path verification
#     These tests confirm the shared compare_outputs() function handles the
#     same rules for Python, C and Java (all languages use the same function).
# ─────────────────────────────────────────────────────────────────────────────

class TestCrossLanguageSemantics(unittest.TestCase):
    """
    Simulate the output that Python, C and Java programs might produce and
    verify compare_outputs() applies the same rules.
    (Actual compilation/execution is not performed here — that is covered by
    the language-specific integration pipeline.  This suite verifies the
    shared validation layer is language-agnostic.)
    """

    # ── Python-style output ──────────────────────────────────────────────────

    def test_python_odd_print_statement(self):
        """print("n is a odd number") → 'n is a odd number\n' → PASS."""
        self.assertTrue(ok('n is a odd number\n', 'odd'))

    def test_python_even_with_f_string(self):
        """print(f"The number {n} is even") might output 'The number 4 is even'."""
        self.assertTrue(ok('The number 4 is even\n', 'even'))

    def test_python_even_false_negation(self):
        """print("The number is not even") → FAIL."""
        self.assertFalse(ok('The number is not even\n', 'even'))

    def test_python_prime_verbose(self):
        """print("7 is a prime number") → PASS for expected 'prime'."""
        self.assertTrue(ok('7 is a prime number\n', 'prime'))

    def test_python_prime_substring_trap(self):
        """A word containing 'prime' as prefix/suffix must not trigger PASS."""
        # 'primal' — 'prime' not present as whole word
        self.assertFalse(ok('primal number\n', 'prime'))

    # ── C-style output (same stdout capture path) ────────────────────────────

    def test_c_printf_odd(self):
        """printf("n is odd\\n") → 'n is odd\n' → PASS."""
        self.assertTrue(ok('n is odd\n', 'odd'))

    def test_c_printf_not_odd(self):
        """printf("n is not odd\\n") → FAIL."""
        self.assertFalse(ok('n is not odd\n', 'odd'))

    def test_c_printf_exact_even(self):
        self.assertTrue(ok('even\n', 'even'))

    def test_c_printf_positive_sentence(self):
        self.assertTrue(ok('the number is positive\n', 'positive'))

    # ── Java-style output (same stdout capture path) ─────────────────────────

    def test_java_sout_odd(self):
        """System.out.println("n is a odd number") → PASS."""
        self.assertTrue(ok('n is a odd number\n', 'odd'))

    def test_java_sout_not_prime(self):
        """System.out.println("not a prime number") → PASS for 'not prime'."""
        self.assertTrue(ok('not a prime number\n', 'not prime'))

    def test_java_sout_prime_vs_not_prime(self):
        """System.out.println("prime") → FAIL for expected 'not prime'."""
        self.assertFalse(ok('prime\n', 'not prime'))

    def test_java_multiline_strict(self):
        """Multi-line Java output must match exactly (order matters)."""
        actual = '6x1=6\n6x2=12\n6x3=18\n6x4=24\n6x5=30\n6x6=36\n'
        expected = '6x1=6\n6x2=12\n6x3=18\n6x4=24\n6x5=30\n6x6=36'
        self.assertTrue(ok(actual, expected))

    def test_java_multiline_wrong_order(self):
        self.assertFalse(ok('6x2=12\n6x1=6\n', '6x1=6\n6x2=12'))

    # ── Error / empty-output cases ───────────────────────────────────────────

    def test_empty_output_fails_odd(self):
        """Empty output (e.g., program produces no stdout) → FAIL."""
        self.assertFalse(ok('', 'odd'))

    def test_empty_output_fails_even(self):
        self.assertFalse(ok('', 'even'))

    def test_whitespace_only_fails_odd(self):
        """Output of only whitespace → FAIL (normalises to empty)."""
        self.assertFalse(ok('   \n\n  ', 'odd'))


if __name__ == '__main__':
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
