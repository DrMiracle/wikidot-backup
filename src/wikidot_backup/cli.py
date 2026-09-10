"""Command-line interface for Wikidot backup operations."""
from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from wikidot_backup.config import DEFAULT_OUTPUT_DIR
from wikidot_backup.services.backup import backup_site
from wikidot_backup.services.backup_types import BackupOptions
from wikidot_backup.storage.inspection import inspect_archive
from wikidot_backup.storage.manifest import ArchiveManifestStore
from wikidot_backup.ui.progress import RichBackupProgress
from wikidot_backup.util.formatting import format_bytes
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
    ] = Path(DEFAULT_OUTPUT_DIR),
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
    revisions: Annotated[
        bool,
        typer.Option(
            "--revisions",
            help="Include complete page revision history.",
        ),
    ] = False,

    files: Annotated[
        bool,
        typer.Option(
            "--files/--no-files",
            help="Download page attachments.",
        ),
    ] = True,
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
                options=BackupOptions(
                    include_revisions=revisions,
                    include_files=files,
                ),
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

@app.command()
def info(
    archive: Annotated[
        Path,
        typer.Argument(
            help="Path to an existing backup archive.",
        ),
    ],
) -> None:
    """Show information about an existing backup archive."""
    statistics = inspect_archive(archive)

    manifest_path = archive / "archive.json"

    manifest = (
        ArchiveManifestStore(archive).load()
        if manifest_path.is_file()
        else None
    )

    table = Table(
        title="Wikidot Backup",
        show_header=False,
    )

    table.add_column("Field")
    table.add_column("Value")

    if manifest is not None:
        table.add_row(
            "Site",
            manifest.site.unix_name,
        )
        table.add_row(
            "Title",
            manifest.site.title or "-",
        )
        table.add_row(
            "Created",
            manifest.created_at.isoformat(),
        )
        table.add_row(
            "Last successful run",
            (
                manifest.last_successful_run_at.isoformat()
                if manifest.last_successful_run_at
                else "-"
            ),
        )
        table.add_row(
            "Last full backup",
            (
                manifest.last_full_backup_at.isoformat()
                if manifest.last_full_backup_at
                else "-"
            ),
        )

        table.add_section()

    table.add_row(
        "Archived pages",
        str(statistics.pages),
    )
    table.add_row(
        "Current sources",
        str(statistics.current_sources),
    )
    table.add_row(
        "Pages with file metadata",
        str(statistics.pages_with_file_metadata),
    )
    table.add_row(
        "Attachment records",
        str(statistics.file_records),
    )
    table.add_row(
        "Unique blobs",
        str(statistics.unique_blobs),
    )
    table.add_row(
        "Pages with revisions",
        str(statistics.pages_with_revisions),
    )
    table.add_row(
        "Revisions",
        str(statistics.revisions),
    )

    table.add_section()

    table.add_row(
        "Page data",
        format_bytes(statistics.pages_bytes),
    )
    table.add_row(
        "Blobs",
        format_bytes(statistics.blobs_bytes),
    )
    table.add_row(
        "Indexes",
        format_bytes(statistics.indexes_bytes),
    )
    table.add_row(
        "State",
        format_bytes(statistics.state_bytes),
    )
    table.add_row(
        "Total",
        format_bytes(statistics.total_bytes),
    )

    table.add_section()

    table.add_row(
        "Incomplete run state",
        (
            "present"
            if statistics.resume_present
            else "none"
        ),
    )
    table.add_row(
        "Pages in resume state",
        str(statistics.resume_pages),
    )
    table.add_row(
        "Error records",
        str(statistics.error_records),
    )

    console.print(table)
