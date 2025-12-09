"""scrubIQ CLI - main entry point."""

import click
from rich.console import Console

console = Console()


@click.group()
@click.version_option(package_name="scrubiq")
def cli():
    """scrubIQ - Find and protect sensitive data."""
    pass


@cli.command()
@click.argument("path")
def scan(path: str):
    """Scan for sensitive data.

    PATH is a directory or file to scan.

    Examples:

        scrubiq scan ./documents

        scrubiq scan "\\\\fileserver\\HR"
    """
    console.print(f"[blue]Scanning:[/blue] {path}")
    console.print("[yellow]Not implemented yet[/yellow]")


if __name__ == "__main__":
    cli()
