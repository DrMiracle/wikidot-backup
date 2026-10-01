"""Static offline browsing for exported data, without executing archived HTML."""

from html import escape
from urllib.parse import quote, urljoin, urlsplit

from bs4 import BeautifulSoup

from wikidot_backup.models.forum_records import ForumPostRecord, ForumThreadRecord

ALLOWED_TAGS = {
    "p",
    "br",
    "div",
    "span",
    "blockquote",
    "pre",
    "code",
    "strong",
    "b",
    "em",
    "i",
    "u",
    "s",
    "del",
    "ins",
    "sub",
    "sup",
    "ul",
    "ol",
    "li",
    "dl",
    "dt",
    "dd",
    "table",
    "thead",
    "tbody",
    "tfoot",
    "tr",
    "th",
    "td",
    "a",
    "hr",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "details",
    "summary",
}


def safe_link(value: str, base_url: str) -> str | None:
    """Resolve remote relative links; exclude executable and local-file schemes."""
    resolved = urljoin(base_url.rstrip("/") + "/", value)
    return resolved if urlsplit(resolved).scheme.lower() in {"https", "http", "mailto"} else None


def render_post_html(content: str, base_url: str) -> str:
    """Render basic formatting; JSON retains original HTML for full fidelity."""
    soup = BeautifulSoup(content, "html.parser")
    for element in list(soup.find_all(True)):
        if element.name is None:
            continue
        if element.name in {"script", "style", "iframe", "object", "embed", "svg", "math"}:
            element.decompose()
        elif element.name == "img":
            url = safe_link(str(element.get("src", "")), base_url)
            label = "[Image not embedded: " + str(element.get("alt") or "image") + "]"
            replacement = soup.new_tag("a") if url else soup.new_tag("span")
            if url:
                replacement["href"] = url
            replacement.string = label
            element.replace_with(replacement)
        elif element.name not in ALLOWED_TAGS:
            element.unwrap()
        else:
            href = element.get("href") if element.name == "a" else None
            element.attrs = {}
            if href:
                url = safe_link(str(href), base_url)
                if url:
                    element["href"] = url
                    element["rel"] = "noreferrer noopener"
    return str(soup)


def link(path: str, label: str) -> str:
    """Create an escaped link to an exported relative path."""
    return f'<a href="{escape(quote(path, safe="/"), quote=True)}">{escape(label)}</a>'


def document(title: str, body: str) -> bytes:
    """Build a standalone page with no scripts or automatic external resources."""
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src &#39;none&#39;; '
        'style-src &#39;unsafe-inline&#39;; base-uri &#39;none&#39;; form-action &#39;none&#39;">'
        f"<title>{escape(title)}</title><style>"
        "body{font:16px/1.6 system-ui,sans-serif;max-width:960px;margin:2rem auto;padding:0 1rem}"
        "a{color:#175bbb}pre{white-space:pre-wrap;overflow-wrap:anywhere}"
        "article{border-left:3px solid #bbb;padding:1rem;margin:1rem 0}"
        ".warning{background:#fff3cd;padding:.7rem}small{color:#555}"
        "table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:.3rem}"
        f"</style></head><body><h1>{escape(title)}</h1>{body}</body></html>"
    ).encode()


def source_html(source: str, *, title: str, text_path: str, back_path: str) -> bytes:
    """Display exact source text with explicit UTF-8 instead of browser encoding guesses."""
    body = "<p>" + link(back_path, "Back") + " · " + link(text_path, "Original text file") + "</p>"
    # A newline immediately after <pre> is consumed by HTML parsing. Put an empty
    # span first so even a source beginning with a newline displays faithfully.
    body += "<pre><span></span>" + escape(source) + "</pre>"
    return document(title, body)


def discussion_html(
    thread: ForumThreadRecord, posts: list[ForumPostRecord], site_url: str, *, back_path: str
) -> bytes:
    """Show observed comments in stored display order, with explicit reply links."""
    by_id = {post.post_id: post for post in posts}
    body = "<p>" + link(back_path, "Back") + "</p>"
    body += "<p>Basic offline formatting. Original HTML is preserved in posts.jsonl. "
    body += "Images are links; external resources are not downloaded.</p>"
    body += "<p>" + link("thread.json", "Thread metadata") + " · "
    body += link("posts.jsonl", "Post records") + "</p>"
    observed = set(thread.observed_post_ids)
    groups = [
        ("Current discussion", [by_id[identifier] for identifier in thread.observed_post_ids]),
        (
            "Retained posts absent from the latest snapshot",
            [post for post in posts if post.post_id not in observed],
        ),
    ]
    for heading, group in groups:
        if not group:
            continue
        body += f"<h2>{heading}</h2>"
        for post in group:
            body += f'<article id="post-{post.post_id}">'
            if post.title:
                body += f"<h3>{escape(post.title)}</h3>"
            body += f"<small>{escape(post.created_by.name)} · {post.created_at.isoformat()}</small>"
            if post.parent_id is not None:
                body += (
                    f'<p>Reply to <a href="#post-{post.parent_id}">post {post.parent_id}</a></p>'
                )
            body += render_post_html(post.html, site_url) + "</article>"
    if not posts:
        body += "<p>No archived posts.</p>"
    return document(thread.title or f"Untitled thread {thread.thread_id}", body)
