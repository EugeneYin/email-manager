"""Rule-based + AI-assisted email categorization."""
import re
from typing import Optional
from .imap_client import EmailMeta, EmailMessage


CATEGORIES = ("financial", "registrations", "business_trips")


def _match_any(text: str, patterns: list[str]) -> bool:
    text_lower = text.lower()
    return any(p.lower() in text_lower for p in patterns)


def categorize_by_rules(meta: EmailMeta, config: dict) -> Optional[str]:
    """
    Return category name or None if no rule matches.
    Priority: financial > business_trips > registrations
    """
    cats = config.get("categories", {})

    for cat in ("financial", "business_trips", "registrations"):
        rules = cats.get(cat, {})
        subject_kws = rules.get("keywords", {}).get("subject", [])
        senders = rules.get("senders", [])

        if _match_any(meta.subject, subject_kws):
            return cat
        if any(_match_any(meta.sender, [s]) for s in senders):
            return cat

    return None


def categorize_by_ai(message: EmailMessage, client) -> Optional[str]:
    """
    Use Claude to classify ambiguous emails. client is anthropic.Anthropic().
    Returns one of: 'financial', 'registrations', 'business_trips', or None.
    """
    snippet = (message.body_text or "")[:800]
    prompt = f"""Classify this email into exactly one category, or reply "none".

Categories:
- financial: bank statements, transaction alerts, investment reports, payment receipts, credit card bills
- registrations: account sign-up confirmations, email verifications, welcome emails for new services
- business_trips: flight/train/hotel bookings, itineraries, expense reimbursement receipts

Email:
Subject: {message.meta.subject}
From: {message.meta.sender}
Body snippet: {snippet}

Reply with just the category name or "none"."""

    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=10,
            messages=[{"role": "user", "content": prompt}],
        )
        result = resp.content[0].text.strip().lower()
        return result if result in CATEGORIES else None
    except Exception:
        return None


def categorize(meta: EmailMeta, config: dict, message: Optional[EmailMessage] = None,
               ai_client=None) -> Optional[str]:
    """Try rule-based first; fall back to AI if message body provided."""
    cat = categorize_by_rules(meta, config)
    if cat:
        return cat
    if message and ai_client:
        return categorize_by_ai(message, ai_client)
    return None
