"""Console script for fruxon-sdk."""

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.prompt import IntPrompt

from fruxon.exceptions import FruxonError, MultipleAgentsError
from fruxon.export import export_agent
from fruxon.fruxon import FruxonClient

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


@app.command()
def run(
    agent: Annotated[str, typer.Argument(help="Agent identifier to execute")],
    tenant: Annotated[str, typer.Option("--tenant", "-t", help="Tenant identifier")],
    api_key: Annotated[str | None, typer.Option("--api-key", "-k", envvar="FRUXON_API_KEY", help="API key")] = None,
    param: Annotated[
        list[str] | None, typer.Option("--param", "-p", help="Parameter as key=value (repeatable)")
    ] = None,
    session_id: Annotated[str | None, typer.Option("--session", "-s", help="Session ID")] = None,
    base_url: Annotated[str, typer.Option("--base-url", help="API base URL")] = FruxonClient.DEFAULT_BASE_URL,
    json_output: Annotated[bool, typer.Option("--json", help="Output full JSON response")] = False,
):
    """Execute a Fruxon agent and print the response.

    Examples:
        fruxon run my-agent -t acme-corp -k frx_...
        fruxon run my-agent -t acme-corp -p question="Hello" -p lang=en
        fruxon run my-agent -t acme-corp --session abc123 --json
    """
    if not api_key:
        console.print("[red]Error: API key required. Use --api-key or set FRUXON_API_KEY.[/red]")
        raise SystemExit(1)

    parameters: dict[str, object] | None = None
    if param:
        parameters = {}
        for p in param:
            if "=" not in p:
                console.print(f"[red]Error: Invalid parameter format '{p}'. Use key=value.[/red]")
                raise SystemExit(1)
            key, value = p.split("=", 1)
            parameters[key] = value

    client = FruxonClient(api_key=api_key, tenant=tenant, base_url=base_url)
    try:
        result = client.execute(agent, parameters=parameters, session_id=session_id)
    except FruxonError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1) from e

    if json_output:
        output = {
            "response": result.response,
            "sessionId": result.session_id,
            "executionRecordId": result.execution_record_id,
            "trace": {
                "agentId": result.trace.agent_id,
                "agentRevision": result.trace.agent_revision,
                "duration": result.trace.duration,
                "inputCost": result.trace.input_cost,
                "outputCost": result.trace.output_cost,
                "totalCost": result.trace.total_cost,
            },
            "links": result.links,
        }
        console.print_json(json.dumps(output))
    else:
        console.print(result.response)


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
