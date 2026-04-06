"""IMAP client — read-only operations only (no move/delete/forward)."""
import ssl
import imaplib
import email
import email.header
from datetime import datetime, date
from typing import Iterator, Optional
from dataclasses import dataclass, field


@dataclass
class EmailMeta:
    uid: str
    subject: str
    sender: str
    date: datetime
    has_attachments: bool
    size: int
    folder: str
    account_name: str
    message_id: str = ""


@dataclass
class EmailMessage:
    meta: EmailMeta
    body_text: str = ""
    body_html: str = ""
    attachments: list = field(default_factory=list)  # list of (filename, data, content_type)
    raw: bytes = field(default=b"", repr=False)


def _decode_header(value: str) -> str:
    """Decode RFC2047-encoded email header."""
    if not value:
        return ""
    parts = []
    for fragment, charset in email.header.decode_header(value):
        if isinstance(fragment, bytes):
            parts.append(fragment.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(fragment)
    return "".join(parts)


def _parse_date(date_str: str) -> datetime:
    from email.utils import parsedate_to_datetime
    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        return datetime.now()


class IMAPClient:
    """Thin read-only IMAP wrapper. Deliberately omits store/expunge/copy."""

    def __init__(self, account: dict):
        self.account = account
        self.name = account["name"]
        self._conn: Optional[imaplib.IMAP4_SSL] = None

    # ------------------------------------------------------------------ #
    #  Connection management                                               #
    # ------------------------------------------------------------------ #

    def connect(self) -> "IMAPClient":
        host = self.account["imap_host"]
        port = self.account.get("imap_port", 993)
        use_ssl = self.account.get("use_ssl", True)

        if use_ssl:
            ctx = ssl.create_default_context()
            self._conn = imaplib.IMAP4_SSL(host, port, ssl_context=ctx)
        else:
            self._conn = imaplib.IMAP4(host, port)

        self._conn.login(self.account["email"], self.account["password"])
        return self

    def disconnect(self):
        if self._conn:
            try:
                self._conn.logout()
            except Exception:
                pass
            self._conn = None

    def __enter__(self):
        return self.connect()

    def __exit__(self, *_):
        self.disconnect()

    # ------------------------------------------------------------------ #
    #  Folder listing                                                      #
    # ------------------------------------------------------------------ #

    def list_folders(self) -> list[str]:
        status, data = self._conn.list()
        folders = []
        for item in data:
            if isinstance(item, bytes):
                parts = item.decode().split('"/"')
                if parts:
                    folders.append(parts[-1].strip().strip('"'))
        return folders

    # ------------------------------------------------------------------ #
    #  Search                                                              #
    # ------------------------------------------------------------------ #

    def search(
        self,
        folder: str = "INBOX",
        subject: Optional[str] = None,
        sender: Optional[str] = None,
        since: Optional[date] = None,
        before: Optional[date] = None,
        keywords: Optional[list[str]] = None,
        max_results: int = 200,
    ) -> list[str]:
        """Return UIDs matching the given criteria (read-only SEARCH)."""
        self._conn.select(folder, readonly=True)

        criteria = ["ALL"]
        if subject:
            criteria = [f'SUBJECT "{subject}"']
        elif keywords:
            # OR-chain multiple subject keywords
            terms = [f'SUBJECT "{kw}"' for kw in keywords]
            if len(terms) == 1:
                criteria = terms
            else:
                # Build nested OR: (OR (OR A B) C) ...
                combined = terms[0]
                for t in terms[1:]:
                    combined = f"(OR {combined} {t})"
                criteria = [combined]

        if sender:
            criteria.append(f'FROM "{sender}"')
        if since:
            criteria.append(f'SINCE {since.strftime("%d-%b-%Y")}')
        if before:
            criteria.append(f'BEFORE {before.strftime("%d-%b-%Y")}')

        query = " ".join(criteria) if criteria else "ALL"
        status, data = self._conn.uid("search", None, query)
        if status != "OK" or not data[0]:
            return []

        uids = data[0].split()
        # Return newest first, capped at max_results
        return [u.decode() for u in reversed(uids[-max_results:])]

    # ------------------------------------------------------------------ #
    #  Fetch                                                               #
    # ------------------------------------------------------------------ #

    def fetch_meta(self, uid: str, folder: str = "INBOX") -> Optional[EmailMeta]:
        """Fetch envelope metadata only (fast)."""
        self._conn.select(folder, readonly=True)
        status, data = self._conn.uid("fetch", uid, "(RFC822.SIZE FLAGS ENVELOPE)")
        if status != "OK" or not data[0]:
            return None

        raw = data[0]
        if isinstance(raw, tuple):
            raw = raw[1]

        # Parse envelope fields
        msg = email.message_from_bytes(self._fetch_raw_header(uid, folder))
        subject = _decode_header(msg.get("Subject", ""))
        sender = _decode_header(msg.get("From", ""))
        date_str = msg.get("Date", "")
        msg_id = msg.get("Message-ID", uid)
        size = self._parse_size(data)

        # Check for attachments by sniffing content-disposition without full download
        has_att = self._has_attachments_quick(uid, folder)

        return EmailMeta(
            uid=uid,
            subject=subject,
            sender=sender,
            date=_parse_date(date_str),
            has_attachments=has_att,
            size=size,
            folder=folder,
            account_name=self.name,
            message_id=msg_id,
        )

    def fetch_full(self, uid: str, folder: str = "INBOX") -> Optional[EmailMessage]:
        """Fetch complete email including body and attachments."""
        self._conn.select(folder, readonly=True)
        status, data = self._conn.uid("fetch", uid, "(RFC822)")
        if status != "OK" or not data[0]:
            return None

        raw_bytes = data[0][1] if isinstance(data[0], tuple) else data[0]
        msg = email.message_from_bytes(raw_bytes)

        subject = _decode_header(msg.get("Subject", ""))
        sender = _decode_header(msg.get("From", ""))
        date_str = msg.get("Date", "")
        msg_id = msg.get("Message-ID", uid)

        body_text = ""
        body_html = ""
        attachments = []

        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))

            if "attachment" in disposition or "inline" in disposition:
                filename = part.get_filename()
                if filename:
                    filename = _decode_header(filename)
                    payload = part.get_payload(decode=True)
                    if payload:
                        attachments.append((filename, payload, content_type))
            elif content_type == "text/plain" and not body_text:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    body_text = payload.decode(charset, errors="replace")
            elif content_type == "text/html" and not body_html:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    body_html = payload.decode(charset, errors="replace")

        meta = EmailMeta(
            uid=uid,
            subject=subject,
            sender=sender,
            date=_parse_date(date_str),
            has_attachments=bool(attachments),
            size=len(raw_bytes),
            folder=folder,
            account_name=self.name,
            message_id=msg_id,
        )

        return EmailMessage(
            meta=meta,
            body_text=body_text,
            body_html=body_html,
            attachments=attachments,
            raw=raw_bytes,
        )

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _fetch_raw_header(self, uid: str, folder: str) -> bytes:
        self._conn.select(folder, readonly=True)
        status, data = self._conn.uid("fetch", uid, "(RFC822.HEADER)")
        if status == "OK" and data[0]:
            return data[0][1] if isinstance(data[0], tuple) else data[0]
        return b""

    def _has_attachments_quick(self, uid: str, folder: str) -> bool:
        self._conn.select(folder, readonly=True)
        status, data = self._conn.uid("fetch", uid, "(BODYSTRUCTURE)")
        if status != "OK" or not data[0]:
            return False
        raw = data[0].decode() if isinstance(data[0], bytes) else str(data[0])
        return "attachment" in raw.lower() or "application/" in raw.lower()

    def _parse_size(self, data) -> int:
        try:
            raw = str(data)
            import re
            m = re.search(r"RFC822\.SIZE (\d+)", raw)
            return int(m.group(1)) if m else 0
        except Exception:
            return 0
