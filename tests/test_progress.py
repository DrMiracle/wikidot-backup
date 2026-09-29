"""Progress lifecycle and verbose output, without depending on Rich spacing."""

from io import StringIO

import pytest
from rich.console import Console

from wikidot_backup.services.backup_types import ForumProgressEvent
from wikidot_backup.ui.progress import RichBackupProgress


@pytest.mark.parametrize("verbose", [False, True])
def test_page_to_forum_transition_uses_one_live_console(verbose):
    output = StringIO()
    console = Console(file=output, force_terminal=False, width=140)

    with RichBackupProgress(console=console, verbose=verbose) as progress:
        progress.begin(discovered=1, already_completed=0, pending=1)
        progress.page_started(fullname="test-page")
        progress.page_succeeded(fullname="test-page", saved=1, failed=0)
        progress.end(saved=1, failed=0)
        assert not progress._progress.live.is_started

        progress.forum_event(ForumProgressEvent("categories", 1))
        progress.forum_event(ForumProgressEvent(
            "categories", 1, 1, message="Discovered category 1: General",
        ))
        progress.forum_event(ForumProgressEvent("threads", 2))
        progress.forum_event(ForumProgressEvent(
            "threads", 2, 1, saved=1, message="Saved thread 123: [example]",
        ))
        progress.forum_event(ForumProgressEvent(
            "threads", 2, 2, saved=1, failed=1, message="Failed thread 456: unavailable",
        ))
        task = progress._progress.tasks[0]
        assert task.completed == 2 and task.fields["failed"] == 1
        assert len(progress._progress.tasks) == 1

    text = output.getvalue()
    assert text.count("Pages") == 1
    assert "Forum categories" in text and "Threads" in text
    assert ("Saved page: test-page" in text) == verbose
    assert ("Saved thread 123: [example]" in text) == verbose
    assert ("Discovered category 1" in text) == verbose
    assert not progress._progress.live.is_started
