"""Configuration loader for email accounts and categories."""
import os
import yaml
from pathlib import Path
from typing import Optional


def load_config(config_path: Optional[str] = None) -> dict:
    """Load account and category configuration."""
    if config_path is None:
        # Search order: project config dir, home dir, current dir
        search_paths = [
            Path(__file__).parent.parent / "config" / "accounts.yaml",
            Path.home() / ".email_manager" / "accounts.yaml",
            Path("accounts.yaml"),
        ]
        for p in search_paths:
            if p.exists():
                config_path = str(p)
                break
        else:
            raise FileNotFoundError(
                "accounts.yaml not found. Copy config/accounts.example.yaml to "
                "config/accounts.yaml and fill in your credentials."
            )

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # Expand ~ in storage paths
    storage = config.get("storage", {})
    base_dir = Path(storage.get("base_dir", "~/EmailArchive")).expanduser()
    config["storage"]["base_dir"] = str(base_dir)

    return config


def get_storage_paths(config: dict) -> dict:
    """Return resolved absolute storage paths for each category."""
    storage = config["storage"]
    base = Path(storage["base_dir"])
    return {
        "base": base,
        "financial": base / storage.get("financial_dir", "financial"),
        "registrations": base / storage.get("registrations_dir", "registrations"),
        "business_trips": base / storage.get("business_trips_dir", "business_trips"),
    }
