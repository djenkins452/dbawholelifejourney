"""
Fixed-header / single-scroll shell — footer-follows-content contract.

Codifies the layout invariants introduced when the global header was made
permanently visible (commit add18eba) and the follow-up fix for the footer
regression (this change).

Background / incident:
  Making the desktop shell a non-scrolling `100vh` flex column (so the header
  stays pinned and only `.desktop-main-area` scrolls) exposed a latent bug:
  `.main-content` used `flex: 1` (i.e. `flex: 1 1 0%`). With `flex-basis: 0%`
  the main box is sized to the flex column's free space (clamped by
  `min-height`) and IGNORES its own content height. Tall page content then
  overflowed the box while the footer — the next flex sibling — sat at the
  box's bottom edge, i.e. IN THE MIDDLE of the content (reported on the Health
  meals page: footer rendered between meal sections, with content continuing
  below it). The fix is `flex: 1 0 auto`: the box sizes to its content
  (`flex-basis: auto`) and never shrinks below it (`flex-shrink: 0`), so the
  footer always follows all content; `flex-grow: 1` still fills the viewport on
  short pages so the footer rests at the bottom.

Two things must hold and are guarded here:

  1. DOM ownership (templates/base.html): the footer is emitted INSIDE
     `.desktop-main-area`, AFTER the `<main class="main-content">` that wraps
     `{% block content %}`. It must never be a sibling that can be laid out
     independently of the page content, and never precede the content.

  2. CSS sizing (static/css/desktop-nav.css): `.main-content` in the desktop
     shell uses `flex: 1 0 auto`, NOT a content-ignoring `flex: 1` /
     `flex: 1 1 0` / `flex: 1 1 0%`.

The companion header invariants (the shell is capped and the root is not a
scroll container) are asserted too, so a future edit can't silently unpick the
single-scroll behavior that the footer fix depends on.

Simple substring/regex parsing is deliberate (matching
test_visual_truth_contract.py); the contract is narrow enough that a CSS/HTML
AST dependency would be more risk than value.
"""

import re
from pathlib import Path

from django.test import SimpleTestCase

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_BASE_HTML = _REPO_ROOT / "templates" / "base.html"
_DESKTOP_NAV_CSS = _REPO_ROOT / "static" / "css" / "desktop-nav.css"
_MAIN_CSS = _REPO_ROOT / "static" / "css" / "main.css"


class FooterFollowsContentDomTest(SimpleTestCase):
    """The footer is the last child of the scroll region, after the content."""

    def setUp(self):
        self.html = _BASE_HTML.read_text(encoding="utf-8")

    def test_footer_is_inside_scroll_region_after_main_content(self):
        idx_main_area = self.html.find('class="desktop-main-area"')
        idx_main_content = self.html.find('class="main-content"')
        idx_block_content = self.html.find("{% block content %}")
        idx_main_close = self.html.find("</main>")
        idx_footer = self.html.find('components/footer.html')
        # The assistant panel is the next SIBLING after `.desktop-main-area`
        # closes; the footer must come before it (i.e. still inside the region).
        idx_assistant = self.html.find('components/assistant_panel.html')

        for name, idx in [
            ("desktop-main-area", idx_main_area),
            ("main-content", idx_main_content),
            ("{% block content %}", idx_block_content),
            ("</main>", idx_main_close),
            ("components/footer.html", idx_footer),
            ("components/assistant_panel.html", idx_assistant),
        ]:
            self.assertNotEqual(
                idx, -1, f"base.html no longer contains expected marker: {name}"
            )

        # Region opens, then main-content, then the content block, then main
        # closes, then the footer — and the footer is still before the
        # assistant panel (which lives OUTSIDE the scroll region).
        self.assertLess(idx_main_area, idx_main_content,
                        "main-content must be inside .desktop-main-area")
        self.assertLess(idx_main_content, idx_block_content,
                        "{% block content %} must be inside <main class=main-content>")
        self.assertLess(idx_block_content, idx_main_close,
                        "page content block must be inside <main>")
        self.assertLess(idx_main_close, idx_footer,
                        "footer must be emitted AFTER </main> (after all page "
                        "content), never before or between content")
        self.assertLess(idx_footer, idx_assistant,
                        "footer must be inside .desktop-main-area (before the "
                        "assistant panel, which is a sibling of the scroll region)")

    def test_single_footer_include_in_layout(self):
        # Exactly one global footer include in the shell — a second, differently
        # placed include is how a footer ends up in the wrong flow.
        self.assertEqual(
            self.html.count('components/footer.html'), 1,
            "base.html must include components/footer.html exactly once",
        )


class MainContentFlexSizingTest(SimpleTestCase):
    """`.main-content` must size to its content so the footer follows it."""

    def setUp(self):
        self.css = _DESKTOP_NAV_CSS.read_text(encoding="utf-8")

    def _main_content_rule_body(self):
        # Grab the declaration block of `body.has-desktop-nav .main-content`.
        m = re.search(
            r"body\.has-desktop-nav\s+\.main-content\s*\{(?P<body>[^}]*)\}",
            self.css,
        )
        self.assertIsNotNone(
            m,
            "desktop-nav.css must define a `body.has-desktop-nav .main-content` rule",
        )
        return m.group("body")

    def test_main_content_flex_is_grow_no_shrink_auto_basis(self):
        body = self._main_content_rule_body()
        flex_decls = re.findall(r"flex\s*:\s*([^;]+);", body)
        self.assertTrue(
            flex_decls,
            "`.main-content` must declare a `flex` value in the desktop shell",
        )
        value = flex_decls[-1].strip()
        normalized = re.sub(r"\s+", " ", value).lower()
        self.assertEqual(
            normalized, "1 0 auto",
            "`.main-content` must be `flex: 1 0 auto` so it sizes to its content "
            "and the footer follows all content. A content-ignoring basis "
            "(`flex: 1`, `flex: 1 1 0`, `flex: 1 1 0%`) reintroduces the "
            f"footer-in-the-middle regression. Found: `flex: {value}`.",
        )


class SingleScrollShellTest(SimpleTestCase):
    """Guard the fixed-header single-scroll shell the footer fix depends on."""

    def setUp(self):
        self.desktop_css = _DESKTOP_NAV_CSS.read_text(encoding="utf-8")
        self.main_css = _MAIN_CSS.read_text(encoding="utf-8")

    @staticmethod
    def _strip_comments(css):
        return re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)

    def _rule_body(self, css, selector_regex):
        # selector_regex must NOT include the opening brace.
        m = re.search(selector_regex + r"\s*\{(?P<body>[^}]*)\}", css)
        self.assertIsNotNone(m, f"expected CSS rule matching /{selector_regex}/")
        return re.sub(r"\s+", " ", m.group("body")).strip().lower()

    def test_desktop_shell_is_viewport_capped_and_clipped(self):
        body = self._rule_body(
            self._strip_comments(self.desktop_css), r"body\.has-desktop-nav"
        )
        self.assertIn("height: 100vh", body,
                      "desktop shell body must be capped to the viewport height")
        self.assertIn("overflow: hidden", body,
                      "desktop shell body must clip so .desktop-main-area is the "
                      "only scroll region")

    def test_root_is_not_a_scroll_container_on_desktop(self):
        # html:has(body.has-desktop-nav) { overflow-x: visible } removes the
        # phantom root scroll that could shove the pinned header off-screen.
        body = self._rule_body(
            self._strip_comments(self.desktop_css),
            r"html:has\(body\.has-desktop-nav\)",
        )
        self.assertIn("overflow-x: visible", body)

    def test_body_is_not_a_scroll_container(self):
        # <body> must NOT set overflow-x (that makes it a scroll container and
        # breaks the sticky mobile .site-header). Horizontal overflow is clipped
        # on <html> instead.
        css = self._strip_comments(self.main_css)
        m = re.search(r"(?<![\.\-\w])body\s*\{(?P<body>[^}]*)\}", css)
        self.assertIsNotNone(m, "main.css must define a base `body` rule")
        self.assertNotIn(
            "overflow-x", re.sub(r"\s+", " ", m.group("body")).lower(),
            "base `body` rule must not set overflow-x (keep it on <html>); "
            "overflow on <body> breaks the sticky global header",
        )
