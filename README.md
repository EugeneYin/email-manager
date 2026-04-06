# email-manager — Claude Code Plugin

Read-only email archival and organization for Gmail and Outlook.

**What it does**
- Connects via IMAP (read-only — no delete, move, or forward ever)
- Categorizes emails into: **financial**, **registrations**, **business_trips**
- Downloads attachments and saves them in organized local folders
- Analyzes business trip screenshots with Claude Vision to auto-fetch related travel emails

**Trigger:** `/email-manager` in Claude Code

---

## Install

### From GitHub release (recommended)

```bash
# Download latest release zip from the Releases page, then:
unzip email-manager-X.Y.Z.zip -d ~/.claude/plugins/email-manager
cd ~/.claude/plugins/email-manager
pip install -r requirements.txt
python run.py setup
```

### From source

```bash
git clone https://github.com/<you>/email-manager
cd email-manager
pip install -r requirements.txt
python run.py setup
```

---

## First-run setup

```bash
python run.py setup
```

The wizard walks you through, step by step:
1. Enter your email address (auto-detects Gmail / Outlook / iCloud)
2. Shows exact instructions to generate an **App Password** for your provider
3. Tests the IMAP connection live
4. Asks where to save your local archive (`~/EmailArchive` by default)
5. Writes `config/accounts.yaml`

You can re-run `setup` at any time to add more accounts.

---

## Commands

| Command | What it does |
|---|---|
| `python run.py setup` | First-run config wizard |
| `python run.py sync` | Fetch & categorize new emails |
| `python run.py search "keyword"` | Search saved emails |
| `python run.py list financial` | List saved financial emails |
| `python run.py list registrations` | List app registration emails |
| `python run.py list business_trips` | List travel/expense emails |
| `python run.py trip screenshot.png` | Analyze trip screenshot → download related emails |
| `python run.py show "keyword"` | Open email folder in Finder |

---

## Archive structure

```
~/EmailArchive/
├── index.json
├── financial/          ← bank statements, invoices, stock alerts
├── registrations/      ← sign-up confirmations, verification codes
└── business_trips/     ← flight/hotel bookings, itineraries, receipts
```

---

## Security

- Credentials stored locally in `config/accounts.yaml` only
- `accounts.yaml` is in `.gitignore` — never committed
- All IMAP access is strictly read-only (`readonly=True`)
- No email is modified, moved, forwarded, or deleted

---

## Build & release

```bash
./build.sh 1.0.0          # creates dist/email-manager-1.0.0.zip
git tag v1.0.0 && git push --tags   # triggers GitHub Actions release
```
