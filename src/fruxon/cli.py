"""Console script for fruxon-sdk."""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.prompt import IntPrompt

from fruxon.export import MultipleAgentsError, export_agent

app = typer.Typer(help="Fruxon CLI - tools for working with the Fruxon platform.")
console = Console()


@app.callback()
def main():
    """Fruxon CLI - tools for working with the Fruxon platform."""


@app.command()
def export(
    entry_point: Annotated[
        Path | None, typer.Argument(help="Path to the main Python file. Auto-detected if omitted.")
    ] = None,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Write output to file instead of stdout")
    ] = None,
    copy: Annotated[bool, typer.Option("--copy", "-c", help="Copy output to clipboard")] = False,
):
    """Export a multi-file Python agent into a single file for Fruxon import.

    Auto-detects the agent entry point by scanning for framework imports
    (LangChain, CrewAI, Google ADK, etc.). You can also specify the entry
    point explicitly.

    Examples:
        fruxon export
        fruxon export graph.py
        fruxon export my_agent/main.py -o export.py
        fruxon export --copy
    """
    try:
        result = export_agent(str(entry_point) if entry_point else None, str(output) if output else None)
    except MultipleAgentsError as e:
        # Prompt user to select which agent to export
        choice = IntPrompt.ask(
            "\nWhich agent do you want to export?",
            choices=[str(i) for i in range(1, len(e.entry_points) + 1)],
        )
        selected_path = e.entry_points[choice - 1][0]
        result = export_agent(str(selected_path), str(output) if output else None)

    _handle_output(result, output, copy)


def _handle_output(result: str, output: Path | None, copy: bool):
    """Handle clipboard copy and stdout output."""
    if copy:
        _copy_to_clipboard(result)

    if not output and not copy:
        console.print(result)
    elif not output and copy:
        lines = result.count("\n") + 1
        console.print(f"[dim]{lines} lines ready to paste into Fruxon.[/dim]")


def _copy_to_clipboard(text: str):
    """Copy text to system clipboard."""
    import subprocess

    for cmd in [["pbcopy"], ["xclip", "-selection", "clipboard"]]:
        try:
            process = subprocess.Popen(cmd, stdin=subprocess.PIPE)
            process.communicate(text.encode("utf-8"))
            console.print("[green]Copied to clipboard.[/green]")
            return
        except FileNotFoundError:
            continue
    console.print("[yellow]Clipboard not available. Install xclip or use -o to write to file.[/yellow]")


if __name__ == "__main__":
    app()
