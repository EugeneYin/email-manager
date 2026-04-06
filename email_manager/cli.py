"""
Command-line interface for the email manager.
All operations are read-only (view/search/download). No delete/move/forward.
"""
import sys
import os
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from .config import load_config, get_storage_paths
from .imap_client import IMAPClient
from .categorizer import categorize
from .storage import EmailStorage
from .trip_analyzer import analyze_trip_screenshot, build_search_params, summarize_trip
from .setup_wizard import run_setup

console = Console()


def get_ai_client():
    """Return Anthropic client if API key available, else None."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        import anthropic
        return anthropic.Anthropic(api_key=api_key)
    except ImportError:
        return None


@click.group()
@click.option("--config", "-c", default=None, help="Path to accounts.yaml")
@click.pass_context
def cli(ctx, config):
    """Email Manager — read-only archival and search tool."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config


# ------------------------------------------------------------------ #
#  sync — fetch and categorize new emails                            #
# ------------------------------------------------------------------ #

# ------------------------------------------------------------------ #
#  setup — guided first-run configuration wizard                     #
# ------------------------------------------------------------------ #

@cli.command()
@click.option("--output", "-o", default=None,
              help="Where to write accounts.yaml (default: config/accounts.yaml)")
@click.pass_context
def setup(ctx, output):
    """Interactive wizard: add email accounts and generate accounts.yaml."""
    from pathlib import Path
    out_path = Path(output) if output else None
    run_setup(config_path=out_path)


# ------------------------------------------------------------------ #
#  sync — fetch and categorize new emails                            #
# ------------------------------------------------------------------ #

@cli.command()
@click.option("--account", "-a", default=None, help="Sync only this account name")
@click.option("--folder", "-f", default="INBOX", help="IMAP folder to sync")
@click.option("--limit", "-n", default=100, help="Max emails to fetch per account")
@click.option("--ai/--no-ai", default=True, help="Use Claude AI for ambiguous categorization")
@click.pass_context
def sync(ctx, account, folder, limit, ai):
    """Fetch recent emails and save categorized copies locally."""
    cfg = load_config(ctx.obj["config_path"])
    storage = EmailStorage(cfg)
    ai_client = get_ai_client() if ai else None

    accounts = cfg["accounts"]
    if account:
        accounts = [a for a in accounts if a["name"] == account]
        if not accounts:
            console.print(f"[red]Account '{account}' not found in config.[/red]")
            sys.exit(1)

    for acc in accounts:
        console.print(f"\n[bold cyan]Syncing {acc['name']} ({acc['email']})[/bold cyan]")
        with IMAPClient(acc) as client:
            _sync_account(client, folder, limit, cfg, storage, ai_client)


def _sync_account(client: IMAPClient, folder: str, limit: int,
                  cfg: dict, storage: EmailStorage, ai_client):
    cats = cfg.get("categories", {})
    # Collect all subject keywords across all categories for broad search
    all_kws = []
    for cat_rules in cats.values():
        all_kws.extend(cat_rules.get("keywords", {}).get("subject", []))

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  console=console) as progress:
        task = progress.add_task("Searching...", total=None)

        uids = client.search(folder=folder, keywords=all_kws[:10], max_results=limit)
        progress.update(task, description=f"Found {len(uids)} candidate emails")

        saved = skipped = uncategorized = 0
        for uid in uids:
            meta = client.fetch_meta(uid, folder)
            if not meta:
                continue

            if storage.is_saved(meta):
                skipped += 1
                continue

            # Quick rule-based check first
            cat = categorize(meta, cfg)
            if not cat and ai_client:
                msg = client.fetch_full(uid, folder)
                cat = categorize(meta, cfg, message=msg, ai_client=ai_client)
                if cat:
                    storage.save_email(msg, cat)
                    saved += 1
                    progress.update(task, description=f"Saved: {saved} | Skipped: {skipped}")
                    continue
            elif cat:
                msg = client.fetch_full(uid, folder)
                storage.save_email(msg, cat)
                saved += 1

            if not cat:
                uncategorized += 1

            progress.update(task, description=f"Saved: {saved} | Skipped: {skipped}")

    console.print(f"  [green]Saved:[/green] {saved}  [yellow]Skipped:[/yellow] {skipped}  "
                  f"[dim]Uncategorized:[/dim] {uncategorized}")


# ------------------------------------------------------------------ #
#  search — search saved index                                       #
# ------------------------------------------------------------------ #

@cli.command()
@click.argument("keyword", required=False)
@click.option("--category", "-c", type=click.Choice(["financial", "registrations",
                                                       "business_trips"]), default=None)
@click.option("--since", "-s", default=None, help="Since date YYYY-MM-DD")
@click.option("--before", "-b", default=None, help="Before date YYYY-MM-DD")
@click.pass_context
def search(ctx, keyword, category, since, before):
    """Search locally saved emails."""
    cfg = load_config(ctx.obj["config_path"])
    storage = EmailStorage(cfg)

    since_dt = datetime.strptime(since, "%Y-%m-%d") if since else None
    before_dt = datetime.strptime(before, "%Y-%m-%d") if before else None

    results = storage.search_index(
        keyword=keyword,
        category=category,
        since=since_dt,
        before=before_dt,
    )

    if not results:
        console.print("[yellow]No matching emails found.[/yellow]")
        return

    table = Table(title=f"Search results ({len(results)})", show_lines=True)
    table.add_column("Date", style="dim", width=12)
    table.add_column("Category", style="cyan", width=14)
    table.add_column("Subject", style="white")
    table.add_column("From", style="green")
    table.add_column("Path", style="dim")

    for entry in results[:50]:
        table.add_row(
            entry.get("date", "")[:10],
            entry.get("category", ""),
            entry.get("subject", "")[:60],
            entry.get("sender", "")[:40],
            entry.get("path", "")[-50:],
        )

    console.print(table)
    if len(results) > 50:
        console.print(f"[dim]... and {len(results) - 50} more[/dim]")


# ------------------------------------------------------------------ #
#  list — list category contents                                     #
# ------------------------------------------------------------------ #

@cli.command("list")
@click.argument("category", type=click.Choice(["financial", "registrations", "business_trips"]))
@click.pass_context
def list_cmd(ctx, category):
    """List all saved emails in a category."""
    ctx.invoke(search, keyword=None, category=category, since=None, before=None)


# ------------------------------------------------------------------ #
#  trip — analyze screenshot and find related emails                 #
# ------------------------------------------------------------------ #

@cli.command()
@click.argument("screenshot_path")
@click.option("--dry-run", is_flag=True, help="Show what would be found without saving")
@click.option("--padding", default=3, help="Days before/after trip to include in search")
@click.pass_context
def trip(ctx, screenshot_path, dry_run, padding):
    """
    Analyze a business trip screenshot, then find and save related emails.

    SCREENSHOT_PATH: path to trip approval/itinerary screenshot (PNG/JPG)
    """
    ai_client = get_ai_client()
    if not ai_client:
        console.print("[red]ANTHROPIC_API_KEY not set. Required for screenshot analysis.[/red]")
        sys.exit(1)

    console.print(Panel("[bold]Step 1: Analyzing screenshot with Claude Vision[/bold]"))
    with console.status("Analyzing image..."):
        trip_info = analyze_trip_screenshot(screenshot_path, ai_client)

    if trip_info.get("parse_error"):
        console.print(f"[red]Could not parse trip info:[/red] {trip_info.get('raw_response')}")
        sys.exit(1)

    console.print(summarize_trip(trip_info))

    params = build_search_params(trip_info, padding_days=padding)
    console.print(f"\n[bold]Search window:[/bold] {params['since']} → {params['before']}")
    console.print(f"[bold]Keywords:[/bold] {', '.join(params['keywords'][:10])}")

    cfg = load_config(ctx.obj["config_path"])
    storage = EmailStorage(cfg)

    if dry_run:
        console.print("\n[yellow]--dry-run: not saving anything.[/yellow]")
        return

    console.print(Panel("[bold]Step 2: Searching mailboxes[/bold]"))
    total_saved = 0

    for acc in cfg["accounts"]:
        console.print(f"\n[cyan]{acc['name']}[/cyan]")
        with IMAPClient(acc) as client:
            for kw_batch in _chunks(params["keywords"], 5):
                uids = client.search(
                    folder="INBOX",
                    keywords=kw_batch,
                    since=params["since"],
                    before=params["before"],
                    max_results=200,
                )
                for uid in uids:
                    meta = client.fetch_meta(uid)
                    if not meta or storage.is_saved(meta):
                        continue
                    msg = client.fetch_full(uid)
                    if msg:
                        email_dir = storage.save_email(msg, "business_trips")
                        console.print(f"  [green]✓[/green] {meta.subject[:60]}")
                        total_saved += 1

    paths = get_storage_paths(cfg)
    console.print(f"\n[bold green]{total_saved} emails saved to:[/bold green]")
    console.print(f"  {paths['business_trips']}")


# ------------------------------------------------------------------ #
#  show — open a saved email folder                                  #
# ------------------------------------------------------------------ #

@cli.command()
@click.argument("search_term")
@click.pass_context
def show(ctx, search_term):
    """Open the local folder for an email matching the search term."""
    cfg = load_config(ctx.obj["config_path"])
    storage = EmailStorage(cfg)
    results = storage.search_index(keyword=search_term)
    if not results:
        console.print("[yellow]No match found.[/yellow]")
        return
    path = results[0]["path"]
    console.print(f"Opening: [cyan]{path}[/cyan]")
    import subprocess
    subprocess.run(["open", path])  # macOS; use xdg-open on Linux


# ------------------------------------------------------------------ #
#  accounts — list configured accounts                               #
# ------------------------------------------------------------------ #

@cli.command()
@click.pass_context
def accounts(ctx):
    """List configured email accounts."""
    cfg = load_config(ctx.obj["config_path"])
    table = Table(title="Configured Accounts")
    table.add_column("Name", style="cyan")
    table.add_column("Email")
    table.add_column("Type")
    table.add_column("Host")
    for acc in cfg["accounts"]:
        table.add_row(acc["name"], acc["email"], acc.get("type", "imap"),
                      acc["imap_host"])
    console.print(table)


def _chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


if __name__ == "__main__":
    cli()
