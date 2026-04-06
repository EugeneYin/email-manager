"""
Interactive first-run setup wizard.
Collects account credentials and writes accounts.yaml.
Run via: python run.py setup
"""
import sys
import ssl
import imaplib
import getpass
from pathlib import Path
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.rule import Rule

console = Console()

# IMAP presets for common providers
PROVIDER_PRESETS = {
    "gmail": {
        "imap_host": "imap.gmail.com",
        "imap_port": 993,
        "use_ssl": True,
        "setup_url": "https://myaccount.google.com/apppasswords",
        "instructions": (
            "Gmail requires an App Password (not your regular login password).\n"
            "Steps:\n"
            "  1. Go to myaccount.google.com → Security → 2-Step Verification (must be ON)\n"
            "  2. Scroll down to 'App passwords' and click it\n"
            "  3. Select app: Mail, device: Other → type 'email-manager'\n"
            "  4. Copy the 16-character password shown\n"
            "  5. Also enable IMAP: Gmail Settings → See all settings → \n"
            "     Forwarding and POP/IMAP → Enable IMAP"
        ),
    },
    "outlook": {
        "imap_host": "outlook.office365.com",
        "imap_port": 993,
        "use_ssl": True,
        "setup_url": "https://account.microsoft.com/security",
        "instructions": (
            "Outlook/Microsoft 365 requires an App Password if MFA is enabled.\n"
            "Steps:\n"
            "  1. Go to account.microsoft.com → Security → Advanced security options\n"
            "  2. Under 'App passwords', create a new one named 'email-manager'\n"
            "  3. Copy the generated password\n"
            "  4. Also enable IMAP: Outlook Settings → Mail → Sync email → Enable IMAP"
        ),
    },
    "icloud": {
        "imap_host": "imap.mail.me.com",
        "imap_port": 993,
        "use_ssl": True,
        "instructions": (
            "iCloud Mail requires an App-Specific Password.\n"
            "Steps:\n"
            "  1. Go to appleid.apple.com → Sign-In and Security → App-Specific Passwords\n"
            "  2. Generate a new password named 'email-manager'\n"
            "  3. Enable IMAP: iCloud Settings → iCloud Mail → Enable"
        ),
    },
    "other": {
        "imap_host": "",
        "imap_port": 993,
        "use_ssl": True,
        "instructions": "Enter your IMAP server details manually.",
    },
}


def _detect_provider(email: str) -> str:
    domain = email.lower().split("@")[-1] if "@" in email else ""
    if "gmail" in domain or "googlemail" in domain:
        return "gmail"
    if "outlook" in domain or "hotmail" in domain or "live" in domain or "microsoft" in domain:
        return "outlook"
    if "icloud" in domain or "me.com" in domain or "mac.com" in domain:
        return "icloud"
    return "other"


def _test_connection(host: str, port: int, use_ssl: bool, email: str, password: str) -> tuple[bool, str]:
    """Try logging in. Returns (success, error_message)."""
    try:
        if use_ssl:
            ctx = ssl.create_default_context()
            conn = imaplib.IMAP4_SSL(host, port, ssl_context=ctx)
        else:
            conn = imaplib.IMAP4(host, port)
        conn.login(email, password)
        conn.logout()
        return True, ""
    except imaplib.IMAP4.error as e:
        return False, f"Authentication failed: {e}"
    except OSError as e:
        return False, f"Connection error: {e}"
    except Exception as e:
        return False, str(e)


def _add_account(existing_names: set) -> dict | None:
    """Interactively collect one account's details. Returns config dict or None to skip."""
    console.print(Rule())

    # Email address
    email = Prompt.ask("[cyan]Email address[/cyan]").strip()
    if not email or "@" not in email:
        console.print("[red]Invalid email address.[/red]")
        return None

    # Auto-detect provider
    detected = _detect_provider(email)
    provider_labels = {"gmail": "Gmail", "outlook": "Outlook/Microsoft 365",
                       "icloud": "iCloud", "other": "Other (custom IMAP)"}
    console.print(f"  Detected provider: [bold]{provider_labels[detected]}[/bold]")

    choices = list(PROVIDER_PRESETS.keys())
    provider = Prompt.ask(
        "Provider",
        choices=choices,
        default=detected,
    )

    preset = PROVIDER_PRESETS[provider]

    # Show setup instructions
    console.print(Panel(preset["instructions"], title="Setup instructions", border_style="yellow"))

    # IMAP host (allow override for "other")
    if provider == "other":
        host = Prompt.ask("[cyan]IMAP host[/cyan] (e.g. mail.example.com)").strip()
        port = int(Prompt.ask("[cyan]IMAP port[/cyan]", default="993"))
        use_ssl = Confirm.ask("Use SSL/TLS?", default=True)
    else:
        host = preset["imap_host"]
        port = preset["imap_port"]
        use_ssl = preset["use_ssl"]
        console.print(f"  IMAP: [dim]{host}:{port} (SSL)[/dim]")

    # App password / token
    console.print(f"\n[cyan]Enter your app password[/cyan] (input hidden):")
    password = getpass.getpass("  App password: ")
    if not password:
        console.print("[red]Password cannot be empty.[/red]")
        return None

    # Test connection
    with console.status("Testing connection..."):
        ok, err = _test_connection(host, port, use_ssl, email, password)

    if ok:
        console.print("[green]✓ Connection successful![/green]")
    else:
        console.print(f"[red]✗ Connection failed: {err}[/red]")
        if not Confirm.ask("Save anyway?", default=False):
            return None

    # Account name (unique)
    default_name = f"{provider}_{email.split('@')[0]}"
    while True:
        name = Prompt.ask("[cyan]Account nickname[/cyan]", default=default_name).strip()
        if name not in existing_names:
            break
        console.print(f"[red]Name '{name}' already used. Choose another.[/red]")

    return {
        "name": name,
        "type": provider,
        "email": email,
        "password": password,
        "imap_host": host,
        "imap_port": port,
        "use_ssl": use_ssl,
    }


def run_setup(config_path: Path | None = None) -> Path:
    """
    Run the interactive setup wizard.
    Returns the path to the written accounts.yaml.
    """
    console.print(Panel(
        "[bold]Email Manager — First-run Setup Wizard[/bold]\n\n"
        "This wizard will help you connect your Gmail / Outlook / other mail accounts.\n"
        "Credentials are stored locally in accounts.yaml (never sent anywhere).\n"
        "You can re-run [cyan]python run.py setup[/cyan] at any time to add or update accounts.",
        border_style="blue",
    ))

    # Determine config path
    if config_path is None:
        default_path = Path(__file__).parent.parent / "config" / "accounts.yaml"
        config_path = Path(Prompt.ask(
            "[cyan]Where to save accounts.yaml[/cyan]",
            default=str(default_path),
        ))

    # Load existing config if present
    existing_config: dict = {}
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            existing_config = yaml.safe_load(f) or {}
        console.print(f"[dim]Existing config found at {config_path}[/dim]")

    existing_accounts: list = existing_config.get("accounts", [])
    existing_names = {a["name"] for a in existing_accounts}

    accounts = list(existing_accounts)

    # Add accounts loop
    while True:
        acc = _add_account(existing_names)
        if acc:
            # Replace if same name exists
            accounts = [a for a in accounts if a["name"] != acc["name"]]
            accounts.append(acc)
            existing_names.add(acc["name"])
            console.print(f"  [green]Account '{acc['name']}' added.[/green]")

        if not Confirm.ask("\nAdd another account?", default=False):
            break

    if not accounts:
        console.print("[yellow]No accounts configured. Exiting.[/yellow]")
        sys.exit(0)

    # Storage directory
    console.print(Rule())
    archive_dir = Prompt.ask(
        "[cyan]Local archive directory[/cyan]",
        default=str(Path.home() / "EmailArchive"),
    ).strip()

    # Build final config (preserve existing categories if present)
    config = existing_config.copy()
    config["accounts"] = accounts
    config.setdefault("storage", {})
    config["storage"]["base_dir"] = archive_dir
    config["storage"].setdefault("financial_dir", "financial")
    config["storage"].setdefault("registrations_dir", "registrations")
    config["storage"].setdefault("business_trips_dir", "business_trips")

    # Load default categories from example file if not set
    if "categories" not in config:
        example = Path(__file__).parent.parent / "config" / "accounts.example.yaml"
        if example.exists():
            with open(example, "r") as f:
                example_cfg = yaml.safe_load(f)
            config["categories"] = example_cfg.get("categories", {})

    # Write config
    config_path.parent.mkdir(parents=True, exist_ok=True)
    # Strip passwords from display
    display_accounts = [
        {**a, "password": "***"} for a in accounts
    ]

    console.print(Panel(
        "\n".join(f"  [green]✓[/green] {a['email']} ({a['name']})" for a in accounts),
        title=f"Saving {len(accounts)} account(s)",
        border_style="green",
    ))

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    console.print(f"\n[bold green]Setup complete![/bold green] Config saved to: [cyan]{config_path}[/cyan]")
    console.print("\nNext steps:")
    console.print("  [dim]python run.py sync[/dim]           — fetch and categorize emails")
    console.print("  [dim]python run.py list financial[/dim] — view saved financial emails")
    console.print("  [dim]python run.py trip <image>[/dim]   — process a business trip screenshot")

    return config_path
