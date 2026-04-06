# Email Manager

Manage Gmail and Outlook email archives locally — read-only, never delete or forward.

## Step 0 — Check setup first

Before any other operation, check if setup has been done:

```bash
ls ~/projects/project-email-manager/config/accounts.yaml 2>/dev/null \
  && echo "CONFIG_EXISTS" || echo "SETUP_NEEDED"
```

If `SETUP_NEEDED`, run the guided setup wizard **before anything else**.

---

## Guided Setup Wizard

Run this and follow the interactive prompts:

```bash
cd ~/projects/project-email-manager
pip install -r requirements.txt -q
python run.py setup
```

The wizard will ask the user for each of these, **one step at a time**:

### Step 1 — Email address
Ask the user for their email address. Auto-detect provider (Gmail / Outlook / iCloud / other).

### Step 2 — App Password instructions
Show provider-specific instructions:

**Gmail:**
> 1. Go to myaccount.google.com → Security → 2-Step Verification (must be ON first)
> 2. Scroll to "App passwords" → select Mail / Other → name it "email-manager"
> 3. Copy the 16-character password
> 4. Enable IMAP: Gmail Settings → Forwarding and POP/IMAP → Enable IMAP

**Outlook / Microsoft 365:**
> 1. Go to account.microsoft.com → Security → Advanced security options → App passwords
> 2. Create new → name "email-manager" → copy the password
> 3. Enable IMAP: Outlook Settings → Mail → Sync email → Enable IMAP

**iCloud:**
> 1. Go to appleid.apple.com → Sign-In and Security → App-Specific Passwords
> 2. Generate new → name "email-manager"
> 3. Enable in iCloud Settings → iCloud Mail

### Step 3 — Test connection
The wizard tests IMAP login immediately and reports success or failure with a clear error.

### Step 4 — Archive directory
Ask where to save local email archives (default: `~/EmailArchive`).

### Step 5 — Confirm and save
Show a summary (email shown, password hidden as ***), ask for confirmation, then write `config/accounts.yaml`.

---

## Commands (after setup)

All commands run from `~/projects/project-email-manager/`:

```bash
# Sync new emails and categorize them
python run.py sync

# Sync a specific account only
python run.py sync --account gmail_personal --limit 200

# Search by keyword
python run.py search "招商银行"
python run.py search --category financial --since 2024-01-01

# List a category
python run.py list financial
python run.py list registrations
python run.py list business_trips

# Analyze business trip screenshot → auto-download related emails
python run.py trip /path/to/screenshot.png
python run.py trip /path/to/screenshot.png --dry-run
python run.py trip /path/to/screenshot.png --padding 5

# Open saved email folder in Finder
python run.py show "flight confirmation"

# Re-run setup (add / update accounts)
python run.py setup
```

---

## Email Categories

| Category | Saved to | What it captures |
|---|---|---|
| `financial` | `~/EmailArchive/financial/` | Bank statements, transaction alerts, fund/stock reports, invoices, payment receipts |
| `registrations` | `~/EmailArchive/registrations/` | Sign-up confirmations, verification codes, welcome emails |
| `business_trips` | `~/EmailArchive/business_trips/` | Flight/train/hotel bookings, itineraries, reimbursement receipts |

---

## Business Trip Screenshot Workflow

When the user provides a screenshot (trip approval form, OA system, itinerary):

1. Save the image to a temp path if needed
2. Run: `python run.py trip <path>`
3. Claude Vision extracts: departure date, return date, destinations, flight/train numbers, hotel names
4. The tool searches all mailboxes in that date range (± padding days)
5. Matching emails + attachments are downloaded to `~/EmailArchive/business_trips/`
6. Report what was found and where it was saved

---

## Local Archive Structure

```
~/EmailArchive/
├── index.json                          ← searchable index
├── financial/
│   └── 20240315_招商银行账单_uid1234/
│       ├── meta.json
│       ├── body.txt
│       └── attachments/statement.pdf
├── registrations/
│   └── 20240301_Welcome_GitHub_uid5678/
│       └── meta.json
└── business_trips/
    └── 20240410_电子行程单_uid9012/
        ├── meta.json
        └── attachments/行程单.pdf
```

---

## Troubleshooting

| Error | Fix |
|---|---|
| `Authentication failed` | Use App Password, not regular login password |
| `IMAP not enabled` | Gmail: Settings → Forwarding and POP/IMAP → Enable IMAP |
| `Connection refused` | Check host/port in accounts.yaml; corporate VPN may block IMAP |
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` first |
| No emails found after sync | Try `--limit 500`; check correct folder name with `python run.py accounts` |

---

## Safety Rules (enforce strictly)

- **Never** delete, move, forward, or reply to any email
- **Never** write or modify any email on the server
- All IMAP connections use `readonly=True`
- Credentials stay in local `accounts.yaml` only
