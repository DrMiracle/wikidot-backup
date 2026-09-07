from __future__ import annotations

from typing import Any

import wikidot
from bs4 import BeautifulSoup

from wikidot_backup.config import LIST_PAGES_PER_PAGE
from wikidot_backup.wikidot.amc import WikidotAmcClient
from wikidot_backup.wikidot.models import WikidotPageData, WikidotUserData
from wikidot_backup.wikidot.retry import retry_wikidot_request


class WikidotClient:
    def __init__(self, site_name: str) -> None:
        """Initialize access to a Wikidot site.

        Both the high-level ``wikidot.py`` client and the low-level AMC client
        are initialized here. The former provides convenient structured access,
        while AMC is used where archival operations require more direct control.

        Args:
            site_name:
                Wikidot unix site name, for example ``scp-ukrainian``.
        """

        self._client = wikidot.Client()
        self._site = self._client.site.get(site_name)

        self.site_name = site_name
        self.site_id = self._site.id
        self.site_title = self._site.title
        self.site_domain = self._site.domain

        self._amc = WikidotAmcClient(
            self._site.url,
        )

    @retry_wikidot_request
    def fetch_page(self, fullname: str) -> WikidotPageData:
        """Retrieve and normalize current data for one Wikidot page.
        Transient communication failures are retried automatically.

        Third-party ``wikidot.py`` objects are converted into primitive values
        before leaving the integration layer. This prevents the rest of the
        backup application from depending directly on the external library.

        Args:
            fullname:
                Canonical Wikidot page fullname, including the category prefix
                where applicable.

        Returns:
            Normalized page data containing source, metadata and relevant
            references.

        Raises:
            LookupError:
                If Wikidot does not return the requested page.
        """

        page = self._site.page.get(fullname)

        if page is None:
            raise LookupError(f"Wikidot page not found: {fullname}")

        page_id = page.id
        source = page.source.wiki_text

        visible_tags, hidden_tags = self._split_tags(page.tags)

        discussion = page.discussion

        return WikidotPageData(
            page_id=page_id,

            fullname=page.fullname,
            name=page.name,
            category=page.category,
            title=page.title,

            parent_fullname=page.parent_fullname,

            tags=visible_tags,
            hidden_tags=hidden_tags,

            children_count=int(page.children_count),
            comments_count=int(page.comments_count),

            size=int(page.size),

            rating=page.rating,
            votes_count=page.votes_count,
            rating_percent=page.rating_percent,

            latest_revision_no=page.revisions_count,

            created_by=self._user_to_dataclass(page.created_by),
            created_at=page.created_at,

            updated_by=self._user_to_dataclass(page.updated_by),
            updated_at=page.updated_at,

            commented_by=self._user_to_dataclass(page.commented_by),
            commented_at=page.commented_at,

            discussion_thread_id=(
                discussion.id
                if discussion is not None
                else None
            ),

            metas=dict(page.metas),

            source=source,
        )

    def list_page_fullnames(self) -> list[str]:
        """Return fullnames of every page on the Wikidot site.

        ListPagesModule is queried page by page until no new page names
        are returned.

        Returns:
            All discovered fullnames without duplicates.
        """

        fullnames: list[str] = []
        seen: set[str] = set()

        offset = 0

        while True:
            batch = self._list_page_fullnames_batch(
                offset=offset,
            )

            new_fullnames = [
                fullname
                for fullname in batch
                if fullname not in seen
            ]

            if not batch:
                break

            # This protects us against unexpected Wikidot behaviour where
            # an ignored offset could repeatedly return the same batch.
            if not new_fullnames:
                raise RuntimeError(
                    "ListPages returned no new pages. "
                    f"The offset {offset} may have been ignored."
                )

            fullnames.extend(new_fullnames)
            seen.update(new_fullnames)

            if len(batch) < LIST_PAGES_PER_PAGE:
                break

            offset += LIST_PAGES_PER_PAGE

        return fullnames

    def _list_page_fullnames_batch(
            self,
            offset: int,
    ) -> list[str]:
        """Retrieve one batch of page fullnames from ListPagesModule.

        Args:
            offset:
                Number of matching pages to skip before returning results.

        Returns:
            Up to LIST_PAGES_PER_PAGE page fullnames.
        """

        result = self._amc.request(
            "list/ListPagesModule",

            # A complete archive must inspect every category and include
            # hidden page types as well as ordinary pages.
            category="*",
            pagetype="*",

            # Stable ordering is essential because offset-based iteration
            # assumes that subsequent requests see the same ordering.
            order="fullname",

            limit=str(LIST_PAGES_PER_PAGE),
            perPage=str(LIST_PAGES_PER_PAGE),

            # Do not use Wikidot's UI pagination (`p`) here. We call
            # ListPagesModule directly through AMC, so advancing through
            # the result set explicitly with an offset is simpler and
            # independent of generated pager links.
            offset=str(offset),

            separate="false",
            module_body="%%fullname%%",
        )

        return self._parse_list_pages_response(
            result["body"],
        )

    @staticmethod
    def _parse_list_pages_response(body: str) -> list[str]:
        """Extract page fullnames from a ListPagesModule response.

        Wikidot renders the requested page values inside ``.list-pages-box``
        and adds pagination controls in a nested ``.pager`` element.
        The pager is removed before extracting text so page numbers and
        navigation labels cannot be mistaken for Wikidot page names.
        """

        soup = BeautifulSoup(
            body,
            "html.parser",
        )

        container = soup.select_one(".list-pages-box")

        if container is None:
            return []

        # Pagination controls are part of the same ListPages container.
        # Remove them before reading text so values such as "1", "2",
        # and "next »" are not interpreted as page fullnames.
        pager = container.select_one(".pager")

        if pager is not None:
            pager.decompose()

        return [
            line.strip()
            for line in container.get_text(separator="\n").splitlines()
            if line.strip()
        ]

    def close(self) -> None:
        """Release HTTP resources owned by the Wikidot integration layer."""

        self._amc.close()

    @staticmethod
    def _split_tags(
            tags: list[str],
    ) -> tuple[list[str], list[str]]:
        """Separate regular Wikidot tags from hidden tags.

        Args:
            tags:
                Combined tag list returned by ``wikidot.py``.

        Returns:
            Tuple of ``(visible_tags, hidden_tags)``.
        """
        visible: list[str] = []
        hidden: list[str] = []

        for tag in tags:
            if tag.startswith("_"):
                hidden.append(tag)
            else:
                visible.append(tag)

        return visible, hidden

    @staticmethod
    def _user_to_dataclass(user: Any | None) -> WikidotUserData | None:
        """Convert a wikidot.py user object into persistent dataclass.

        Wikidot system, deleted or special users may not have a numeric ID,
        therefore the ID is intentionally nullable.

        Args:
            user:
                wikidot.py user object or ``None``.

        Returns:
            Dataclass with user information or ``None``.
        """
        if user is None:
            return None

        return WikidotUserData(
            id=user.id,
            name=user.name,
            unix_name=getattr(
                user,
                "unix_name",
                None,
            ),
        )
