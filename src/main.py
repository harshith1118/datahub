"""DataHub-Sentinel CLI — monitor schema diffs, auto-fix SQL, and open PRs."""

import logging
import re
from pathlib import Path

import typer
from pydantic import BaseModel
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table

from datahub_client import DataHubClient
from github_client import GitHubClient

app = typer.Typer()
console = Console()

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, console=console, show_path=False)],
)
logger = logging.getLogger("datahub-sentinel")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class SchemaFieldChange(BaseModel):
    field_path: str
    previous_name: str
    new_name: str
    field_type: str
    nullable: bool


class SchemaEvent(BaseModel):
    event_type: str
    dataset_urn: str
    timestamp: int
    changes: list[SchemaFieldChange]
    downstream_urns: list[str]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def refactor_sql(sql: str, changes: list[SchemaFieldChange]) -> tuple[str, list[str]]:
    """Replace all occurrences of old column names with new names in SQL.

    Returns the fixed SQL and a list of human-readable change descriptions.
    """
    log_lines: list[str] = []
    for change in changes:
        count = sql.count(change.previous_name)
        if count == 0:
            logger.warning("'%s' not found in SQL — skipping", change.previous_name)
            continue
        sql = sql.replace(change.previous_name, change.new_name)
        log_lines.append(
            f"  {change.previous_name} -> {change.new_name}  ({count} occurrences)"
        )
    return sql, log_lines


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

@app.command()
def remediate(
    sql_path: str = typer.Option(
        "mock_data/broken_dbt_model.sql", "--sql-path", help="Path to the broken SQL file"
    ),
    event_path: str = typer.Option(
        "mock_data/schema_event.json", "--event-path", help="Path to the DataHub schema event JSON"
    ),
    pr_title: str = typer.Option(
        "fix: remediate schema breaking change", "--pr-title", help="Title for the GitHub PR"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview changes without creating PR or writing DataHub tags"
    ),
) -> None:
    """Full remediation pipeline: fix SQL -> create PR -> write DataHub tag."""
    console.print(Panel.fit("[bold cyan]DataHub-Sentinel — Remediation Pipeline[/]", border_style="cyan"))

    # ── 1. Load schema event ──────────────────────────────────────────────
    event_path_obj = Path(event_path)
    if not event_path_obj.exists():
        console.print(f"[red]Schema event file not found:[/] {event_path}")
        raise typer.Exit(1)

    event = SchemaEvent.model_validate_json(event_path_obj.read_text())
    console.print(f"\n[bold]Schema Event:[/]  {event.event_type}")
    console.print(f"  Dataset URN:     {event.dataset_urn}")
    console.print(f"  Downstream URNs: {', '.join(event.downstream_urns)}")
    for c in event.changes:
        console.print(f"  Change:          {c.previous_name} [yellow]->[/] {c.new_name}  ({c.field_type})")

    # ── 2. Read and refactor SQL ──────────────────────────────────────────
    sql_path_obj = Path(sql_path)
    if not sql_path_obj.exists():
        console.print(f"[red]SQL file not found:[/] {sql_path}")
        raise typer.Exit(1)

    original_sql = sql_path_obj.read_text()
    fixed_sql, change_log = refactor_sql(original_sql, event.changes)

    if not change_log:
        console.print("\n[yellow]No changes to apply. Exiting.[/]")
        raise typer.Exit(0)

    table = Table(title="Column Refactors Applied", title_style="bold green")
    table.add_column("Change", style="cyan")
    for line in change_log:
        table.add_row(line)
    console.print("\n", table)

    # ── 3. Dry-run guard ──────────────────────────────────────────────────
    gh = GitHubClient(dry_run=dry_run)
    dh = DataHubClient(dry_run=dry_run)

    if dry_run:
        console.print("\n[bold yellow]DRY RUN — no API calls will be made[/]")
        console.print(f"\n  Fixed SQL preview:\n[dim]{fixed_sql}[/]")
        console.print("\n  Would execute:")
        console.print("    1. Create branch   fix/schema-update")
        console.print("    2. Commit file     ", sql_path)
        console.print("    3. Open PR         ", pr_title)
        console.print("    4. Write tag       STATUS: FIX_PENDING_PR_<id>  ->", event.dataset_urn)
        console.print("    5. Incident link   ->", event.dataset_urn)
        console.print("\n[green]Dry-run complete. No changes were made.[/]")
        raise typer.Exit(0)

    # ── 4. GitHub: branch, commit, PR ────────────────────────────────────
    console.print("\n[bold]Step 1/3:[/] Creating GitHub branch...")
    gh.create_branch(base="main", branch_name="fix/schema-update")

    console.print("[bold]Step 2/3:[/] Committing fixed SQL...")
    gh.commit_file(
        file_path=sql_path,
        content=fixed_sql,
        message=pr_title,
        branch="fix/schema-update",
    )

    console.print("[bold]Step 3/3:[/] Opening Pull Request...")
    pr_body = (
        f"## Automated Remediation\n\n"
        f"**Schema event:** `{event.event_type}`\n"
        f"**Dataset:** `{event.dataset_urn}`\n\n"
        f"### Changes applied\n"
    )
    for line in change_log:
        pr_body += f"- {line.strip()}\n"
    pr_url = gh.create_pr(
        title=pr_title,
        body=pr_body,
        head="fix/schema-update",
        base="main",
    )
    console.print(f"\n[green]Pull Request created:[/] {pr_url}")

    # ── 5. DataHub write-back ────────────────────────────────────────────
    pr_number_match = re.search(r"/pull/(\d+)", pr_url)
    pr_number = pr_number_match.group(1) if pr_number_match else "unknown"
    tag = f"STATUS: FIX_PENDING_PR_{pr_number}"

    console.print(f"[bold]Step 4/4:[/] Writing back to DataHub...")
    dh.write_remediation_tag(event.dataset_urn, tag)
    dh.write_incident_link(event.dataset_urn, pr_url)

    # ── 6. Summary ────────────────────────────────────────────────────────
    console.print(
        Panel(
            f"[green]Remediation complete![/]\n\n"
            f"  PR URL:      {pr_url}\n"
            f"  DataHub tag: {tag}\n"
            f"  Dataset:     {event.dataset_urn}",
            title="Summary",
            border_style="green",
        )
    )


@app.command()
def pr(
    sql_path: str = typer.Argument(
        ..., help="Path to the fixed SQL file to commit and PR"
    ),
    pr_title: str = typer.Option(
        "fix: remediate schema breaking change", "--pr-title", help="Title for the GitHub PR"
    ),
    branch: str = typer.Option(
        "fix/schema-update", "--branch", help="Branch name to create and push to"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview changes without creating a PR"
    ),
) -> None:
    """Create a GitHub PR from a pre-fixed SQL file (no refactoring)."""
    console.print(Panel.fit("[bold cyan]DataHub-Sentinel — PR Submission[/]", border_style="cyan"))

    sql_path_obj = Path(sql_path)
    if not sql_path_obj.exists():
        console.print(f"[red]SQL file not found:[/] {sql_path}")
        raise typer.Exit(1)

    content = sql_path_obj.read_text()
    gh = GitHubClient(dry_run=dry_run)

    console.print(f"\n  File:    {sql_path}")
    console.print(f"  Branch:  {branch}")
    console.print(f"  Title:   {pr_title}")

    if dry_run:
        console.print("\n[bold yellow]DRY RUN — no API calls will be made[/]")
        console.print("  Would execute:")
        console.print(f"    1. Create branch   {branch}")
        console.print(f"    2. Commit file     {sql_path}")
        console.print(f"    3. Open PR         {pr_title}")
        console.print("\n[green]Dry-run complete. No changes were made.[/]")
        raise typer.Exit(0)

    console.print("\n[bold]Step 1/3:[/] Creating branch...")
    gh.create_branch(base="main", branch_name=branch)

    console.print("[bold]Step 2/3:[/] Committing SQL file...")
    gh.commit_file(file_path=sql_path, content=content, message=pr_title, branch=branch)

    console.print("[bold]Step 3/3:[/] Opening Pull Request...")
    pr_url = gh.create_pr(title=pr_title, body=f"Automated fix committed to `{sql_path}`.", head=branch, base="main")

    console.print(
        Panel(
            f"[green]PR submitted![/]\n\n  PR URL: {pr_url}",
            title="Summary",
            border_style="green",
        )
    )


@app.command()
def status(
    dataset_urn: str = typer.Argument(
        ..., help="URN of the dataset to check remediation status on"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview the query without calling DataHub"
    ),
) -> None:
    """Read schema metadata and remediation tags from DataHub for a dataset."""
    console.print(Panel.fit("[bold cyan]DataHub-Sentinel — Dataset Status[/]", border_style="cyan"))

    dh = DataHubClient(dry_run=dry_run)
    gh = GitHubClient(dry_run=dry_run)

    console.print(f"\n[bold]Dataset URN:[/] {dataset_urn}")

    if dry_run:
        console.print("\n[bold yellow]DRY RUN — no API calls will be made[/]")
        console.print("  Would execute:")
        console.print(f"    1. fetch_schema_diffs({dataset_urn})")
        console.print(f"    2. fetch_lineage({dataset_urn})")
        console.print("\n[green]Dry-run complete.[/]")
        raise typer.Exit(0)

    console.print("\n[bold]Fetching schema diffs...[/]")
    schema = dh.fetch_schema_diffs(dataset_urn)
    console.print(schema)

    console.print("\n[bold]Fetching lineage...[/]")
    lineage = dh.fetch_lineage(dataset_urn)
    console.print(lineage)


if __name__ == "__main__":
    app()