"""Rich terminal UI components for scrubIQ."""

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

from ..scanner.results import FileResult, ScanResult

console = Console()


@dataclass
class ScanStats:
    """Live statistics during scan."""

    total_files: int = 0
    scanned: int = 0
    with_matches: int = 0
    errors: int = 0
    current_file: str = ""
    entity_counts: dict = field(default_factory=dict)
    recent_matches: list = field(default_factory=list)


class ScanUI:
    """
    Rich terminal UI for scan progress.

    Shows a live-updating panel with:
    - Progress bar and percentage
    - Counts (scanned, matches, errors)
    - Entity type breakdown with mini bar charts
    - Recent matches feed
    - Current file being scanned

    Usage:
        ui = ScanUI()
        ui.start(total=100, source_path="/documents")

        for file in files:
            result = scan(file)
            ui.update(result)

        ui.complete(scan_result)
    """

    def __init__(self, quiet: bool = False):
        self.quiet = quiet
        self.stats = ScanStats()
        self.live: Optional[Live] = None
        self.start_time: Optional[datetime] = None
        self.source_path: str = ""

    def start(self, total: int, source_path: str = ""):
        """Start the live display."""
        self.stats = ScanStats(total_files=total)
        self.start_time = datetime.now()
        self.source_path = source_path

        if self.quiet:
            return

        self.live = Live(
            self._render(),
            console=console,
            refresh_per_second=4,
            transient=True,  # Remove the live display when done
        )
        self.live.start()

    def update(self, result: FileResult):
        """Update with a file result."""
        self.stats.scanned += 1
        self.stats.current_file = str(result.path)[-60:]

        if result.error:
            self.stats.errors += 1
        elif result.has_sensitive_data:
            self.stats.with_matches += 1

            # Count entities
            for match in result.real_matches:
                key = match.entity_type.value
                self.stats.entity_counts[key] = self.stats.entity_counts.get(key, 0) + 1

            # Track recent matches (last 3)
            self.stats.recent_matches.append(
                {
                    "file": result.path.name,
                    "types": [m.entity_type.value for m in result.real_matches[:3]],
                }
            )
            self.stats.recent_matches = self.stats.recent_matches[-3:]

        if self.live:
            self.live.update(self._render())

    def complete(self, result: ScanResult):
        """Show completion summary."""
        if self.live:
            self.live.stop()

        if not self.quiet:
            console.print(self._render_summary(result))

    def _render(self) -> Panel:
        """Render the live display panel."""
        stats = self.stats

        # Progress bar
        pct = (stats.scanned / stats.total_files * 100) if stats.total_files > 0 else 0
        filled = int(pct / 5)
        bar = "█" * filled + "░" * (20 - filled)

        # Elapsed time
        elapsed = ""
        if self.start_time:
            secs = (datetime.now() - self.start_time).total_seconds()
            elapsed = f" ({secs:.0f}s)"

        # Entity breakdown with mini bar charts
        entity_lines = []
        for entity, count in sorted(stats.entity_counts.items(), key=lambda x: -x[1])[:5]:
            bar_len = min(count, 15)
            entity_lines.append(f"  {entity:<18} {count:>4}  {'█' * bar_len}")

        # Recent matches feed
        recent_lines = []
        for match in stats.recent_matches:
            types = ", ".join(match["types"][:2])
            if len(match["types"]) > 2:
                types += "..."
            recent_lines.append(f"  • {match['file'][:35]:<35} → {types}")

        # Build content
        content = f"""[bold]Scanning...[/bold]  [{bar}]  {pct:.0f}%  {stats.scanned:,}/{stats.total_files:,}{elapsed}

  Scanned       {stats.scanned:>6,}
  [green]With matches[/green]  {stats.with_matches:>6,}
  [red]Errors[/red]        {stats.errors:>6,}

[bold]Entities Found[/bold]
{chr(10).join(entity_lines) if entity_lines else '  [dim](none yet)[/dim]'}

[bold]Recent Matches[/bold]
{chr(10).join(recent_lines) if recent_lines else '  [dim](none yet)[/dim]'}

[dim]Current: {stats.current_file}[/dim]"""

        return Panel(
            content,
            title="[blue]scrubIQ[/blue]",
            border_style="blue",
            padding=(0, 1),
        )

    def _render_summary(self, result: ScanResult) -> Panel:
        """Render completion summary panel."""
        # Elapsed time
        elapsed = ""
        if result.started_at and result.completed_at:
            secs = (result.completed_at - result.started_at).total_seconds()
            elapsed = f"in {secs:.1f}s"

        # Entity totals
        entity_totals = {}
        for f in result.files:
            for m in f.real_matches:
                key = m.entity_type.value
                entity_totals[key] = entity_totals.get(key, 0) + 1

        entity_lines = []
        for entity, count in sorted(entity_totals.items(), key=lambda x: -x[1]):
            entity_lines.append(f"  {entity:<20} {count:>6,}")

        # Label recommendations
        label_counts = {}
        for f in result.files:
            if f.label_recommendation:
                key = f.label_recommendation.value
                label_counts[key] = label_counts.get(key, 0) + 1

        label_lines = []
        for label, count in sorted(label_counts.items(), key=lambda x: -x[1]):
            label_lines.append(f"  {label:<20} {count:>6,} files")

        # Determine panel style based on results
        if result.files_with_matches > 0:
            title = "[red]⚠ Sensitive Data Found[/red]"
            border_style = "red"
            status = f"[bold red]⚠ Scan Complete[/bold red] {elapsed}"
        else:
            title = "[green]✓ No Sensitive Data[/green]"
            border_style = "green"
            status = f"[bold green]✓ Scan Complete[/bold green] {elapsed}"

        content = f"""{status}

[bold]Summary[/bold]
  Total files scanned  {result.total_files:>6,}
  Files with matches   {result.files_with_matches:>6,}
  Files with errors    {result.files_errored:>6,}
  Total matches        {result.total_matches:>6,}

[bold]Entities Found[/bold]
{chr(10).join(entity_lines) if entity_lines else '  [dim](none)[/dim]'}

[bold]Label Recommendations[/bold]
{chr(10).join(label_lines) if label_lines else '  [dim](none)[/dim]'}"""

        return Panel(
            content,
            title=title,
            border_style=border_style,
            padding=(0, 1),
        )


def print_error(message: str):
    """Print an error message."""
    console.print(f"[red]Error:[/red] {message}")


def print_warning(message: str):
    """Print a warning message."""
    console.print(f"[yellow]Warning:[/yellow] {message}")


def print_success(message: str):
    """Print a success message."""
    console.print(f"[green]✓[/green] {message}")


def print_info(message: str):
    """Print an info message."""
    console.print(f"[blue]ℹ[/blue] {message}")
