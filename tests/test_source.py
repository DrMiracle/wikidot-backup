"""Tests for canonical Wikidot source parsing."""

import pytest

from wikidot_backup.wikidot.source import (
    parse_current_source_response,
    parse_revision_source_response,
)


def test_current_source_removes_transport_wrapper() -> None:
    """Current source should discard ViewSourceModule wrapper formatting."""
    body = """
<h1>Page source</h1>
<div class="page-source">
\t[[include <a href="/credit:start">credit:start</a>]]<br />
**Article:** Test<br />
[[include <a href="/credit:end">credit:end</a>]]
</div>
"""

    source = parse_current_source_response(body)

    assert source == (
        "[[include credit:start]]\n"
        "**Article:** Test\n"
        "[[include credit:end]]"
    )


def test_revision_source_decodes_html_entities() -> None:
    """Historical source should restore characters escaped by Wikidot."""
    body = """
<h2>Revision source</h2>
<div class="page-source">
**Об&#039;єкт:** test<br />
&lt;literal&gt;
</div>
"""

    source = parse_revision_source_response(body)

    assert source == (
        "**Об'єкт:** test\n"
        "<literal>"
    )


def test_source_preserves_blank_lines() -> None:
    """Consecutive source line breaks must not be collapsed."""
    body = """
<div class="page-source">
first<br />
<br />
third
</div>
"""

    source = parse_revision_source_response(body)

    assert source == "first\n\nthird"


def test_source_normalizes_wikidot_nbsp() -> None:
    """Wikidot presentation NBSP entities should become ordinary spaces."""
    body = """
<div class="page-source">
hello&nbsp;world
</div>
"""

    source = parse_revision_source_response(body)

    assert source == "hello world"


def test_current_source_preserves_real_leading_tab() -> None:
    """Removing the wrapper tab must not remove source indentation."""
    body = """
<div class="page-source">
\t\tindented source
</div>
"""

    source = parse_current_source_response(body)

    # ViewSourceModule contributes the first tab; the second belongs to
    # the actual Wikidot source and must survive canonicalization.
    assert source == "\tindented source"


def test_source_preserves_trailing_source_newline() -> None:
    """A trailing Wikidot line break must not be stripped."""
    body = """
<div class="page-source">
content<br />
</div>
"""

    source = parse_revision_source_response(body)

    assert source == "content\n"


def test_current_and_revision_formats_produce_same_source() -> None:
    """Equivalent source from both Wikidot modules should canonicalize equally."""
    current_body = """
<h1>Page source</h1>
<div class="page-source">
\t[[include <a href="/credit:start">credit:start</a>]]<br />
**Об'єкт:** SCP-001<br />
<br />
Text&nbsp;here
</div>
"""

    revision_body = """
<h2>Revision source</h2>
<div class="page-source">
[[include credit:start]]<br />
**Об&#039;єкт:** SCP-001<br />
<br />
Text&nbsp;here
</div>
"""

    current = parse_current_source_response(
        current_body
    )
    revision = parse_revision_source_response(
        revision_body
    )

    assert current == revision


@pytest.mark.parametrize(
    "parser",
    [
        parse_current_source_response,
        parse_revision_source_response,
    ],
)
def test_source_requires_page_source_container(parser) -> None:
    """Source parsers should fail rather than silently return invalid data."""
    body = "<div>not a source response</div>"

    with pytest.raises(
        RuntimeError,
        match="Could not find Wikidot source content",
    ):
        parser(body)
