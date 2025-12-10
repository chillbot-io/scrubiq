"""scrubIQ CLI - main entry point."""

import click
import json
import webbrowser
from pathlib import Path
from rich.table import Table

from .ui import ScanUI, console, print_error, print_warning, print_success, print_info
from ..scanner.scanner import Scanner
from ..storage.database import FindingsDatabase
from ..reporter.html import generate_html_report


@click.group()
@click.version_option(package_name="scrubiq")
def cli():
    """scrubIQ - Find and protect sensitive data."""
    pass


@cli.command()
@click.argument("path")
@click.option("--output", "-o", type=click.Path(), help="Save report to file")
@click.option(
    "--format",
    "-f",
    "fmt",
    type=click.Choice(["html", "json"]),
    default="html",
    help="Output format",
)
@click.option("--open", "open_report", is_flag=True, help="Open HTML report in browser")
@click.option("--store/--no-store", default=True, help="Store results in encrypted database")
@click.option("--presidio/--no-presidio", default=True, help="Use Presidio NER for names/addresses")
@click.option(
    "--apply-labels", is_flag=True, help="Apply sensitivity labels after scan (uses AIP client)"
)
@click.option("--dry-run", is_flag=True, help="Show what labels would be applied without applying")
@click.option("--quiet", "-q", is_flag=True, help="Minimal output")
def scan(
    path: str,
    output: str,
    fmt: str,
    open_report: bool,
    store: bool,
    presidio: bool,
    apply_labels: bool,
    dry_run: bool,
    quiet: bool,
):
    """Scan for sensitive data.

    PATH is a directory or file to scan.

    Examples:

        scrubiq scan ./documents

        scrubiq scan ./documents --open

        scrubiq scan ./documents --output report.html --format html

        scrubiq scan ./documents --output results.json --format json

        scrubiq scan "\\\\fileserver\\HR" --no-store

        scrubiq scan ./documents --apply-labels

        scrubiq scan ./documents --apply-labels --dry-run

        scrubiq scan ./documents --no-presidio  # Skip NER (faster)
    """
    path_obj = Path(path).resolve()

    if not path_obj.exists():
        print_error(f"Path not found: {path}")
        raise SystemExit(1)

    # Check AIP client if labeling requested
    aip_client = None
    if apply_labels:
        from ..labeler.aip import AIPClient
        from ..auth.config import Config

        aip_client = AIPClient()
        if not aip_client.is_available():
            print_error("AIP client not installed. Cannot apply labels to local files.")
            console.print("\nInstall the AIP client:")
            console.print(
                "  https://docs.microsoft.com/en-us/azure/information-protection/rms-client/install-unifiedlabelingclient-app"
            )
            console.print("\nOr use --no-apply-labels to scan without labeling.")
            raise SystemExit(1)

        # Check config for label mappings
        config = Config.load()
        if not config.has_label_mappings:
            print_warning("No label mappings configured.")
            console.print("Run: [bold]scrubiq config labels[/bold] to configure mappings.")
            console.print("\nContinuing scan without labeling...")
            apply_labels = False

    scanner = Scanner(enable_presidio=presidio)
    ui = ScanUI(quiet=quiet)

    # Count files first
    files = list(scanner._iter_files(path_obj))
    total = len(files)

    if total == 0:
        print_warning("No scannable files found.")
        raise SystemExit(0)

    if not quiet:
        print_info(f"Found {total} files to scan in {path_obj}")
        # Show Presidio status
        if presidio and scanner.classifier.has_presidio:
            console.print("[dim]  NER: Presidio enabled (names, addresses)[/dim]")
        elif presidio and not scanner.classifier.has_presidio:
            console.print(
                "[dim]  NER: Presidio not available (install with: pip install scrubiq\\[nlp])[/dim]"
            )
        else:
            console.print("[dim]  NER: Disabled (--no-presidio)[/dim]")

        if apply_labels:
            if dry_run:
                console.print("[dim]  Labeling: DRY-RUN (will show what would be labeled)[/dim]")
            else:
                console.print("[yellow]  Labeling: ENABLED (will apply labels after scan)[/yellow]")

        console.print()

    # Start UI and scan with live updates
    ui.start(total=total, source_path=str(path_obj))

    def on_file(result):
        ui.update(result)

    result = scanner.scan(str(path_obj), on_file=on_file)

    # Show completion summary
    ui.complete(result)

    # Store in encrypted database
    if store:
        db = FindingsDatabase()
        db.store_scan(result)
        db.close()
        if not quiet:
            console.print(
                f"\n[dim]Results stored in encrypted database (scan_id: {result.scan_id})[/dim]"
            )

    # Apply labels if requested
    if apply_labels and result.files_with_matches > 0:
        console.print("\n[bold]Applying Sensitivity Labels[/bold]")
        if dry_run:
            console.print("[dim]DRY-RUN: No changes will be made[/dim]\n")

        from ..auth.config import Config

        config = Config.load()

        labeled = 0
        skipped = 0
        errors = 0

        # Supported extensions for AIP labeling
        supported_extensions = {".docx", ".xlsx", ".pptx", ".pdf", ".doc", ".xls", ".ppt"}

        for file_result in result.files:
            if not file_result.has_sensitive_data:
                continue

            if not file_result.label_recommendation:
                continue

            # Check if file type is supported
            if file_result.path.suffix.lower() not in supported_extensions:
                if not quiet:
                    console.print(f"  [dim]Skip {file_result.path.name} (unsupported type)[/dim]")
                skipped += 1
                continue

            # Get label ID for recommendation
            label_id = config.get_label_id(file_result.label_recommendation.value)

            if not label_id:
                if not quiet:
                    console.print(
                        f"  [dim]Skip {file_result.path.name} (no label mapping for {file_result.label_recommendation.value})[/dim]"
                    )
                skipped += 1
                continue

            if dry_run:
                label_name = config.label_mappings.get(file_result.label_recommendation.value)
                label_display = (
                    label_name.label_name if label_name and label_name.label_name else label_id[:20]
                )
                console.print(f"  Would label: {file_result.path.name} → {label_display}")
                labeled += 1
            else:
                # Actually apply label
                success, message = aip_client.apply_label(
                    file_result.path,
                    label_id,
                    justification=config.labeling.default_justification,
                )

                if success:
                    if not quiet:
                        console.print(f"  [green]✓[/green] {file_result.path.name}")
                    labeled += 1
                else:
                    if not quiet:
                        console.print(f"  [red]✗[/red] {file_result.path.name}: {message}")
                    errors += 1

        # Summary
        console.print()
        if dry_run:
            print_info(f"Would label {labeled} files")
        else:
            print_success(f"Labeled {labeled} files")

        if skipped > 0:
            console.print(f"[dim]Skipped: {skipped}[/dim]")
        if errors > 0:
            console.print(f"[red]Errors: {errors}[/red]")

    # Generate report output
    if output or open_report:
        if fmt == "html":
            report_path = Path(output) if output else Path(f"scrubiq-report-{result.scan_id}.html")
            generate_html_report(result, report_path)
            print_success(f"Report saved to: {report_path}")

            if open_report:
                webbrowser.open(f"file://{report_path.resolve()}")
        else:
            # JSON format
            output_path = Path(output) if output else Path(f"scrubiq-results-{result.scan_id}.json")
            output_path.write_text(json.dumps(result.to_dict(), indent=2))
            print_success(f"Results saved to: {output_path}")

    # Show files with sensitive data
    if not quiet and result.files_with_matches > 0 and not apply_labels:
        console.print("\n[bold]Files with Sensitive Data:[/bold]")
        files_with_matches = [f for f in result.files if f.has_sensitive_data]
        for f in files_with_matches[:10]:
            label = f.label_recommendation.value if f.label_recommendation else "unknown"
            match_summary = ", ".join(set(m.entity_type.value for m in f.real_matches[:3]))
            console.print(
                f"  [yellow]•[/yellow] {f.path.name} → {match_summary} [dim]({label})[/dim]"
            )

        if len(files_with_matches) > 10:
            console.print(f"  [dim]... and {len(files_with_matches) - 10} more files[/dim]")

    # Exit code: 1 if sensitive data found
    if result.files_with_matches > 0:
        raise SystemExit(1)


@cli.command()
@click.option("--scan-id", help="Show details for specific scan")
def stats(scan_id: str):
    """Show database statistics."""
    try:
        db = FindingsDatabase()

        if scan_id:
            # Show specific scan details
            scan = db.get_scan(scan_id)
            if not scan:
                print_error(f"Scan not found: {scan_id}")
                db.close()
                raise SystemExit(1)

            console.print(f"\n[bold]Scan Details: {scan_id}[/bold]\n")
            console.print(f"  Source:          {scan['source_path']}")
            console.print(f"  Started:         {scan['started_at']}")
            console.print(f"  Files scanned:   {scan['total_files']:,}")
            console.print(f"  Files w/matches: {scan['files_with_matches']:,}")
            console.print(f"  Total matches:   {scan['total_matches']:,}")
        else:
            # Show overall stats
            stats = db.get_stats()
            audit_stats = db.audit.get_stats()

            console.print("\n[bold]Database Statistics[/bold]\n")
            console.print(f"  Scans:          {stats['scans']:>6,}")
            console.print(f"  Files:          {stats['files']:>6,}")
            console.print(f"  Matches:        {stats['matches']:>6,}")
            console.print(f"  Real matches:   {stats['real_matches']:>6,}")

            if stats["by_entity_type"]:
                console.print("\n[bold]By Entity Type:[/bold]")
                for entity, count in sorted(stats["by_entity_type"].items(), key=lambda x: -x[1]):
                    console.print(f"  {entity:<20} {count:>6,}")

            # List recent scans
            scans = db.list_scans(limit=5)
            if scans:
                console.print("\n[bold]Recent Scans:[/bold]")
                table = Table(show_header=True, header_style="bold", box=None)
                table.add_column("ID", style="dim")
                table.add_column("Date")
                table.add_column("Path")
                table.add_column("Files", justify="right")
                table.add_column("Matches", justify="right")

                for s in scans:
                    date = s["started_at"][:10] if s["started_at"] else "?"
                    path = (
                        s["source_path"][-40:] if len(s["source_path"]) > 40 else s["source_path"]
                    )
                    table.add_row(
                        s["scan_id"],
                        date,
                        path,
                        str(s["total_files"]),
                        str(s["total_matches"]),
                    )
                console.print(table)

            console.print("\n[bold]Audit Log:[/bold]")
            console.print(f"  Total entries:  {audit_stats['total_entries']:>6,}")

        db.close()

    except Exception as e:
        print_error(str(e))
        raise SystemExit(1)


@cli.command()
@click.option("--scan-id", help="Delete specific scan")
@click.option("--all", "purge_all", is_flag=True, help="Delete ALL data")
@click.confirmation_option(prompt="Are you sure you want to delete this data?")
def purge(scan_id: str, purge_all: bool):
    """Delete stored findings.

    Examples:

        scrubiq purge --scan-id abc123

        scrubiq purge --all
    """
    db = FindingsDatabase()

    if purge_all:
        count = db.purge_all()
        print_warning(f"Deleted all data ({count} matches)")
    elif scan_id:
        count = db.delete_scan(scan_id)
        if count >= 0:
            print_success(f"Deleted scan {scan_id} ({count} matches)")
        else:
            print_error(f"Scan not found: {scan_id}")
    else:
        print_error("Specify --scan-id or --all")
        db.close()
        raise SystemExit(1)

    db.close()


@cli.command()
@click.argument("scan_id")
@click.option("--decrypt/--no-decrypt", default=True, help="Decrypt sensitive values")
@click.option("--output", "-o", type=click.Path(), help="Export to JSON file")
def export(scan_id: str, decrypt: bool, output: str):
    """Export findings for a scan.

    Examples:

        scrubiq export abc123

        scrubiq export abc123 --output findings.json

        scrubiq export abc123 --no-decrypt
    """
    db = FindingsDatabase()

    scan = db.get_scan(scan_id)
    if not scan:
        print_error(f"Scan not found: {scan_id}")
        db.close()
        raise SystemExit(1)

    findings = list(db.get_findings(scan_id=scan_id, decrypt=decrypt))

    if output:
        output_path = Path(output)
        output_path.write_text(json.dumps(findings, indent=2, default=str))
        print_success(f"Exported {len(findings)} findings to: {output_path}")
    else:
        # Display findings
        console.print(f"\n[bold]Findings for scan {scan_id}[/bold]\n")

        for f in findings[:20]:
            entity = f["entity_type"]
            value = f.get("value", f["value_redacted"]) if decrypt else f["value_redacted"]
            confidence = f["confidence"]
            file_path = Path(f["file_path"]).name

            console.print(f"  [{entity}] {value} ({confidence:.0%}) in {file_path}")

        if len(findings) > 20:
            console.print(f"\n  [dim]... and {len(findings) - 20} more findings[/dim]")

        console.print(f"\n  Total: {len(findings)} findings")

    db.close()


@cli.command()
@click.argument("scan_id")
@click.option("--output", "-o", type=click.Path(), help="Output path for report")
@click.option("--open", "open_report", is_flag=True, help="Open report in browser")
def report(scan_id: str, output: str, open_report: bool):
    """Generate HTML report from stored scan.

    Examples:

        scrubiq report abc123 --open

        scrubiq report abc123 --output report.html
    """
    from ..scanner.results import ScanResult, FileResult, Match, EntityType, LabelRecommendation
    from datetime import datetime

    db = FindingsDatabase()

    scan = db.get_scan(scan_id)
    if not scan:
        print_error(f"Scan not found: {scan_id}")
        db.close()
        raise SystemExit(1)

    # Reconstruct ScanResult from database
    result = ScanResult(
        scan_id=scan["scan_id"],
        started_at=datetime.fromisoformat(scan["started_at"]) if scan["started_at"] else None,
        completed_at=(
            datetime.fromisoformat(scan["completed_at"]) if scan.get("completed_at") else None
        ),
        source_path=scan["source_path"],
        source_type=scan.get("source_type", "filesystem"),
    )

    # Get all files and findings
    files_data = db.get_files(scan_id=scan_id)
    findings_by_file: dict[str, list[dict]] = {}

    for finding in db.get_findings(scan_id=scan_id, decrypt=True):
        file_path = finding["file_path"]
        if file_path not in findings_by_file:
            findings_by_file[file_path] = []
        findings_by_file[file_path].append(finding)

    # Build FileResult objects
    for file_data in files_data:
        file_path = Path(file_data["file_path"])

        matches = []
        for f in findings_by_file.get(str(file_path), []):
            try:
                entity_type = EntityType(f["entity_type"])
            except ValueError:
                continue

            matches.append(
                Match(
                    entity_type=entity_type,
                    value=f.get("value", f["value_redacted"]),
                    start=0,
                    end=0,
                    confidence=f["confidence"],
                    detector=f.get("detector", "unknown"),
                    is_test_data=f.get("is_test_data", False),
                )
            )

        label_rec = None
        if file_data.get("label_recommendation"):
            try:
                label_rec = LabelRecommendation(file_data["label_recommendation"])
            except ValueError:
                pass

        file_result = FileResult(
            path=file_path,
            source="filesystem",
            size_bytes=file_data.get("size_bytes", 0),
            modified=(
                datetime.fromisoformat(file_data["modified"])
                if file_data.get("modified")
                else datetime.now()
            ),
            matches=matches,
            label_recommendation=label_rec,
        )
        result.add_file(file_result)

    db.close()

    # Generate report
    report_path = Path(output) if output else Path(f"scrubiq-report-{scan_id}.html")
    generate_html_report(result, report_path)
    print_success(f"Report saved to: {report_path}")

    if open_report:
        webbrowser.open(f"file://{report_path.resolve()}")


@cli.command()
@click.argument("scan_id")
@click.option(
    "--threshold", "-t", default=0.85, help="Review matches below this confidence (default: 0.85)"
)
@click.option("--limit", "-n", type=int, help="Maximum samples to review")
@click.option("--stats", "show_stats", is_flag=True, help="Show review statistics only")
def review(scan_id: str, threshold: float, limit: int, show_stats: bool):
    """Review low-confidence matches to improve accuracy.

    Matches below the confidence threshold are shown for human review.
    Verdicts are saved anonymously for model training.

    Examples:

        scrubiq review abc123

        scrubiq review abc123 --threshold 0.75

        scrubiq review abc123 --limit 20

        scrubiq review --stats
    """
    from ..review import ReviewSampler, ReviewTUI, ReviewStorage

    storage = ReviewStorage()

    # If --stats flag, just show statistics
    if show_stats:
        stats = storage.get_stats()
        console.print("\n[bold]Review Statistics[/bold]\n")
        console.print(f"  Total verdicts:    {stats['total']:>6,}")
        console.print(f"  True positives:    {stats['true_positives']:>6,}")
        console.print(f"  False positives:   {stats['false_positives']:>6,}")
        if stats["total"] > 0:
            console.print(f"  Detection accuracy: {stats['accuracy']:.1%}")

        if stats["by_entity_type"]:
            console.print("\n[bold]By Entity Type:[/bold]")
            for entity, count in sorted(stats["by_entity_type"].items(), key=lambda x: -x[1]):
                console.print(f"  {entity:<20} {count:>6,}")
        return

    # Open database
    db = FindingsDatabase()

    # Check scan exists
    scan = db.get_scan(scan_id)
    if not scan:
        print_error(f"Scan not found: {scan_id}")
        db.close()
        raise SystemExit(1)

    # Create sampler and get samples
    sampler = ReviewSampler(db)
    reviewable = sampler.count_reviewable(scan_id, max_confidence=threshold)

    if reviewable == 0:
        print_info(f"No matches below {threshold:.0%} confidence to review.")
        db.close()
        return

    # Show what we're reviewing
    print_info(f"Found {reviewable} matches below {threshold:.0%} confidence in scan {scan_id}")
    if limit:
        print_info(f"Reviewing up to {limit} samples")

    # Get samples
    samples = list(sampler.get_samples(scan_id, max_confidence=threshold, limit=limit))

    db.close()

    # Run review TUI
    tui = ReviewTUI(samples, storage, scan_id=scan_id)
    results = tui.run()

    # Show where verdicts are stored
    if results["reviewed"] > 0:
        console.print(f"\n[dim]Verdicts saved to: {storage.path}[/dim]")


@cli.command()
@click.option("--nemotron", "-n", default=5000, help="Max examples from Nemotron-PII dataset")
@click.option("--fp-per-type", "-f", default=100, help="False positive examples per entity type")
@click.option("--output", "-o", type=click.Path(), help="Output path for trained model")
@click.option("--data-only", is_flag=True, help="Only prepare data, don't train")
@click.option(
    "--iterations", "-i", default=20, help="Training iterations (more = better but slower)"
)
def train(nemotron: int, fp_per_type: int, output: str, data_only: bool, iterations: int):
    """Train the TP/FP classifier to reduce false positives.
    
    This trains a model to distinguish real PII from test data,
    examples, and other false positives.
    
    Prerequisites:
    
        pip install setfit datasets sentence-transformers
        
    First time - download Nemotron-PII dataset:
    
        python -c "from datasets import load_dataset; \\
            ds = load_dataset('nvidia/Nemotron-PII'); \\
            ds.save_to_disk('./nemotron_pii')"
    
    Examples:
    
        scrubiq train
        
        scrubiq train --output ./models/tpfp-v1
        
        scrubiq train --nemotron 10000 --iterations 30
        
        scrubiq train --data-only  # Just prepare dataset
    """
    from ..training.data import prepare_training_dataset
    from ..training.model import TPFPClassifier, is_available

    # Check dependencies
    if not data_only and not is_available():
        print_error("Training dependencies not installed.")
        console.print("\nInstall with:")
        console.print("  pip install setfit datasets sentence-transformers")
        raise SystemExit(1)

    # Prepare data
    console.print("[bold]Preparing training data...[/bold]\n")

    try:
        examples = prepare_training_dataset(
            nemotron_examples=nemotron,
            fp_per_type=fp_per_type,
            include_user_feedback=True,
        )
    except ImportError as e:
        print_error(f"Failed to load data: {e}")
        console.print("\nMake sure to download Nemotron-PII first:")
        console.print(
            "  python -c \"from datasets import load_dataset; ds = load_dataset('nvidia/Nemotron-PII'); ds.save_to_disk('./nemotron_pii')\""
        )
        raise SystemExit(1)
    except Exception as e:
        print_error(f"Failed to prepare data: {e}")
        raise SystemExit(1)

    if data_only:
        print_success("Data preparation complete.")
        return

    # Train model
    console.print("\n[bold]Training TP/FP classifier...[/bold]\n")

    classifier = TPFPClassifier()

    try:
        metrics = classifier.train(
            examples,
            num_iterations=iterations,
            show_progress=True,
        )
    except Exception as e:
        print_error(f"Training failed: {e}")
        raise SystemExit(1)

    # Save model
    if output:
        output_path = Path(output)
    else:
        # Default location
        from ..storage.database import get_data_dir

        output_path = get_data_dir() / "models" / "tpfp-v1"

    classifier.save(output_path)
    print_success(f"Model saved to: {output_path}")

    # Summary
    console.print("\n[bold]Training complete![/bold]")
    console.print(f"  Accuracy: {metrics.get('accuracy', 0):.1%}")
    console.print("\nTo use in scans, the model will be loaded automatically.")


# =============================================================================
# Setup and Configuration Commands
# =============================================================================


@cli.command()
@click.option("--manual", is_flag=True, help="Show manual setup instructions instead of wizard")
@click.option("--reset", is_flag=True, help="Clear existing configuration")
def setup(manual: bool, reset: bool):
    """Set up Microsoft 365 integration.

    This wizard will:
    1. Authenticate you with Microsoft 365 (requires Global Admin)
    2. Create an app registration in your tenant
    3. Grant the necessary permissions
    4. Save credentials securely

    After setup, scrubIQ can:
    - List sensitivity labels from your tenant
    - Apply labels to SharePoint/OneDrive files
    - Apply labels to local files (with AIP client)

    Examples:

        scrubiq setup              # Interactive wizard

        scrubiq setup --manual     # Show manual instructions

        scrubiq setup --reset      # Clear config and start over
    """
    from ..auth.config import Config, reset_config
    from ..auth.setup import AzureSetupWizard, ManualSetupGuide

    # Reset if requested
    if reset:
        if click.confirm("This will delete all saved credentials. Continue?"):
            reset_config()
            print_success("Configuration reset.")
        return

    # Manual setup
    if manual:
        console.print(ManualSetupGuide.get_instructions())
        return

    # Check existing config
    config = Config.load()
    if config.is_configured:
        console.print("[yellow]scrubIQ is already configured.[/yellow]")
        console.print(f"  Tenant: {config.tenant_id}")
        console.print(f"  Client: {config.client_id}")
        console.print("\nUse [bold]scrubiq setup --reset[/bold] to reconfigure.")
        return

    # Start setup wizard
    console.print(
        """
╔══════════════════════════════════════════════════════════════════════╗
║                         scrubIQ Setup                                 ║
╚══════════════════════════════════════════════════════════════════════╝
    """
    )

    console.print("This wizard will configure Microsoft 365 integration.\n")
    console.print("You will need:")
    console.print("  • Global Admin access to your Microsoft 365 tenant")
    console.print("  • A web browser for authentication\n")

    wizard = AzureSetupWizard()

    # Check if automated setup is available
    if not wizard.can_auto_setup:
        console.print("[yellow]Automated setup not available.[/yellow]")
        console.print("The bootstrap app is not configured.\n")
        console.print("Use [bold]--manual[/bold] for step-by-step instructions:")
        console.print("  scrubiq setup --manual\n")
        console.print("Or set credentials manually:")
        console.print("  scrubiq config set tenant_id <your-tenant-id>")
        console.print("  scrubiq config set client_id <your-client-id>")
        console.print("  scrubiq config set client_secret <your-secret>")
        return

    if not click.confirm("Ready to begin?"):
        return

    # Start device code flow
    console.print("\n[bold]Step 1: Authentication[/bold]")
    console.print("Opening browser for Microsoft sign-in...\n")

    try:
        flow = wizard.start_device_flow()

        # Show device code
        console.print(f"Go to: [cyan]{flow['verification_uri']}[/cyan]")
        console.print(f"Enter code: [bold yellow]{flow['user_code']}[/bold yellow]\n")

        # Try to open browser
        import webbrowser

        webbrowser.open(flow["verification_uri"])

        console.print("[dim]Waiting for authentication...[/dim]")

        # Complete setup
        def on_progress(msg):
            console.print(f"  {msg}")

        result = wizard.complete_setup(
            flow,
            app_name="scrubIQ",
            include_labeling_permissions=True,
            on_progress=on_progress,
        )

        if not result.success:
            print_error(f"Setup failed: {result.error}")
            raise SystemExit(1)

        # Save to config
        config.tenant_id = result.tenant_id
        config.client_id = result.client_id
        config.setup_complete = True
        config.app_created_by_setup = True
        config.save()

        # Save secret to keyring
        try:
            config.set_client_secret(result.client_secret)
            secret_location = "system keyring"
        except Exception:
            # Fall back to environment variable instruction
            secret_location = None

        console.print("\n" + "═" * 70)
        print_success("Setup complete!")
        console.print(f"\n  Tenant ID: {result.tenant_id}")
        console.print(f"  Client ID: {result.client_id}")

        if secret_location:
            console.print(f"  Secret:    stored in {secret_location}")
        else:
            console.print("\n[yellow]Note: Could not save secret to keyring.[/yellow]")
            console.print("Set this environment variable:")
            console.print(f"  export SCRUBIQ_CLIENT_SECRET='{result.client_secret}'")

        console.print("\n[bold]Next steps:[/bold]")
        console.print("  1. Configure label mappings: [cyan]scrubiq config labels[/cyan]")
        console.print("  2. Test connection:          [cyan]scrubiq labels[/cyan]")
        console.print(
            "  3. Scan and label:           [cyan]scrubiq scan ./docs --apply-labels[/cyan]"
        )

    except RuntimeError as e:
        print_error(str(e))
        console.print("\nTry manual setup instead:")
        console.print("  scrubiq setup --manual")
        raise SystemExit(1)


@cli.group()
def config():
    """Manage scrubIQ configuration."""
    pass


@config.command("show")
def config_show():
    """Show current configuration.

    Examples:

        scrubiq config show
    """
    from ..auth.config import Config, CONFIG_FILE

    config = Config.load()

    console.print("\n[bold]scrubIQ Configuration[/bold]\n")

    # Connection
    console.print("[bold]Microsoft 365 Connection:[/bold]")
    console.print(f"  Tenant ID:     {config.tenant_id or '[dim](not set)[/dim]'}")
    console.print(f"  Client ID:     {config.client_id or '[dim](not set)[/dim]'}")
    console.print(
        f"  Client Secret: {'[green]✓ configured[/green]' if config.get_client_secret() else '[dim](not set)[/dim]'}"
    )
    console.print(
        f"  Status:        {'[green]✓ Ready[/green]' if config.is_configured else '[yellow]⚠ Incomplete[/yellow]'}"
    )

    # Labeling
    console.print("\n[bold]Labeling Settings:[/bold]")
    console.print(f"  Method:              {config.labeling.method}")
    console.print(f"  Skip already labeled: {config.labeling.skip_already_labeled}")

    # Label mappings
    console.print("\n[bold]Label Mappings:[/bold]")
    has_mappings = False
    for rec, mapping in config.label_mappings.items():
        if mapping.skip:
            console.print(f"  {rec:<25} → [dim](skip)[/dim]")
        elif mapping.label_id:
            has_mappings = True
            label_display = mapping.label_name or mapping.label_id[:20] + "..."
            console.print(f"  {rec:<25} → {label_display}")
        else:
            console.print(f"  {rec:<25} → [dim](not mapped)[/dim]")

    if not has_mappings:
        console.print("\n  [yellow]No label mappings configured.[/yellow]")
        console.print("  Run [cyan]scrubiq config labels[/cyan] to configure.")

    # Config file location
    console.print(f"\n[dim]Config file: {CONFIG_FILE}[/dim]")


@config.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str):
    """Set a configuration value.

    Keys:

        tenant_id       Azure AD tenant ID
        client_id       Azure AD application ID
        client_secret   Application client secret (stored in keyring)
        method          Labeling method: aip_client or graph_api

    Examples:

        scrubiq config set tenant_id abc123-...

        scrubiq config set client_id def456-...

        scrubiq config set client_secret xyz789...

        scrubiq config set method aip_client
    """
    from ..auth.config import Config

    config = Config.load()

    if key == "tenant_id":
        config.tenant_id = value
        config.save()
        print_success("Tenant ID set.")

    elif key == "client_id":
        config.client_id = value
        config.save()
        print_success("Client ID set.")

    elif key == "client_secret":
        try:
            config.set_client_secret(value)
            print_success("Client secret stored in keyring.")
        except Exception as e:
            print_warning(f"Could not save to keyring: {e}")
            console.print("Set environment variable instead:")
            console.print(f"  export SCRUBIQ_CLIENT_SECRET='{value}'")

    elif key == "method":
        if value not in ("aip_client", "graph_api"):
            print_error("Method must be 'aip_client' or 'graph_api'")
            raise SystemExit(1)
        config.labeling.method = value
        config.save()
        print_success(f"Labeling method set to: {value}")

    else:
        print_error(f"Unknown key: {key}")
        console.print("\nValid keys: tenant_id, client_id, client_secret, method")
        raise SystemExit(1)


@config.command("labels")
def config_labels():
    """Configure label mappings interactively.

    Maps scrubIQ's classification recommendations to your tenant's
    sensitivity labels.

    Examples:

        scrubiq config labels
    """
    from ..auth.config import Config

    config = Config.load()

    # Try to get labels from tenant if configured
    labels = []
    if config.is_configured:
        console.print("[dim]Loading labels from tenant...[/dim]")
        try:
            from ..labeler import Labeler

            labeler = Labeler(config.tenant_id, config.client_id, config.get_client_secret())
            labels = labeler.get_labels()
            labeler.close()
        except Exception as e:
            print_warning(f"Could not load labels: {e}")

    if labels:
        console.print("\n[bold]Available labels in your tenant:[/bold]")
        for i, label in enumerate(labels, 1):
            console.print(f"  {i}. {label.get('name', label.get('id'))}")
        console.print()
    else:
        console.print("\n[yellow]Could not load labels from tenant.[/yellow]")
        console.print("You'll need to enter label IDs manually.\n")

    # Map each recommendation
    recommendations = [
        ("highly_confidential", "SSN, Credit Card, MRN, Health Plan ID"),
        ("confidential", "Names, Addresses, Diagnoses, Medications"),
        ("internal", "Email, Phone numbers"),
        ("public", "Low-confidence matches"),
    ]

    console.print("[bold]Map scrubIQ recommendations to your labels:[/bold]")
    console.print(
        "[dim]Enter label number, label ID, 'skip' to not label, or press Enter to keep current[/dim]\n"
    )

    for rec, description in recommendations:
        current = config.label_mappings.get(rec)
        current_display = "(not set)"
        if current and current.skip:
            current_display = "(skip)"
        elif current and current.label_name:
            current_display = current.label_name
        elif current and current.label_id:
            current_display = current.label_id[:20] + "..."

        console.print(f"[bold]{rec}[/bold] - {description}")
        console.print(f"  Current: {current_display}")

        choice = click.prompt("  New value", default="", show_default=False).strip()

        if not choice:
            # Keep current
            continue

        if choice.lower() == "skip":
            config.set_label_mapping(rec, skip=True)
            console.print("  → Will skip\n")
        elif choice.isdigit() and labels and 1 <= int(choice) <= len(labels):
            # Selected by number
            selected = labels[int(choice) - 1]
            config.set_label_mapping(
                rec,
                label_id=selected.get("id"),
                label_name=selected.get("name"),
            )
            console.print(f"  → {selected.get('name')}\n")
        else:
            # Assume it's a label ID
            config.set_label_mapping(rec, label_id=choice)
            console.print(f"  → {choice}\n")

    config.save()
    print_success("Label mappings saved.")


@config.command("test")
def config_test():
    """Test Microsoft 365 connection.

    Verifies that credentials are working and permissions are granted.

    Examples:

        scrubiq config test
    """
    from ..auth.config import Config
    from ..auth.graph import GraphClient, GraphAuthError, GraphAPIError

    config = Config.load()

    if not config.is_configured:
        print_error("Not configured. Run: scrubiq setup")
        raise SystemExit(1)

    console.print("[dim]Testing connection...[/dim]")

    try:
        client = GraphClient(
            config.tenant_id,
            config.client_id,
            config.get_client_secret(),
        )

        client.test_connection()
        print_success("✓ Authentication successful")

        # Test permissions
        try:
            labels = client.get_sensitivity_labels()
            print_success(f"✓ Can read sensitivity labels ({len(labels)} found)")
        except GraphAPIError as e:
            print_warning(f"✗ Cannot read labels: {e}")

        try:
            sites = client.list_sites()
            print_success(f"✓ Can list SharePoint sites ({len(sites)} found)")
        except GraphAPIError as e:
            print_warning(f"✗ Cannot list sites: {e}")

        client.close()

        # Test AIP client
        from ..labeler.aip import AIPClient

        aip = AIPClient()
        if aip.is_available():
            print_success(f"✓ AIP client available (v{aip.version})")
        else:
            console.print("[dim]  AIP client not installed (local labeling unavailable)[/dim]")

    except GraphAuthError as e:
        print_error(f"Authentication failed: {e}")
        console.print("\nCheck your credentials:")
        console.print("  scrubiq config show")
        raise SystemExit(1)


# =============================================================================
# Labeling Commands
# =============================================================================


def _get_credentials():
    """Get Microsoft credentials from config, keyring, or environment."""
    from ..auth.config import Config
    import os

    config = Config.load()

    # Config takes precedence
    tenant_id = config.tenant_id or os.environ.get("SCRUBIQ_TENANT_ID")
    client_id = config.client_id or os.environ.get("SCRUBIQ_CLIENT_ID")
    client_secret = config.get_client_secret()  # Checks keyring and env

    if not all([tenant_id, client_id, client_secret]):
        console.print("[yellow]Microsoft 365 credentials not found.[/yellow]")
        console.print("\nRun setup wizard:")
        console.print("  [bold]scrubiq setup[/bold]")
        console.print("\nOr set environment variables:")
        console.print("  SCRUBIQ_TENANT_ID     - Azure AD tenant ID")
        console.print("  SCRUBIQ_CLIENT_ID     - Azure AD application ID")
        console.print("  SCRUBIQ_CLIENT_SECRET - Application client secret")
        return None, None, None

    return tenant_id, client_id, client_secret


@cli.command("labels")
def list_labels():
    """List available sensitivity labels from Microsoft 365.

    Shows all sensitivity labels configured in your tenant.
    Use the label ID (GUID) or name with the 'label' command.

    Examples:

        scrubiq labels
    """
    tenant_id, client_id, client_secret = _get_credentials()
    if not tenant_id:
        raise SystemExit(1)

    from ..labeler import Labeler
    from ..auth.graph import GraphAuthError, GraphAPIError

    try:
        console.print("[dim]Connecting to Microsoft Graph...[/dim]")
        labeler = Labeler(tenant_id, client_id, client_secret)

        labels = labeler.get_labels()

        if not labels:
            print_warning("No sensitivity labels found in tenant.")
            console.print(
                "\nMake sure your Azure AD app has InformationProtectionPolicy.Read permission."
            )
            raise SystemExit(0)

        # Display as table
        table = Table(title="Sensitivity Labels")
        table.add_column("Name", style="cyan")
        table.add_column("ID", style="dim")
        table.add_column("Description")
        table.add_column("Color", style="bold")

        for label in labels:
            table.add_row(
                label.get("name", ""),
                label.get("id", "")[:8] + "...",
                (label.get("description", "") or "")[:40],
                label.get("color", ""),
            )

        console.print(table)
        console.print(f"\n[dim]Total: {len(labels)} labels[/dim]")

        # Show mapping hint
        console.print("\n[bold]scrubIQ Recommendation Mapping:[/bold]")
        labeler.auto_map_labels()
        for rec in ["highly_confidential", "confidential", "internal", "public"]:
            label_id = labeler.mapping._mappings.get(rec)
            if label_id:
                # Find name for ID
                name = next(
                    (lbl["name"] for lbl in labels if lbl["id"] == label_id), "?"
                )
                console.print(f"  {rec:<20} → {name}")
            else:
                console.print(f"  {rec:<20} → [dim](no match)[/dim]")

        labeler.close()

    except GraphAuthError as e:
        print_error(f"Authentication failed: {e}")
        console.print("\nCheck your credentials and try again.")
        raise SystemExit(1)
    except GraphAPIError as e:
        print_error(f"API error: {e}")
        raise SystemExit(1)


@cli.command("label")
@click.argument("scan_id")
@click.option("--apply", "do_apply", is_flag=True, help="Actually apply labels (default: dry-run)")
@click.option(
    "--label", "-l", "label_override", help="Apply specific label (name or ID) to all files"
)
@click.option("--skip-labeled/--include-labeled", default=True, help="Skip files already labeled")
def label(scan_id: str, do_apply: bool, label_override: str, skip_labeled: bool):
    """Apply sensitivity labels based on scan results.

    Uses stored scan results to apply appropriate Microsoft sensitivity
    labels to SharePoint/OneDrive files.

    SCAN_ID is the ID from a previous scan (see 'scrubiq stats').

    DRY-RUN BY DEFAULT: Use --apply to actually make changes.

    Examples:

        # Preview what would be labeled (dry-run)
        scrubiq label abc123

        # Actually apply labels
        scrubiq label abc123 --apply

        # Apply specific label to all files
        scrubiq label abc123 --label "Confidential" --apply

        # Include files that already have labels
        scrubiq label abc123 --include-labeled --apply
    """
    tenant_id, client_id, client_secret = _get_credentials()
    if not tenant_id:
        raise SystemExit(1)

    # Load scan results
    db = FindingsDatabase()
    scan_result = db.load_scan(scan_id)
    db.close()

    if scan_result is None:
        print_error(f"Scan not found: {scan_id}")
        console.print("\nUse [bold]scrubiq stats[/bold] to see available scans.")
        raise SystemExit(1)

    from ..labeler import Labeler
    from ..auth.graph import GraphAuthError, GraphAPIError

    # Status header
    if not do_apply:
        console.print("[yellow]DRY-RUN MODE[/yellow] - No changes will be made")
        console.print("Add [bold]--apply[/bold] to actually apply labels\n")
    else:
        console.print("[red bold]APPLYING LABELS[/red bold] - This will modify files\n")

    try:
        console.print("[dim]Connecting to Microsoft Graph...[/dim]")
        labeler = Labeler(tenant_id, client_id, client_secret)

        # Auto-map labels
        console.print("[dim]Loading sensitivity labels...[/dim]")
        labeler.auto_map_labels()

        # Count files to label
        files_with_recommendations = [
            f for f in scan_result.files if f.has_sensitive_data and f.label_recommendation
        ]

        console.print(f"\nScan: {scan_id}")
        console.print(f"Files with sensitive data: {len(files_with_recommendations)}")
        console.print()

        if not files_with_recommendations:
            print_warning("No files need labeling.")
            raise SystemExit(0)

        # Progress tracking
        from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console,
        ) as progress:

            task = progress.add_task("Labeling...", total=len(files_with_recommendations))

            def on_progress(current, total, path):
                progress.update(
                    task, completed=current, description=f"[dim]{Path(path).name[:30]}[/dim]"
                )

            results = labeler.apply_from_scan(
                scan_result,
                dry_run=not do_apply,
                on_progress=on_progress,
                skip_already_labeled=skip_labeled,
            )

        # Summary
        console.print()

        if do_apply:
            print_success(f"Labeled {results.labeled} files")
        else:
            print_info(f"Would label {results.labeled} files")

        if results.skipped > 0:
            console.print(f"[dim]Skipped: {results.skipped}[/dim]")
        if results.errors > 0:
            console.print(f"[red]Errors: {results.errors}[/red]")

        # By label breakdown
        if results.by_label:
            console.print("\n[bold]By Label:[/bold]")
            for label_name, count in sorted(results.by_label.items(), key=lambda x: -x[1]):
                console.print(f"  {label_name}: {count}")

        # Show errors
        errors = [r for r in results.results if r.error and not r.dry_run]
        if errors:
            console.print("\n[bold red]Errors:[/bold red]")
            for r in errors[:5]:  # Show first 5
                console.print(f"  {Path(r.path).name}: {r.error}")
            if len(errors) > 5:
                console.print(f"  ... and {len(errors) - 5} more")

        # Show skipped (for SharePoint metadata issue)
        sharepoint_skipped = [
            r
            for r in results.results
            if r.skipped and r.skip_reason and "SharePoint" in r.skip_reason
        ]
        if sharepoint_skipped:
            console.print(
                f"\n[yellow]Note: {len(sharepoint_skipped)} local files skipped (not in SharePoint)[/yellow]"
            )
            console.print("[dim]Labeling only works for SharePoint/OneDrive files.[/dim]")
            console.print("[dim]Use 'scrubiq scan-sharepoint' to scan cloud files directly.[/dim]")

        labeler.close()

    except GraphAuthError as e:
        print_error(f"Authentication failed: {e}")
        raise SystemExit(1)
    except GraphAPIError as e:
        print_error(f"API error: {e}")
        raise SystemExit(1)


@cli.command("scan-sharepoint")
@click.argument("site")
@click.option("--drive", "-d", help="Document library name or ID (default: Documents)")
@click.option("--folder", "-f", default="/", help="Folder path to scan (default: root)")
@click.option("--apply-labels", is_flag=True, help="Apply labels immediately after scan")
@click.option("--label", "-l", "label_override", help="Apply specific label to all sensitive files")
@click.option("--quiet", "-q", is_flag=True, help="Minimal output")
def scan_sharepoint(
    site: str, drive: str, folder: str, apply_labels: bool, label_override: str, quiet: bool
):
    """Scan SharePoint site and optionally apply labels.

    SITE is the SharePoint site URL or ID.

    Examples:

        # Scan a SharePoint site
        scrubiq scan-sharepoint "https://contoso.sharepoint.com/sites/HR"

        # Scan specific document library
        scrubiq scan-sharepoint contoso.sharepoint.com:/sites/HR --drive "Shared Documents"

        # Scan and apply labels in one step
        scrubiq scan-sharepoint https://contoso.sharepoint.com/sites/HR --apply-labels
    """
    tenant_id, client_id, client_secret = _get_credentials()
    if not tenant_id:
        raise SystemExit(1)

    from ..auth.graph import GraphClient, GraphAuthError, GraphAPIError

    console.print("[dim]Connecting to Microsoft Graph...[/dim]")

    try:
        client = GraphClient(tenant_id, client_id, client_secret)

        # Resolve site
        if site.startswith("http"):
            # Parse URL like https://contoso.sharepoint.com/sites/HR
            from urllib.parse import urlparse

            parsed = urlparse(site)
            hostname = parsed.netloc
            site_path = parsed.path.rstrip("/")
            site_info = client.get_site_by_url(hostname, site_path)
        else:
            # Try as site ID or hostname:/path format
            if ":/" in site:
                hostname, site_path = site.split(":/", 1)
                site_path = "/" + site_path
                site_info = client.get_site_by_url(hostname, site_path)
            else:
                site_info = client.get_site(site)

        site_id = site_info["id"]
        site_name = site_info.get("displayName", site_id)

        console.print(f"Site: [cyan]{site_name}[/cyan]")

        # Get drive
        drives = client.list_drives(site_id)

        if not drives:
            print_error("No document libraries found in site.")
            raise SystemExit(1)

        if drive:
            # Find by name or ID
            drive_info = next(
                (d for d in drives if d.get("name") == drive or d.get("id") == drive), None
            )
            if not drive_info:
                print_error(f"Document library not found: {drive}")
                console.print("Available libraries:")
                for d in drives:
                    console.print(f"  - {d.get('name')}")
                raise SystemExit(1)
        else:
            # Use first drive (usually "Documents")
            drive_info = drives[0]

        drive_id = drive_info["id"]
        drive_name = drive_info.get("name", drive_id)

        console.print(f"Library: [cyan]{drive_name}[/cyan]")

        # List files
        console.print("\n[dim]Scanning files...[/dim]")

        items = list(client.list_items_recursive(site_id, drive_id, "root"))

        console.print(f"Found [bold]{len(items)}[/bold] files")

        if not items:
            print_warning("No files to scan.")
            raise SystemExit(0)

        # Scan files
        # For now, download and scan locally
        # TODO: Stream content to avoid downloading large files

        print_warning("\nSharePoint scanning is a preview feature.")
        console.print("Full implementation coming in Phase 9.")

        client.close()

    except GraphAuthError as e:
        print_error(f"Authentication failed: {e}")
        raise SystemExit(1)
    except GraphAPIError as e:
        print_error(f"API error: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    cli()
