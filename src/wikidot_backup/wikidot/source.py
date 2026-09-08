"""Parsing helpers for Wikidot source-module responses."""

from __future__ import annotations

from bs4 import BeautifulSoup
from bs4.element import NavigableString, PageElement, Tag


def parse_current_source_response(body: str) -> str:
    """Extract canonical source from a current-page source response.

    ViewSourceModule adds one indentation tab before the source content.
    That transport-specific wrapper is removed after common source decoding.

    Args:
        body:
            HTML fragment returned by ViewSourceModule.

    Returns:
        Canonical Wikidot source text.
    """
    source = _parse_source_response(body)

    return source.removeprefix("\t")


def parse_revision_source_response(body: str) -> str:
    """Extract canonical source from a historical revision response.

    Args:
        body:
            HTML fragment returned by PageSourceModule.

    Returns:
        Canonical Wikidot source text.
    """
    return _parse_source_response(body)


def _parse_source_response(body: str) -> str:
    """Decode source shared by Wikidot source-view modules.

    Source line breaks are represented by ``<br>`` elements. Literal
    CR/LF characters in surrounding HTML text nodes are presentation
    formatting produced by the module and are therefore discarded.

    Args:
        body:
            HTML fragment containing a ``div.page-source`` element.

    Returns:
        Decoded source text.

    Raises:
        RuntimeError:
            If the source container is absent.
    """
    # Wikidot uses &nbsp; as part of its HTML source presentation.
    # Normalize it before parsing so current and historical sources use
    # the same representation.
    body = body.replace("&nbsp;", " ")

    soup = BeautifulSoup(
        body,
        "html.parser",
    )

    container = soup.select_one(
        "div.page-source"
    )

    if container is None:
        raise RuntimeError(
            "Could not find Wikidot source content."
        )

    return "".join(
        _decode_source_node(child)
        for child in container.children
    )


def _decode_source_node(
    node: PageElement,
) -> str:
    """Decode one node from Wikidot's HTML representation of source."""
    if isinstance(node, NavigableString):
        # Actual source line breaks are represented by <br>. CR/LF
        # characters in text nodes come from formatting of the AMC response.
        return (
            str(node)
            .replace("\r", "")
            .replace("\n", "")
        )

    if isinstance(node, Tag):
        if node.name == "br":
            return "\n"

        # ViewSourceModule may insert elements such as <a> inside otherwise
        # plain source text. Decode their textual children recursively.
        return "".join(
            _decode_source_node(child)
            for child in node.children
        )

    return ""