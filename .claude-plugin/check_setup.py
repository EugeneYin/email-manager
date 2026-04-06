#!/usr/bin/env python3
"""
Startup check: if accounts.yaml is missing, print a hint to Claude's context.
This runs as an async hook at SessionStart so Claude knows setup is needed.
"""
import sys
import os
from pathlib import Path

# Locate config relative to this plugin file
plugin_dir = Path(__file__).parent.parent
config_file = plugin_dir / "config" / "accounts.yaml"
config_exists = config_file.exists()

if not config_exists:
    # Write to stdout — Claude Code hooks inject stdout into context
    print(
        "[email-manager] accounts.yaml not found. "
        f"Run: python {plugin_dir}/run.py setup\n"
        "Or type /email-manager and ask Claude to run the setup wizard."
    )
    sys.exit(0)

# Quick sanity check: can we load and parse the config?
try:
    import yaml
    with open(config_file) as f:
        cfg = yaml.safe_load(f)
    accounts = cfg.get("accounts", [])
    if accounts:
        print(f"[email-manager] {len(accounts)} account(s) configured. Ready.")
    else:
        print("[email-manager] accounts.yaml exists but no accounts found. Run setup.")
except Exception as e:
    print(f"[email-manager] Config error: {e}. Run: python {plugin_dir}/run.py setup")
