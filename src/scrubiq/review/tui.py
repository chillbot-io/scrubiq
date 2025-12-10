"""Simple TUI for human review with live updates."""

from datetime import datetime
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from .models import ReviewSample, Verdict
from .storage import ReviewStorage


console = Console()


class ReviewTUI:
    """
    Terminal UI for reviewing matches.

    Shows one sample at a time with live progress updates.
    Simple keyboard input: c/w/s/q

    Usage:
        tui = ReviewTUI(samples, storage)
        tui.run()
    """

    def __init__(
        self,
        samples: list[ReviewSample],
        storage: ReviewStorage,
        scan_id: str = "",
    ):
        self.samples = samples
        self.storage = storage
        self.scan_id = scan_id
        self.current_index = 0
        self.reviewed = 0
        self.correct = 0
        self.wrong = 0
        self.skipped = 0
        self.start_time = datetime.now()

    @property
    def total(self) -> int:
        return len(self.samples)

    @property
    def current_sample(self) -> Optional[ReviewSample]:
        if self.current_index < len(self.samples):
            return self.samples[self.current_index]
        return None

    def run(self) -> dict:
        """
        Run the review session.

        Returns stats dict with review results.
        """
        if not self.samples:
            console.print("[yellow]No samples to review.[/yellow]")
            return self._get_stats()

        console.print()

        while self.current_index < len(self.samples):
            sample = self.current_sample

            # Show the sample panel
            console.print(self._render_sample(sample))

            # Get verdict
            verdict = self._prompt_verdict()

            if verdict == "quit":
                break

            # Record verdict
            sample.verdict = verdict
            sample.reviewed_at = datetime.now()

            if verdict == Verdict.CORRECT:
                self.correct += 1
                self.reviewed += 1
            elif verdict == Verdict.WRONG:
                self.wrong += 1
                self.reviewed += 1
            elif verdict == Verdict.SKIP:
                self.skipped += 1

            # Save to training storage (anonymized)
            self.storage.save_verdict(sample)

            self.current_index += 1
            console.print()  # Blank line between samples

        # Show summary
        console.print(self._render_summary())

        return self._get_stats()

    def _render_sample(self, sample: ReviewSample) -> Panel:
        """Render a sample for review."""
        # Progress line
        progress = f"[{self.current_index + 1}/{self.total}]"
        stats = f"✓{self.correct} ✗{self.wrong} ⊘{self.skipped}"

        # Highlight the value in context
        context_display = self._highlight_value(sample.context, sample.value)

        # File info
        file_info = f"[dim]{sample.file_path}[/dim]"

        # Entity info
        entity_info = (
            f"[bold]{sample.entity_type.upper()}[/bold]  "
            f"{sample.confidence_pct}% confidence  "
            f"[dim]({sample.detector})[/dim]"
        )

        content = f"""
{progress}  {stats}

{file_info}

{context_display}

{entity_info}

[dim]Value: {sample.value_redacted}[/dim]

[bold][c][/bold]orrect  [bold][w][/bold]rong  [bold][s][/bold]kip  [bold][q][/bold]uit
"""

        return Panel(
            content.strip(),
            title="[yellow]Review Sample[/yellow]",
            border_style="yellow",
        )

    def _highlight_value(self, context: str, value: str) -> str:
        """Highlight the matched value in context."""
        if not value or value not in context:
            return context

        # Replace value with highlighted version
        highlighted = f"[bold red on white] {value} [/bold red on white]"
        return context.replace(value, highlighted)

    def _prompt_verdict(self) -> Verdict | str:
        """Get verdict from user."""
        while True:
            response = Prompt.ask(
                "Verdict",
                choices=["c", "w", "s", "q"],
                default="s",
            )

            if response == "c":
                return Verdict.CORRECT
            elif response == "w":
                return Verdict.WRONG
            elif response == "s":
                return Verdict.SKIP
            elif response == "q":
                return "quit"

    def _render_summary(self) -> Panel:
        """Render session summary."""
        elapsed = (datetime.now() - self.start_time).total_seconds()

        accuracy = self.correct / self.reviewed if self.reviewed > 0 else 0

        content = f"""
[bold green]✓ Review Complete[/bold green]

Scan:       {self.scan_id}
Duration:   {elapsed:.0f}s

[bold]Results[/bold]
  Reviewed:    {self.reviewed}
  Correct:     {self.correct} ({accuracy:.0%} accurate)
  Wrong:       {self.wrong}
  Skipped:     {self.skipped}

{self.wrong} false positive(s) captured for model training.
"""

        return Panel(content.strip(), border_style="green")

    def _get_stats(self) -> dict:
        """Get session statistics."""
        return {
            "total_samples": self.total,
            "reviewed": self.reviewed,
            "correct": self.correct,
            "wrong": self.wrong,
            "skipped": self.skipped,
            "accuracy": self.correct / self.reviewed if self.reviewed > 0 else 0,
        }
