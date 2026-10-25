"""Identity Resolution Engine.

Resolves current and historical identifiers across user snapshots and audit logs.
"""

from __future__ import annotations

import csv
import hashlib
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set


def parse_timestamp(ts_str: str) -> Optional[datetime]:
    """Parse ISO and common datetime strings into datetime objects."""
    if not ts_str:
        return None
    for fmt in (
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(ts_str.strip(), fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(ts_str.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass
class UserProfile:
    user_id: str
    names: Set[str] = field(default_factory=set)
    emails: Set[str] = field(default_factory=set)
    phones: Set[str] = field(default_factory=set)
    email_hashes: Set[str] = field(default_factory=set)
    updated_at: Optional[datetime] = None

    def add_email(self, email: str) -> None:
        if email:
            norm_email = email.strip().lower()
            self.emails.add(norm_email)
            h = hashlib.sha256(norm_email.encode("utf-8")).hexdigest()
            self.email_hashes.add(h)

    def add_phone(self, phone: str) -> None:
        if phone:
            self.phones.add(phone.strip())

    def add_name(self, name: str) -> None:
        if name:
            self.names.add(name.strip())


class IdentityResolver:
    """Reconstructs historical identity graphs for users."""

    def __init__(self, identities_path: str, audit_log_path: str) -> None:
        self.identities_path = identities_path
        self.audit_log_path = audit_log_path
        self.users: Dict[str, UserProfile] = {}
        self.email_to_userid: Dict[str, str] = {}
        self.phone_to_userid: Dict[str, str] = {}
        self.hash_to_userid: Dict[str, str] = {}
        self._load_identities()
        self._load_audit_logs()

    def _load_identities(self) -> None:
        if not os.path.exists(self.identities_path):
            return

        with open(self.identities_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                user_id = row.get("user_id", "").strip()
                if not user_id:
                    continue

                profile = self.users.get(user_id, UserProfile(user_id=user_id))
                name = row.get("name", "")
                email = row.get("email", "")
                phone = row.get("phone", "")
                email_hash = row.get("email_hash", "")
                updated_at_str = row.get("updated_at", "")

                if name:
                    profile.add_name(name)
                if email:
                    profile.add_email(email)
                if phone:
                    profile.add_phone(phone)
                if email_hash:
                    profile.email_hashes.add(email_hash.strip().lower())
                if updated_at_str:
                    profile.updated_at = parse_timestamp(updated_at_str)

                self.users[user_id] = profile

                for e in profile.emails:
                    self.email_to_userid[e.lower()] = user_id
                for p in profile.phones:
                    self.phone_to_userid[p] = user_id
                for h in profile.email_hashes:
                    self.hash_to_userid[h.lower()] = user_id

    def _load_audit_logs(self) -> None:
        if not os.path.exists(self.audit_log_path):
            return

        with open(self.audit_log_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                user_id = row.get("user_id", "").strip()
                field_name = row.get("field_name", "").strip().lower()
                old_val = row.get("old_value", "").strip()
                new_val = row.get("new_value", "").strip()

                if not user_id:
                    # Attempt linkage via old or new identifier
                    if field_name in ("email", "user_email"):
                        user_id = self.email_to_userid.get(
                            old_val.lower()
                        ) or self.email_to_userid.get(new_val.lower(), "")
                    elif field_name in ("phone", "phone_number"):
                        user_id = self.phone_to_userid.get(
                            old_val
                        ) or self.phone_to_userid.get(new_val, "")

                if not user_id:
                    continue

                profile = self.users.get(user_id, UserProfile(user_id=user_id))

                for val in (old_val, new_val):
                    if not val:
                        continue
                    if field_name in ("email", "user_email"):
                        profile.add_email(val)
                        self.email_to_userid[val.lower()] = user_id
                    elif field_name in ("phone", "phone_number"):
                        profile.add_phone(val)
                        self.phone_to_userid[val] = user_id
                    elif field_name in ("name", "full_name"):
                        profile.add_name(val)
                    elif field_name in ("email_hash", "hash"):
                        profile.email_hashes.add(val.lower())
                        self.hash_to_userid[val.lower()] = user_id

                self.users[user_id] = profile

    def resolve_identifiers(
        self, case_id: str, request_email: str
    ) -> UserProfile:
        """Resolve all known current and historical identifiers for the target request."""
        norm_email = request_email.strip().lower() if request_email else ""
        user_id = self.email_to_userid.get(norm_email)

        if not user_id:
            # Fallback check against sha256 of request email
            req_hash = hashlib.sha256(norm_email.encode("utf-8")).hexdigest()
            user_id = self.hash_to_userid.get(req_hash)

        if not user_id:
            # Check user_id matches
            if norm_email in self.users:
                user_id = norm_email

        if not user_id:
            # Return an ephemeral profile if unmatched
            ephemeral = UserProfile(user_id=f"unknown_{case_id}")
            if norm_email:
                ephemeral.add_email(norm_email)
            return ephemeral

        return self.users[user_id]
