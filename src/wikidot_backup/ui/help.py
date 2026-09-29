"""A boxed command-option overview generated from the actual CLI definitions."""

from typing import Any

import typer
from rich.console import Console
from rich.table import Table
from typer.core import TyperArgument, TyperGroup, TyperOption


class BackupCommandGroup(TyperGroup):
    """Keep standard Typer help and add an overview of subcommand options."""

    def format_help(self, ctx: typer.Context, formatter: Any) -> None:
        super().format_help(ctx, formatter)

        table = Table(title="Command arguments and options", show_lines=True)
        table.add_column("Command", style="cyan", no_wrap=True)
        table.add_column("Options (after the command)")

        for name in self.list_commands(ctx):
            command = self.get_command(ctx, name)
            if command is None or command.hidden:
                continue

            arguments = []
            options = []
            for parameter in command.params:
                if isinstance(parameter, TyperArgument):
                    arguments.append(parameter.name.upper())
                elif isinstance(parameter, TyperOption) and not parameter.hidden:
                    label = "/".join(parameter.opts + parameter.secondary_opts)
                    if not parameter.is_flag:
                        label += " " + (parameter.metavar or parameter.name.upper())
                    options.append(label)

            table.add_row(" ".join([name, *arguments]), "\n".join(options))

        console = Console(width=ctx.terminal_width)
        console.print(table)
        console.print("Details and defaults: wikidot-backup COMMAND --help", markup=False)
