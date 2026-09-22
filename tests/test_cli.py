"""CLI automation contracts, independent of terminal spacing."""

from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

import wikidot_backup.cli as cli
from wikidot_backup.services.backup_types import SiteBackupResult


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
