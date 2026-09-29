"""CLI automation contracts, independent of terminal spacing."""

from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

import wikidot_backup.cli as cli
from wikidot_backup.services.backup_types import ForumBackupResult, SiteBackupResult


def test_root_help_lists_command_arguments_and_options():
    result = CliRunner().invoke(cli.app, ["--help"], terminal_width=120)
    assert result.exit_code == 0
    text = " ".join(result.output.split())
    for entry in ("backup SITE", "backup-forums SITE", "estimate SITE", "info ARCHIVE",
                  "--forums", "--revisions", "--no-files", "--verbose", "--refresh",
                  "--output", "--limit", "COMMAND --help"):
        assert entry in text


@pytest.mark.parametrize("failed, expected", [(0, 0), (1, 1)])
def test_backup_exit_code(monkeypatch, failed, expected):
    client = Mock()
    monkeypatch.setattr(cli, "WikidotClient", Mock(return_value=client))
    monkeypatch.setattr(
        cli,
        "backup_site",
        Mock(
            return_value=SiteBackupResult(
                discovered=1,
                already_completed=0,
                processed=1,
                saved=1 - failed,
                failed=failed,
                limited=False,
                resume_state_cleared=not failed,
            )
        ),
    )
    result = CliRunner().invoke(cli.app, ["backup", "example"])
    assert result.exit_code == expected
    client.close.assert_called_once()


def test_interrupted_backup_exits_130_and_closes_client(monkeypatch):
    client = Mock()
    monkeypatch.setattr(cli, "WikidotClient", Mock(return_value=client))
    monkeypatch.setattr(cli, "backup_site", Mock(side_effect=KeyboardInterrupt))
    assert CliRunner().invoke(cli.app, ["backup", "example"]).exit_code == 130
    client.close.assert_called_once()


@pytest.mark.parametrize("forum_failed, warnings, exit_code", [(0, [], 0), (1, [], 1),
                                                              (0, ["Missing threads"], 2)])
def test_backup_forum_option_and_result(monkeypatch, forum_failed, warnings, exit_code):
    client = Mock()
    monkeypatch.setattr(cli, "WikidotClient", Mock(return_value=client))
    service = Mock(return_value=SiteBackupResult(
        discovered=1, already_completed=0, processed=1, saved=1, failed=0,
        limited=False, resume_state_cleared=exit_code == 0,
        forums=ForumBackupResult(failed=forum_failed, warnings=warnings),
    ))
    monkeypatch.setattr(cli, "backup_site", service)

    result = CliRunner().invoke(cli.app, ["backup", "example", "--forums", "--revisions"])

    assert result.exit_code == exit_code, result.output
    options = service.call_args.kwargs["options"]
    assert options.include_forums and options.include_revisions
    client.close.assert_called_once()
