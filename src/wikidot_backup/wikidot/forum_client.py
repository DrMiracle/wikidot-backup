"""Public forum endpoints, with explicit pagination and UTC timestamps."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlsplit

from bs4 import BeautifulSoup, Tag

from wikidot_backup.wikidot.amc import WikidotAmcClient
from wikidot_backup.wikidot.models import WikidotUserData


@dataclass(slots=True)
class WikidotForumCategoryData:
    """A category and the count advertised by the public forum index."""

    id: int
    group_position: int
    title: str
    description_html: str
    reported_threads: int


@dataclass(slots=True)
class WikidotForumPostData:
    """Rendered post or historical version; raw Wikidot source is unavailable."""

    id: int
    title: str
    html: str
    created_at: datetime
    created_by: WikidotUserData
    parent_id: int | None = None
    revision_id: int | None = None
    history_position: int | None = None


@dataclass(slots=True)
class WikidotForumThreadData:
    """Thread metadata and posts, plus original endpoint bodies for fidelity."""

    id: int
    title: str
    category_id: int | None
    reported_posts: int
    created_at: datetime
    created_by: WikidotUserData
    posts: list[WikidotForumPostData]
    responses: dict[str, str] = field(default_factory=dict)


def required(node: Tag | BeautifulSoup, selector: str) -> Tag:
    """Reject an unexpected response instead of interpreting it as empty data."""
    result = node.select_one(selector)
    if result is None:
        raise RuntimeError(f"Missing forum element: {selector}")

    return result


def timestamp(node: Tag) -> datetime:
    """Decode Wikidot's Unix timestamp independently of the local timezone."""
    date = required(node, ".odate")
    match = re.search(r"\btime_(\d+)\b", " ".join(date.get("class", [])))
    if match is None:
        raise RuntimeError("Missing forum timestamp")

    return datetime.fromtimestamp(int(match[1]), UTC)


def author(node: Tag) -> WikidotUserData:
    """Preserve displayed usernames; extract standard profile slugs explicitly."""
    user = required(node, ".printuser")
    links = user.select("a")
    link = links[-1] if links else None

    name = link.get_text() if link else user.get_text()
    match = re.search(r"userInfo\((\d+)\)", str(user))
    identifier = int(match[1]) if match else None

    if identifier is None and user.get("data-id"):
        identifier = int(user["data-id"])

    slug = None
    if link:
        url = urlsplit(str(link.get("href", "")))
        if url.hostname in {"www.wikidot.com", "wikidot.com"}:
            prefix = "/user:info/"
            if url.path.startswith(prefix):
                slug = url.path[len(prefix) :]

    return WikidotUserData(id=identifier, name=name, unix_name=slug)


def pagination(soup: BeautifulSoup, expected: int) -> int:
    """Follow the advertised pager, including empty trailing category pages."""
    pagers = soup.select(".pager")
    if not pagers:
        if expected != 1:
            raise RuntimeError("Forum pagination disappeared")
        return 1

    last = expected
    for pager in pagers:
        current = required(pager, ".current").get_text(strip=True)
        if current != str(expected):
            raise RuntimeError(f"Wrong forum page: expected {expected}, got {current}")

        for element in pager.select("a, .target, .current"):
            label = element.get_text(strip=True)
            if label.isdecimal():
                last = max(last, int(label))
            match = re.search(r"/p/(\d+)", str(element.get("href", "")))
            if match:
                last = max(last, int(match[1]))

    return last


class WikidotForumClient:
    """Use the existing retrying AMC layer; never call editing endpoints."""

    def __init__(self, amc: WikidotAmcClient) -> None:
        self.amc = amc

    def body(self, module: str, **params: str) -> str:
        response = self.amc.request(module, **params)
        body = response.get("body")
        if not isinstance(body, str):
            raise RuntimeError("Missing forum response body")
        return body

    def catalog(self) -> tuple[list[WikidotForumCategoryData], list[str], str]:
        """Return categories, group HTML, and the unchanged public index body."""
        body = self.body("forum/ForumStartModule", hidden="true")
        soup = BeautifulSoup(body, "html.parser")
        box = required(soup, ".forum-start-box")

        categories = []
        groups = []
        seen = set()
        for position, group in enumerate(box.select(".forum-group")):
            groups.append(str(required(group, ".head")))
            for row in group.select("table tr"):
                if "head" in row.get("class", []):
                    continue
                link = required(row, "td.name a")
                match = re.search(r"/c-(\d+)", str(link.get("href", "")))
                if match is None or int(match[1]) in seen:
                    raise RuntimeError("Missing or duplicate forum category ID")

                seen.add(int(match[1]))
                categories.append(
                    WikidotForumCategoryData(
                        id=int(match[1]),
                        group_position=position,
                        title=link.get_text(),
                        description_html=str(required(row, ".description")),
                        reported_threads=int(required(row, "td.threads").get_text()),
                    )
                )

        return categories, groups, body

    def category_threads(self, category_id: int) -> list[int]:
        """Fetch every advertised page, rejecting duplicates and moving pagers."""
        ids = []
        seen = set()
        page = 1
        last = None
        while True:
            body = self.body("forum/ForumViewCategoryModule", c=str(category_id), p=str(page))
            soup = BeautifulSoup(body, "html.parser")
            table = required(required(soup, ".forum-category-box"), "table.table")
            advertised = pagination(soup, page)
            if last is not None and advertised != last:
                raise RuntimeError("Forum category pagination changed during discovery")

            last = advertised
            for row in table.select("tr"):
                if "head" in row.get("class", []):
                    continue
                link = required(row, ".title a")
                match = re.search(r"/t-(\d+)", str(link.get("href", "")))
                if match is None or int(match[1]) in seen:
                    raise RuntimeError("Missing or duplicate forum thread ID")

                seen.add(int(match[1]))
                ids.append(int(match[1]))

            if page == last:
                return ids

            page += 1

    def thread(self, thread_id: int) -> WikidotForumThreadData:
        """Collect one thread and all nested posts in their displayed order."""
        body = self.body("forum/ForumViewThreadModule", t=str(thread_id))
        soup = BeautifulSoup(body, "html.parser")
        match = re.search(r"WIKIDOT.forumThreadId\s*=\s*(\d+)", body)
        if match is None or int(match[1]) != thread_id:
            raise RuntimeError("Forum thread identity mismatch")

        box = required(soup, ".forum-thread-box")
        crumbs = required(box, ".forum-breadcrumbs")
        title = str(crumbs.contents[-1])
        title = title.strip().removeprefix("»").strip()

        category = crumbs.select_one('a[href*="/c-"]')
        category_id = None
        if category:
            category_id = int(re.search(r"/c-(\d+)", category["href"])[1])

        stats = required(box, ".statistics")
        breaks = stats.select("br")
        count = (
            re.search(r"(\d+)\s*$", str(breaks[2].previous_sibling)) if len(breaks) >= 3 else None
        )

        if count is None:
            raise RuntimeError("Missing reported post count")
        posts = []
        responses = {"thread": body}
        page, last = 1, None

        while True:
            body = self.body("forum/ForumViewThreadPostsModule", t=str(thread_id), pageNo=str(page))
            responses[f"posts-{page}"] = body
            soup = BeautifulSoup(body, "html.parser")
            # An empty posts response is valid for a thread reporting zero posts.
            if not soup.select(".post") and (int(count[1]) != 0 or body.strip()):
                raise RuntimeError("Missing forum posts")

            advertised = pagination(soup, page)
            if last is not None and advertised != last:
                raise RuntimeError("Forum post pagination changed during collection")

            last = advertised
            for post in soup.select(".post"):
                identifier = re.fullmatch(r"post-(\d+)", str(post.get("id", "")))
                if identifier is None:
                    raise RuntimeError("Missing forum post ID")

                container = post.find_parent(class_="post-container")
                ancestor = container.find_parent(class_="post-container") if container else None
                parent = ancestor.find(class_="post", recursive=False) if ancestor else None
                parent_id = int(parent["id"].removeprefix("post-")) if parent else None
                head = required(post, ":scope > .long > .head")

                posts.append(
                    WikidotForumPostData(
                        id=int(identifier[1]),
                        title=required(head, ".title").get_text().strip(),
                        # The outer div belongs to Wikidot's interface, not the comment.
                        # Preserve the unmodified response separately in thread.responses.
                        html=required(post, ":scope > .long > .content").decode_contents(),
                        created_at=timestamp(head),
                        created_by=author(head),
                        parent_id=parent_id,
                    )
                )

            if page == last:
                break

            page += 1

        parents = {post.id: post.parent_id for post in posts}
        if len(parents) != len(posts):
            raise RuntimeError("Duplicate forum post ID")

        for identifier in parents:
            visited = set()
            while identifier is not None:
                if identifier in visited or identifier not in parents:
                    raise RuntimeError("Broken forum parent chain")
                visited.add(identifier)
                identifier = parents[identifier]

        return WikidotForumThreadData(
            id=thread_id,
            title=title,
            category_id=category_id,
            reported_posts=int(count[1]),
            created_at=timestamp(stats),
            created_by=author(stats),
            posts=posts,
            responses=responses,
        )

    def revisions(self, post_id: int) -> list[WikidotForumPostData]:
        """Archive HTML revisions; history_position is derived, not a remote revision number."""
        body = self.body("forum/sub/ForumPostRevisionsModule", postId=str(post_id))
        soup = BeautifulSoup(body, "html.parser")
        match = re.search(r"hideHistory\(event,\s*(\d+)\)", body)
        if match is None or int(match[1]) != post_id or soup.select(".pager"):
            raise RuntimeError("Unexpected forum history response")

        rows = required(soup, "table.table").select("tr")
        result = []
        seen = set()
        for position, row in enumerate(reversed(rows)):
            link = required(row, 'a[onclick*="showRevision"]')
            match = re.search(r"showRevision\(event,\s*(\d+)\)", link["onclick"])
            if match is None or int(match[1]) in seen:
                raise RuntimeError("Missing or duplicate forum revision ID")

            revision_id = int(match[1])
            seen.add(revision_id)
            response = self.amc.request(
                "forum/sub/ForumPostRevisionModule", revisionId=str(revision_id)
            )
            if (
                response.get("postId") != post_id
                or not isinstance(response.get("title"), str)
                or not isinstance(response.get("content"), str)
            ):
                raise RuntimeError("Invalid forum revision content or post identity")
            result.append(
                WikidotForumPostData(
                    id=post_id,
                    title=response["title"],
                    html=response["content"],
                    created_at=timestamp(row),
                    created_by=author(row),
                    revision_id=revision_id,
                    history_position=position,
                )
            )

        if not result:
            raise RuntimeError("Empty forum post history")

        return result
