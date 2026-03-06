"""Console script for fruxon-sdk."""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from fruxon.export import export_agent

app = typer.Typer(help="Fruxon CLI - tools for working with the Fruxon platform.")
console = Console()


@app.command()
def export(
    entry_point: Annotated[Path, typer.Argument(help="Path to the main Python file (e.g. graph.py, crew.py)")],
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Write output to file instead of stdout")
    ] = None,
    copy: Annotated[bool, typer.Option("--copy", "-c", help="Copy output to clipboard")] = False,
):
    """Export a multi-file Python agent into a single file for Fruxon import.

    Traces local imports from your entry point and consolidates all local
    modules into one file. Third-party packages (langchain, crewai, etc.)
    are left as import statements.

    Examples:
        fruxon export graph.py
        fruxon export my_agent/main.py -o export.py
        fruxon export graph.py --copy
    """
    result = export_agent(str(entry_point), str(output) if output else None)

    if copy:
        try:
            import subprocess

            process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
            process.communicate(result.encode("utf-8"))
            console.print("[green]Copied to clipboard.[/green]")
        except FileNotFoundError:
            try:
                import subprocess

                process = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE)
                process.communicate(result.encode("utf-8"))
                console.print("[green]Copied to clipboard.[/green]")
            except FileNotFoundError:
                console.print("[yellow]Clipboard not available. Install xclip or use -o to write to file.[/yellow]")

    if not output and not copy:
        console.print(result)
    elif not output and copy:
        # Already copied, just show summary
        lines = result.count("\n") + 1
        console.print(f"[dim]{lines} lines ready to paste into Fruxon.[/dim]")


if __name__ == "__main__":
    app()
