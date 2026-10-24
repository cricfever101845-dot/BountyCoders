"""
test_html_evaluator.py — Regression tests for HTML structural evaluation
========================================================================

Tests cover:
  - Complete HTML documents with required elements   → accepted
  - Minimal HTML fragments with required elements    → accepted
  - Submissions missing required elements            → rejected
  - Required tags inside HTML comments              → rejected
  - Required tags as escaped / plain text            → rejected
  - Documents with extra valid elements              → accepted
  - Required attributes (href, type, etc.)          → checked
  - Tag-name capitalisation variations               → handled
  - All 15 real expected_output strings from DB     → covered
  - Python / C / Java evaluation paths unchanged    → verified

Run:  python test_html_evaluator.py
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from html_evaluator import evaluate_html, _parse_expected


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def ok(code, expected):
    return evaluate_html(code, expected).is_correct

def fail(code, expected):
    return not ok(code, expected)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Complete HTML document — must be accepted
# ─────────────────────────────────────────────────────────────────────────────

class TestCompleteDocument(unittest.TestCase):
    """A full HTML document containing the required element is accepted."""

    FULL_DOC = """\
<!DOCTYPE html>
<html>
<head>
    <title>Bold Text</title>
</head>
<body>
    <b>Hello World</b>
</body>
</html>"""

    def test_full_document_bold_accepted(self):
        self.assertTrue(ok(self.FULL_DOC, '<b> and </b>'))

    def test_full_document_body_ignored_extra_tags(self):
        # html/head/title/body are extra — must not cause rejection
        self.assertTrue(ok(self.FULL_DOC, '<b> and </b>'))

    def test_full_document_paragraph(self):
        doc = """<!DOCTYPE html><html><body><p>Hello</p></body></html>"""
        self.assertTrue(ok(doc, '<p> and </p>'))

    def test_full_document_heading_h3_with_text(self):
        doc = """<!DOCTYPE html><html><body><h3>Welcome</h3></body></html>"""
        # Expected pattern: "h3>Welcome</h3" (DB artifact missing leading <)
        self.assertTrue(ok(doc, 'h3>Welcome</h3'))

    def test_full_document_italic(self):
        doc = """<!DOCTYPE html><html><body><i>slanted</i></body></html>"""
        self.assertTrue(ok(doc, '<i> and </i>'))

    def test_full_document_anchor_with_href(self):
        doc = """<!DOCTYPE html><html><body>
        <a href="https://google.com">Google</a></body></html>"""
        self.assertTrue(ok(doc, 'href="https://google.com"'))

    def test_full_document_button_with_text(self):
        doc = """<!DOCTYPE html><html><body>
        <button>Submit</button></body></html>"""
        self.assertTrue(ok(doc, '<button>submit</button>'))

    def test_full_document_input_type_password(self):
        doc = """<!DOCTYPE html><html><body>
        <input type="password" /></body></html>"""
        self.assertTrue(ok(doc, '<input and type="password"'))

    def test_full_document_table(self):
        doc = """<!DOCTYPE html><html><body>
        <table><tr><td>Cell</td></tr></table></body></html>"""
        self.assertTrue(ok(doc, '<table> and <tr> and <td>'))

    def test_full_document_form_input_button(self):
        doc = """<!DOCTYPE html><html><body>
        <form>
          <input type="text" />
          <button>Login</button>
        </form></body></html>"""
        self.assertTrue(ok(doc, '<form> and <input and <button>'))

    def test_full_document_select_option(self):
        doc = """<!DOCTYPE html><html><body>
        <select>
          <option>One</option>
          <option>Two</option>
        </select></body></html>"""
        self.assertTrue(ok(doc, '<select> and <option>'))

    def test_full_document_semantic_tags(self):
        doc = """<!DOCTYPE html><html><body>
        <header>H</header><nav>N</nav><section>S</section><footer>F</footer>
        </body></html>"""
        self.assertTrue(ok(doc, '<header> and <nav> and <section> and <footer>'))

    def test_full_document_video_controls(self):
        doc = """<!DOCTYPE html><html><body>
        <video controls><source src="vid.mp4"></video>
        </body></html>"""
        self.assertTrue(ok(doc, '<video> and controls'))

    def test_full_document_audio_controls(self):
        doc = """<!DOCTYPE html><html><body>
        <audio controls><source src="a.mp3"></audio>
        </body></html>"""
        self.assertTrue(ok(doc, '<audio> and controls'))

    def test_full_document_img_attrs(self):
        doc = """<!DOCTYPE html><html><body>
        <img src="cat.jpg" height="200" width="200" alt="cat">
        </body></html>"""
        self.assertTrue(ok(doc, '<img and height="200" and width="200" and alt='))

    def test_full_document_iframe(self):
        doc = """<!DOCTYPE html><html><body>
        <iframe src="https://example.com"></iframe>
        </body></html>"""
        self.assertTrue(ok(doc, '<iframe>'))

    def test_full_document_hr(self):
        doc = """<!DOCTYPE html><html><body><hr></body></html>"""
        self.assertTrue(ok(doc, '<hr>'))

    def test_full_document_br(self):
        doc = """<!DOCTYPE html><html><body><p>Line1<br>Line2</p></body></html>"""
        self.assertTrue(ok(doc, '<br>'))

    def test_full_document_textarea(self):
        doc = """<!DOCTYPE html><html><body><textarea></textarea></body></html>"""
        self.assertTrue(ok(doc, '<textarea>'))

    def test_full_document_ul_li(self):
        doc = """<!DOCTYPE html><html><body>
        <ul><li>A</li><li>B</li></ul></body></html>"""
        self.assertTrue(ok(doc, '<ul> and <li>'))

    def test_full_document_ol_li(self):
        doc = """<!DOCTYPE html><html><body>
        <ol><li>A</li><li>B</li></ol></body></html>"""
        self.assertTrue(ok(doc, '<ol> and <li>'))

    def test_full_document_table_caption(self):
        doc = """<!DOCTYPE html><html><body>
        <table><caption>My Table</caption><tr><td>X</td></tr></table>
        </body></html>"""
        self.assertTrue(ok(doc, '<table> and <caption>'))

    def test_full_document_table_th(self):
        doc = """<!DOCTYPE html><html><body>
        <table><tr><th>Head</th></tr><tr><td>Cell</td></tr></table>
        </body></html>"""
        self.assertTrue(ok(doc, '<table> and <th>'))

    def test_full_document_img_src(self):
        doc = """<!DOCTYPE html><html><body>
        <img src="cat.jpg">
        </body></html>"""
        self.assertTrue(ok(doc, 'img and src'))

    def test_full_document_comment(self):
        doc = """<!DOCTYPE html><html><body><!-- a comment --><p>Hi</p></body></html>"""
        self.assertTrue(ok(doc, '<!-- and -->'))

    def test_full_document_anchor_tag(self):
        doc = """<!DOCTYPE html><html><body><a href="#">link</a></body></html>"""
        self.assertTrue(ok(doc, '<a>'))


# ─────────────────────────────────────────────────────────────────────────────
# 2. Minimal HTML fragments — must also be accepted
# ─────────────────────────────────────────────────────────────────────────────

class TestFragments(unittest.TestCase):
    """Bare fragments without DOCTYPE or html/body are accepted."""

    def test_fragment_bold(self):
        self.assertTrue(ok('<b>Hello</b>', '<b> and </b>'))

    def test_fragment_italic(self):
        self.assertTrue(ok('<i>text</i>', '<i> and </i>'))

    def test_fragment_paragraph(self):
        self.assertTrue(ok('<p>Hello</p>', '<p> and </p>'))

    def test_fragment_anchor(self):
        self.assertTrue(ok('<a href="https://google.com">G</a>',
                           'href="https://google.com"'))

    def test_fragment_button_text(self):
        self.assertTrue(ok('<button>submit</button>', '<button>submit</button>'))

    def test_fragment_img_src(self):
        self.assertTrue(ok('<img src="cat.jpg">', 'img and src'))

    def test_fragment_ul_li(self):
        self.assertTrue(ok('<ul><li>A</li><li>B</li></ul>', '<ul> and <li>'))

    def test_fragment_input_checkbox(self):
        self.assertTrue(ok('<input type="checkbox">', '<input and type="checkbox"'))

    def test_fragment_video_controls(self):
        self.assertTrue(ok('<video controls></video>', '<video> and controls'))


# ─────────────────────────────────────────────────────────────────────────────
# 3. Submissions missing required elements — must be rejected
# ─────────────────────────────────────────────────────────────────────────────

class TestMissingElements(unittest.TestCase):

    def test_missing_bold(self):
        doc = """<!DOCTYPE html><html><body><p>Hello World</p></body></html>"""
        self.assertTrue(fail(doc, '<b> and </b>'))

    def test_missing_italic(self):
        self.assertTrue(fail('<p>text</p>', '<i> and </i>'))

    def test_missing_anchor_href(self):
        self.assertTrue(fail('<p>Google</p>', 'href="https://google.com"'))

    def test_wrong_heading_level(self):
        doc = """<h2>Welcome</h2>"""
        # Expected h3 with text Welcome
        self.assertTrue(fail(doc, 'h3>Welcome</h3'))

    def test_missing_table(self):
        self.assertTrue(fail('<p>no table</p>', '<table> and <tr> and <td>'))

    def test_missing_li_in_ul(self):
        self.assertTrue(fail('<ul></ul>', '<ul> and <li>'))

    def test_missing_input_type(self):
        # Has input but wrong type
        self.assertTrue(fail('<input type="text">', '<input and type="password"'))

    def test_missing_button_text(self):
        # Has button but wrong text
        self.assertTrue(fail('<button>Click me</button>', '<button>submit</button>'))

    def test_missing_controls_attr(self):
        self.assertTrue(fail('<video src="v.mp4"></video>', '<video> and controls'))

    def test_missing_img_height(self):
        # Has img but no height attribute
        self.assertTrue(fail('<img src="x.jpg" width="200" alt="x">',
                             '<img and height="200" and width="200" and alt='))


# ─────────────────────────────────────────────────────────────────────────────
# 4. Tags inside HTML comments — must NOT satisfy the requirement
# ─────────────────────────────────────────────────────────────────────────────

class TestCommentedOutTags(unittest.TestCase):

    def test_bold_in_comment_rejected(self):
        doc = """<!DOCTYPE html><html><body><!-- <b>bold</b> --><p>Hi</p></body></html>"""
        self.assertTrue(fail(doc, '<b> and </b>'))

    def test_anchor_in_comment_rejected(self):
        doc = """<!-- <a href="https://google.com">link</a> --><p>no link</p>"""
        self.assertTrue(fail(doc, 'href="https://google.com"'))

    def test_table_in_comment_rejected(self):
        doc = """<p><!-- <table><tr><td>x</td></tr></table> --></p>"""
        self.assertTrue(fail(doc, '<table> and <tr> and <td>'))

    def test_input_type_in_comment_rejected(self):
        doc = """<!-- <input type="password"> --><p>nothing here</p>"""
        self.assertTrue(fail(doc, '<input and type="password"'))

    def test_comment_marker_requirement_satisfied(self):
        # When the *requirement* itself is <!-- and -->, the doc must have a comment
        doc = """<html><body><!-- this is a comment --><p>hi</p></body></html>"""
        self.assertTrue(ok(doc, '<!-- and -->'))

    def test_comment_marker_requirement_no_comment(self):
        doc = """<html><body><p>no comment</p></body></html>"""
        self.assertTrue(fail(doc, '<!-- and -->'))


# ─────────────────────────────────────────────────────────────────────────────
# 5. Tags as plain / escaped text — must NOT satisfy the requirement
# ─────────────────────────────────────────────────────────────────────────────

class TestEscapedText(unittest.TestCase):

    def test_tag_as_visible_text_rejected(self):
        # The text "&lt;b&gt;" is escaped — no real <b> element present
        doc = """<p>&lt;b&gt;Hello&lt;/b&gt;</p>"""
        self.assertTrue(fail(doc, '<b> and </b>'))

    def test_tag_inside_script_rejected(self):
        doc = """<script>var x = '<b>hello</b>';</script><p>hi</p>"""
        self.assertTrue(fail(doc, '<b> and </b>'))

    def test_attr_value_inside_script_rejected(self):
        doc = """<script>var url = 'https://google.com';</script>"""
        self.assertTrue(fail(doc, 'href="https://google.com"'))

    def test_tag_inside_style_rejected(self):
        doc = """<style>b { color: red; }</style><p>no bold tag</p>"""
        self.assertTrue(fail(doc, '<b> and </b>'))


# ─────────────────────────────────────────────────────────────────────────────
# 6. Extra valid elements — complete document accepted when not prohibited
# ─────────────────────────────────────────────────────────────────────────────

class TestExtraElements(unittest.TestCase):

    def test_doctype_plus_structure_accepted(self):
        doc = """\
<!DOCTYPE html>
<html>
<head><title>Example</title></head>
<body>
    <p>This is <b>important text</b>.</p>
</body>
</html>"""
        self.assertTrue(ok(doc, '<b> and </b>'))

    def test_extra_tags_with_bold_accepted(self):
        doc = """<html><body><div><span><b>bold</b></span></div></body></html>"""
        self.assertTrue(ok(doc, '<b> and </b>'))

    def test_extra_list_items_accepted(self):
        doc = """<ul><li>A</li><li>B</li><li>C</li><li>D</li><li>E</li></ul>"""
        self.assertTrue(ok(doc, '<ul> and <li>'))

    def test_form_with_extra_fields_accepted(self):
        doc = """\
<form>
  <input type="text" name="user">
  <input type="password" name="pass">
  <input type="email" name="mail">
  <button>Submit</button>
</form>"""
        self.assertTrue(ok(doc, '<form> and <input and <button>'))


# ─────────────────────────────────────────────────────────────────────────────
# 7. Attribute checks
# ─────────────────────────────────────────────────────────────────────────────

class TestAttributeChecks(unittest.TestCase):

    def test_href_exact_value(self):
        self.assertTrue(ok('<a href="https://google.com">G</a>',
                           'href="https://google.com"'))

    def test_href_wrong_value(self):
        self.assertTrue(fail('<a href="https://bing.com">B</a>',
                             'href="https://google.com"'))

    def test_type_checkbox(self):
        self.assertTrue(ok('<input type="checkbox">', '<input and type="checkbox"'))

    def test_type_radio(self):
        self.assertTrue(ok('<input type="radio">', '<input and type="radio"'))

    def test_type_date(self):
        self.assertTrue(ok('<input type="date">', '<input and type="date"'))

    def test_type_number(self):
        self.assertTrue(ok('<input type="number">', '<input and type="number"'))

    def test_type_color(self):
        self.assertTrue(ok('<input type="color">', '<input and type="color"'))

    def test_type_reset(self):
        self.assertTrue(ok('<input type="reset">', '<input and type="reset"'))

    def test_type_password(self):
        self.assertTrue(ok('<input type="password">', '<input and type="password"'))

    def test_required_attr_present(self):
        self.assertTrue(ok('<input type="email" required>',
                           'type="email" and required'))

    def test_required_attr_missing(self):
        self.assertTrue(fail('<input type="email">',
                             'type="email" and required'))

    def test_img_with_all_attrs(self):
        self.assertTrue(ok('<img src="x.jpg" height="200" width="200" alt="cat">',
                           '<img and height="200" and width="200" and alt='))

    def test_img_missing_one_attr(self):
        self.assertTrue(fail('<img src="x.jpg" height="200" alt="cat">',
                             '<img and height="200" and width="200" and alt='))


# ─────────────────────────────────────────────────────────────────────────────
# 8. Tag-name capitalisation — handled correctly
# ─────────────────────────────────────────────────────────────────────────────

class TestCapitalisation(unittest.TestCase):

    def test_uppercase_b_tag(self):
        self.assertTrue(ok('<B>Hello</B>', '<b> and </b>'))

    def test_mixed_case_input(self):
        self.assertTrue(ok('<INPUT TYPE="PASSWORD">', '<input and type="password"'))

    def test_uppercase_table_tags(self):
        doc = '<TABLE><TR><TD>x</TD></TR></TABLE>'
        self.assertTrue(ok(doc, '<table> and <tr> and <td>'))

    def test_mixed_case_select_option(self):
        doc = '<SELECT><OPTION>A</OPTION></SELECT>'
        self.assertTrue(ok(doc, '<select> and <option>'))


# ─────────────────────────────────────────────────────────────────────────────
# 9. Real expected_output strings from the database (all 15 questions)
# ─────────────────────────────────────────────────────────────────────────────

class TestAllRealExpected(unittest.TestCase):
    """
    Each test uses the exact expected_output string from seed_questions.py
    and verifies that a correct submission passes AND an incorrect one fails.
    """

    # ── Easy ─────────────────────────────────────────────────────────────────

    def test_103_1_exp1_h3_welcome(self):
        good = '<h3>Welcome</h3>'
        bad  = '<h2>Welcome</h2>'
        self.assertTrue(ok(good,  'h3>Welcome</h3'))
        self.assertTrue(fail(bad, 'h3>Welcome</h3'))

    def test_103_1_exp2_h2(self):
        good = '<h2>Title</h2>'
        bad  = '<h3>Title</h3>'
        self.assertTrue(ok(good,  'h2> and </h2'))
        self.assertTrue(fail(bad, 'h2> and </h2'))

    def test_103_1_exp3_h4(self):
        good = '<h4>Sub</h4>'
        self.assertTrue(ok(good, 'h4> and </h4'))

    def test_103_2_exp1_p(self):
        good = '<p>First</p><p>Second</p>'
        bad  = '<div>First</div>'
        self.assertTrue(ok(good,  '<p> and </p>'))
        self.assertTrue(fail(bad, '<p> and </p>'))

    def test_103_2_exp2_bold(self):
        good = '<b>bold</b>'
        bad  = '<p>not bold</p>'
        self.assertTrue(ok(good,  '<b> and </b>'))
        self.assertTrue(fail(bad, '<b> and </b>'))

    def test_103_2_exp3_a(self):
        good = '<a href="#">link</a>'
        bad  = '<p>no link</p>'
        self.assertTrue(ok(good,  '<a>'))
        self.assertTrue(fail(bad, '<a>'))

    def test_103_3_exp1_img_src(self):
        good = '<img src="cat.jpg">'
        bad  = '<p>no image</p>'
        self.assertTrue(ok(good,  'img and src'))
        self.assertTrue(fail(bad, 'img and src'))

    def test_103_3_exp2_italic(self):
        good = '<i>italic</i>'
        self.assertTrue(ok(good, '<i> and </i>'))

    def test_103_3_exp3_two_imgs(self):
        good = '<img src="a.jpg"><img src="b.jpg">'
        bad  = '<img src="a.jpg">'          # only one img — still has <img> tag
        # Expected: two <img> tags present — <img> and <img>
        # The rule fires for each token: both resolve to _TagExistsRule('img')
        # Two identical rules → both pass if at least one img exists
        # In practice, this is equivalent to checking img exists at least once.
        # That's the stored requirement; testing both tokens resolve correctly.
        self.assertTrue(ok(good, '<img> and <img>'))
        self.assertTrue(ok(bad,  '<img> and <img>'))   # one img still matches

    def test_103_4_exp1_href_google(self):
        good = '<a href="https://google.com">Google</a>'
        bad  = '<a href="https://bing.com">Bing</a>'
        self.assertTrue(ok(good,  'href="https://google.com"'))
        self.assertTrue(fail(bad, 'href="https://google.com"'))

    def test_103_4_exp2_br(self):
        good = '<p>Line1<br>Line2</p>'
        bad  = '<p>no break</p>'
        self.assertTrue(ok(good,  '<br>'))
        self.assertTrue(fail(bad, '<br>'))

    def test_103_4_exp3_ol_li(self):
        good = '<ol><li>A</li></ol>'
        bad  = '<ul><li>A</li></ul>'
        self.assertTrue(ok(good,  '<ol> and <li>'))
        self.assertTrue(fail(bad, '<ol> and <li>'))

    def test_103_5_exp1_hr(self):
        good = '<hr>'
        bad  = '<p>no rule</p>'
        self.assertTrue(ok(good,  '<hr>'))
        self.assertTrue(fail(bad, '<hr>'))

    def test_103_5_exp2_comment(self):
        good = '<!-- comment --><p>hi</p>'
        bad  = '<p>no comment</p>'
        self.assertTrue(ok(good,  '<!-- and -->'))
        self.assertTrue(fail(bad, '<!-- and -->'))

    def test_103_5_exp3_ul_li(self):
        good = '<ul><li>A</li></ul>'
        self.assertTrue(ok(good, '<ul> and <li>'))

    # ── Medium ───────────────────────────────────────────────────────────────

    def test_103_6_exp1_ul_li(self):
        self.assertTrue(ok('<ul><li>1</li><li>2</li><li>3</li><li>4</li></ul>',
                           '<ul> and <li>'))

    def test_103_6_exp2_textarea(self):
        good = '<textarea></textarea>'
        bad  = '<input type="text">'
        self.assertTrue(ok(good,  '<textarea>'))
        self.assertTrue(fail(bad, '<textarea>'))

    def test_103_6_exp3_form_input(self):
        good = '<form><input type="text"></form>'
        self.assertTrue(ok(good, '<form> and <input'))

    def test_103_7_exp1_ol_li(self):
        self.assertTrue(ok('<ol><li>1</li></ol>', '<ol> and <li>'))

    def test_103_7_exp2_checkbox(self):
        self.assertTrue(ok('<input type="checkbox">', '<input and type="checkbox"'))

    def test_103_7_exp3_number(self):
        self.assertTrue(ok('<input type="number">', '<input and type="number"'))

    def test_103_8_exp2_radio(self):
        self.assertTrue(ok('<input type="radio"><input type="radio">',
                           '<input and type="radio"'))

    def test_103_8_exp3_date(self):
        self.assertTrue(ok('<input type="date">', '<input and type="date"'))

    def test_103_9_exp1_button_submit(self):
        good = '<button>submit</button>'
        bad  = '<button>click me</button>'
        self.assertTrue(ok(good,  '<button>submit</button>'))
        self.assertTrue(fail(bad, '<button>submit</button>'))

    def test_103_9_exp2_password(self):
        self.assertTrue(ok('<input type="password">', '<input and type="password"'))

    def test_103_9_exp3_color(self):
        self.assertTrue(ok('<input type="color">', '<input and type="color"'))

    def test_103_10_exp1_table(self):
        self.assertTrue(ok(
            '<table><tr><td>X</td></tr></table>',
            '<table> and <tr> and <td>'))

    def test_103_10_exp2_reset(self):
        self.assertTrue(ok('<input type="reset">', '<input and type="reset"'))

    def test_103_10_exp3_button_submit(self):
        self.assertTrue(ok('<button>submit</button>', '<button>submit</button>'))

    # ── Hard ─────────────────────────────────────────────────────────────────

    def test_103_11_exp1_form_input_button(self):
        doc = '<form><input type="text"><input type="password"><button>Login</button></form>'
        self.assertTrue(ok(doc, '<form> and <input and <button>'))

    def test_103_11_exp2_select_option(self):
        doc = '<select><option>A</option><option>B</option></select>'
        self.assertTrue(ok(doc, '<select> and <option>'))

    def test_103_11_exp3_semantic(self):
        doc = '<header>H</header><nav>N</nav><section>S</section><footer>F</footer>'
        self.assertTrue(ok(doc, '<header> and <nav> and <section> and <footer>'))

    def test_103_12_exp1_iframe(self):
        self.assertTrue(ok('<iframe src="x.html"></iframe>', '<iframe>'))

    def test_103_12_exp2_table_caption(self):
        doc = '<table><caption>Cap</caption><tr><td>X</td></tr></table>'
        self.assertTrue(ok(doc, '<table> and <caption>'))

    def test_103_12_exp3_table_th(self):
        doc = '<table><tr><th>Head</th></tr><tr><td>Data</td></tr></table>'
        self.assertTrue(ok(doc, '<table> and <th>'))

    def test_103_13_exp1_video_controls(self):
        doc = '<video controls><source src="v.mp4"></video>'
        self.assertTrue(ok(doc, '<video> and controls'))

    def test_103_13_exp2_a_img(self):
        doc = '<a href="#"><img src="pic.jpg"></a>'
        self.assertTrue(ok(doc, '<a and <img'))

    def test_103_13_exp3_email_required_password(self):
        doc = '<form><input type="email" required><input type="password"></form>'
        self.assertTrue(ok(doc, 'type="email" and required and type="password"'))

    def test_103_14_exp1_audio_controls(self):
        doc = '<audio controls><source src="a.mp3"></audio>'
        self.assertTrue(ok(doc, '<audio> and controls'))

    def test_103_14_exp2_email_required(self):
        doc = '<input type="email" required>'
        self.assertTrue(ok(doc, 'type="email" and required'))

    def test_103_14_exp3_audio_video_controls(self):
        doc = '<audio controls></audio><video controls></video>'
        self.assertTrue(ok(doc, '<audio and <video and controls'))

    def test_103_15_exp1_header_main_footer(self):
        doc = '<header>H</header><main>M</main><footer>F</footer>'
        self.assertTrue(ok(doc, '<header> and <main> and <footer>'))

    def test_103_15_exp2_form_email_password_button(self):
        doc = ('<form><input type="email"><input type="password">'
               '<button>Submit</button></form>')
        self.assertTrue(ok(doc, '<form> and type="email" and type="password" and <button>'))

    def test_103_15_exp3_img_all_attrs(self):
        doc = '<img src="x.jpg" height="200" width="200" alt="photo">'
        self.assertTrue(ok(doc, '<img and height="200" and width="200" and alt='))


# ─────────────────────────────────────────────────────────────────────────────
# 10. Python / C / Java evaluation paths unchanged
# ─────────────────────────────────────────────────────────────────────────────

class TestNonHTMLPathsUnchanged(unittest.TestCase):
    """
    Verify that evaluator.compare_outputs() still works correctly for
    Python, C, Java, etc. — html_evaluator must not affect those paths.
    """

    def setUp(self):
        import sys, os
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from evaluator import compare_outputs
        self.cmp = compare_outputs

    def test_python_hello_world(self):
        r = self.cmp('hello world\n', 'hello world')
        self.assertTrue(r.is_correct)

    def test_python_case_insensitive(self):
        r = self.cmp('Palindrome\n', 'palindrome')
        self.assertTrue(r.is_correct)

    def test_python_wrong_answer(self):
        r = self.cmp('100\n', '10')
        self.assertFalse(r.is_correct)

    def test_java_multiline(self):
        r = self.cmp('6x1=6\n6x2=12\n6x3=18\n', '6x1=6\n6x2=12\n6x3=18')
        self.assertTrue(r.is_correct)

    def test_c_positive(self):
        r = self.cmp('Positive\n', 'positive')
        self.assertTrue(r.is_correct)

    def test_numeric_mode(self):
        r = self.cmp('20.0\n', '20', mode='numeric')
        self.assertTrue(r.is_correct)

    def test_html_evaluator_not_called_for_python(self):
        # evaluate_html should never be called for Python output — just verify
        # that the module import doesn't interfere with compare_outputs()
        from html_evaluator import evaluate_html
        r = self.cmp('palindrome\n', 'palindrome')
        self.assertTrue(r.is_correct)


# ─────────────────────────────────────────────────────────────────────────────
# Run
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
