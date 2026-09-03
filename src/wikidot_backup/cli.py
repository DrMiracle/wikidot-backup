"""Command-line interface for Wikidot backup operations."""
from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from wikidot_backup.services.backup import backup_site
from wikidot_backup.ui.progress import RichBackupProgress
from wikidot_backup.wikidot.client import WikidotClient


app = typer.Typer(
    no_args_is_help=True,
    help="Create portable backups of Wikidot sites.",
)

console = Console()

@app.callback()
def main() -> None:
    """Backup and archival tools for Wikidot sites."""


@app.command()
def backup(
    site: Annotated[
        str,
        typer.Argument(
            help="Wikidot site unix name, e.g. scp-ukrainian.",
        ),
    ],
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Backup archive directory.",
        ),
    ] = Path("backup"),
    limit: Annotated[
        int | None,
        typer.Option(
            "--limit",
            min=1,
            help=(
                "Process at most this many unfinished pages. "
                "Useful for development and testing."
            ),
        ),
    ] = None,
) -> None:
    """Back up current page content from a Wikidot site.

    Existing resume state is used automatically. Pages completed during an
    interrupted previous invocation are skipped, while unfinished or failed
    pages are retried.
    """

    client: WikidotClient | None = None

    try:
        client = WikidotClient(site)

        with RichBackupProgress() as progress:
            result = backup_site(
                client,
                output,
                limit=limit,
                progress=progress,
            )

    except KeyboardInterrupt:
        console.print()
        console.print(
            "[yellow]Backup interrupted.[/yellow] "
            "Resume state has been preserved."
        )

        raise typer.Exit(
            code=130,
        )

    finally:
        if client is not None:
            client.close()

    console.print()

    if result.failed:
        console.print(
            f"[yellow]Backup finished with "
            f"{result.failed} failed page(s).[/yellow]"
        )
        console.print(
            f"See: {output / '.state' / 'errors.jsonl'}"
        )
    elif result.limited:
        console.print(
            "[green]Current batch completed successfully.[/green] "
            "More pages remain for the next run."
        )
    else:
        console.print(
            "[bold green]All discovered pages were archived "
            "successfully.[/bold green]"
        )

    console.print(
        f"Saved this run: {result.saved}"
    )
