"""Progress lifecycle and verbose output, without depending on Rich spacing."""

from io import StringIO

import pytest
from rich.console import Console

from wikidot_backup.services.backup_types import ForumProgressEvent
from wikidot_backup.ui.progress import RichBackupProgress


def test_preparation_phases_are_visible_before_page_collection():
    output = StringIO()
    console = Console(file=output, force_terminal=False, width=160)
    with RichBackupProgress(console=console, verbose=True) as progress:
        progress.discovery_started()
        progress.discovery_advanced(250)
        assert progress._progress.tasks[0].completed == 250
        progress.resume_loading()
        assert not progress._progress.live.is_started
        assert not progress._progress.tasks
        assert output.getvalue().splitlines()[-1] == "Reading resume state..."
        progress.resume_validation(total=1, completed=0, fullname="")
        progress.resume_validation(total=1, completed=0, fullname="saved-page")
        assert progress._progress.tasks[0].completed == 0
        assert progress._progress.tasks[0].fields["current_page"] == "saved-page"
        progress.resume_validation(total=1, completed=1, fullname="saved-page")
        progress.begin(discovered=250, already_completed=1, pending=249)
        assert len(progress._progress.tasks) == 1
        assert progress._progress.tasks[0].description == "Pages"

    text = output.getvalue()
    assert "Fetching page list" in text
    assert "Reading resume state" in text
    assert "Checking saved page IDs" in text
    assert text.count("Checking saved page ID: saved-page") == 1


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
