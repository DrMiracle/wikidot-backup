"""Explicit conversion of transient forum data into persistent records."""
from datetime import UTC, datetime

from wikidot_backup.collectors.common import user_to_ref
from wikidot_backup.models.forum_records import (
    ForumPostRecord,
    ForumRevisionRecord,
    ForumThreadRecord,
)
from wikidot_backup.wikidot.forum_client import WikidotForumClient


def collect_thread(
    client: WikidotForumClient,
    thread_id: int,
    *,
    page_ids: list[int],
    revisions: bool,
) -> tuple[ForumThreadRecord, list[ForumPostRecord], list[ForumRevisionRecord]]:
    """Collect the entire requested snapshot before publishing or marking completion."""
    data = client.thread(thread_id)
    thread = ForumThreadRecord(
        thread_id=data.id,
        title=data.title,
        category_id=data.category_id,
        created_at=data.created_at,
        created_by=user_to_ref(data.created_by),
        fetched_at=datetime.now(UTC),
        reported_posts=data.reported_posts,
        observed_post_ids=[post.id for post in data.posts],
        archived_page_ids=page_ids,
        revisions_included=revisions,
        responses=data.responses,
    )
    posts = []
    history = []
    for post in data.posts:
        posts.append(
            ForumPostRecord(
                thread_id=thread_id,
                post_id=post.id,
                parent_id=post.parent_id,
                title=post.title,
                html=post.html,
                created_at=post.created_at,
                created_by=user_to_ref(post.created_by),
            )
        )
        if revisions:
            for revision in client.revisions(post.id):
                history.append(
                    ForumRevisionRecord(
                        thread_id=thread_id,
                        post_id=post.id,
                        revision_id=revision.revision_id,
                        history_position=revision.history_position,
                        title=revision.title,
                        html=revision.html,
                        created_at=revision.created_at,
                        created_by=user_to_ref(revision.created_by),
                    )
                )
    return thread, posts, history
