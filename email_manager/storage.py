"""Local storage — saves email metadata index and attachments."""
import json
import re
import os
from pathlib import Path
from datetime import datetime
from typing import Optional
from .imap_client import EmailMessage, EmailMeta
from .config import get_storage_paths


def _safe_filename(name: str) -> str:
    """Strip characters illegal in filenames."""
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    return name[:200]  # cap length


def _email_folder_name(meta: EmailMeta) -> str:
    """e.g. 20240315_Bank_Statement_uid123"""
    date_str = meta.date.strftime("%Y%m%d")
    subject_short = _safe_filename(meta.subject[:50])
    return f"{date_str}_{subject_short}_uid{meta.uid}"


class EmailStorage:
    def __init__(self, config: dict):
        self.paths = get_storage_paths(config)
        # Create all base dirs
        for p in self.paths.values():
            p.mkdir(parents=True, exist_ok=True)
        self.index_file = self.paths["base"] / "index.json"
        self._index: dict = self._load_index()

    # ------------------------------------------------------------------ #
    #  Index                                                               #
    # ------------------------------------------------------------------ #

    def _load_index(self) -> dict:
        if self.index_file.exists():
            with open(self.index_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_index(self):
        with open(self.index_file, "w", encoding="utf-8") as f:
            json.dump(self._index, f, ensure_ascii=False, indent=2, default=str)

    def index_key(self, meta: EmailMeta) -> str:
        return f"{meta.account_name}:{meta.uid}:{meta.folder}"

    def is_saved(self, meta: EmailMeta) -> bool:
        return self.index_key(meta) in self._index

    def get_entry(self, meta: EmailMeta) -> Optional[dict]:
        return self._index.get(self.index_key(meta))

    # ------------------------------------------------------------------ #
    #  Save                                                                #
    # ------------------------------------------------------------------ #

    def save_email(self, message: EmailMessage, category: str) -> Path:
        """
        Save email metadata, body text, and attachments under category folder.
        Returns the folder path where the email was saved.
        """
        meta = message.meta
        cat_path = self.paths.get(category, self.paths["base"])
        folder_name = _email_folder_name(meta)
        email_dir = cat_path / folder_name
        email_dir.mkdir(parents=True, exist_ok=True)

        # Save metadata JSON
        meta_file = email_dir / "meta.json"
        meta_data = {
            "uid": meta.uid,
            "account": meta.account_name,
            "folder": meta.folder,
            "subject": meta.subject,
            "sender": meta.sender,
            "date": meta.date.isoformat(),
            "message_id": meta.message_id,
            "category": category,
            "saved_at": datetime.now().isoformat(),
            "attachments": [],
        }

        # Save body
        if message.body_text:
            (email_dir / "body.txt").write_text(message.body_text, encoding="utf-8")
        if message.body_html:
            (email_dir / "body.html").write_text(message.body_html, encoding="utf-8")

        # Save attachments
        att_dir = email_dir / "attachments"
        for filename, data, content_type in message.attachments:
            safe_name = _safe_filename(filename)
            att_path = att_dir / safe_name
            att_dir.mkdir(exist_ok=True)
            att_path.write_bytes(data)
            meta_data["attachments"].append({
                "filename": filename,
                "saved_as": safe_name,
                "content_type": content_type,
                "size": len(data),
            })

        meta_file.write_text(json.dumps(meta_data, ensure_ascii=False, indent=2, default=str),
                             encoding="utf-8")

        # Update index
        self._index[self.index_key(meta)] = {
            "path": str(email_dir),
            "category": category,
            "subject": meta.subject,
            "sender": meta.sender,
            "date": meta.date.isoformat(),
        }
        self._save_index()

        return email_dir

    # ------------------------------------------------------------------ #
    #  Search index                                                        #
    # ------------------------------------------------------------------ #

    def search_index(
        self,
        keyword: Optional[str] = None,
        category: Optional[str] = None,
        since: Optional[datetime] = None,
        before: Optional[datetime] = None,
    ) -> list[dict]:
        """Full-text search over the saved index."""
        results = []
        for key, entry in self._index.items():
            if category and entry.get("category") != category:
                continue
            if keyword:
                kw = keyword.lower()
                if kw not in entry.get("subject", "").lower() and \
                   kw not in entry.get("sender", "").lower():
                    continue
            entry_date = None
            if "date" in entry:
                try:
                    entry_date = datetime.fromisoformat(entry["date"])
                except Exception:
                    pass
            if since and entry_date and entry_date < since:
                continue
            if before and entry_date and entry_date > before:
                continue
            results.append({**entry, "key": key})

        # Sort by date descending
        results.sort(key=lambda x: x.get("date", ""), reverse=True)
        return results

    def list_category(self, category: str) -> list[dict]:
        return self.search_index(category=category)
