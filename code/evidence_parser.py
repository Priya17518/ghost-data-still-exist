"""Corpus & Evidence Parser.

Ingests SQLite DB snapshots, JSON logs, textual evidence, and system activities.
"""

from __future__ import annotations

import csv
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from identity_resolver import UserProfile, parse_timestamp


@dataclass
class EvidenceItem:
    evidence_id: str
    file_path: str
    system_id: str
    resource_id: str
    file_type: str
    created_at: Optional[datetime] = None


@dataclass
class ActivityItem:
    activity_id: str
    timestamp: Optional[datetime]
    system_id: str
    resource_id: str
    activity_type: str
    status: str
    user_id: str
    details: str


class EvidenceParser:
    """Extracts ground-truth system states from evidence files and activities."""

    def __init__(
        self,
        evidence_manifest_path: str,
        evidence_dir: str,
        activity_path: str,
    ) -> None:
        self.evidence_manifest_path = evidence_manifest_path
        self.evidence_dir = evidence_dir
        self.activity_path = activity_path
        self.evidence_manifest: Dict[str, EvidenceItem] = {}
        self.activities: List[ActivityItem] = []
        self._load_manifest()
        self._load_activities()

    def _load_manifest(self) -> None:
        if not os.path.exists(self.evidence_manifest_path):
            return

        with open(self.evidence_manifest_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                e_id = row.get("evidence_id") or row.get("file_id", "").strip()
                f_path = row.get("file_path", "").strip()
                sys_id = row.get("system_id", "").strip()
                res_id = row.get("resource_id", "").strip()
                f_type = row.get("file_type", "").strip()
                created_at = parse_timestamp(row.get("created_at", ""))

                if e_id:
                    self.evidence_manifest[e_id] = EvidenceItem(
                        evidence_id=e_id,
                        file_path=f_path,
                        system_id=sys_id,
                        resource_id=res_id,
                        file_type=f_type,
                        created_at=created_at,
                    )

    def _load_activities(self) -> None:
        if not os.path.exists(self.activity_path):
            return

        with open(self.activity_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                act_id = row.get("activity_id", "").strip()
                ts = parse_timestamp(
                    row.get("timestamp") or row.get("created_at", "")
                )
                sys_id = row.get("system_id", "").strip()
                res_id = row.get("resource_id", "").strip()
                act_type = (
                    row.get("activity_type") or row.get("operation", "")
                ).strip()
                status = row.get("status", "").strip().upper()
                uid = row.get("user_id", "").strip()
                details = row.get("details", "").strip()

                self.activities.append(
                    ActivityItem(
                        activity_id=act_id,
                        timestamp=ts,
                        system_id=sys_id,
                        resource_id=res_id,
                        activity_type=act_type,
                        status=status,
                        user_id=uid,
                        details=details,
                    )
                )

    def check_active_flows_and_restores(
        self, profile: UserProfile, audit_at: datetime
    ) -> List[Tuple[str, str, str, str, str]]:
        """Identify active synchronization or restore flows that risk recreating deleted data.

        Returns list of (phase_op, system_id, resource_id, evidence_id, target_state)
        """
        risks: List[Tuple[str, str, str, str, str]] = []
        user_tokens = (
            {profile.user_id}
            | profile.emails
            | profile.phones
            | profile.email_hashes
        )

        for act in self.activities:
            if act.timestamp and act.timestamp > audit_at:
                continue

            matches_user = False
            if act.user_id and act.user_id in user_tokens:
                matches_user = True
            elif any(token in act.details for token in user_tokens if token):
                matches_user = True

            if not matches_user:
                continue

            act_type_upper = act.activity_type.upper()
            if any(
                w in act_type_upper
                for w in ("SYNC", "REPLICATION", "EXPORT", "INDEX")
            ):
                if act.status in ("ACTIVE", "RUNNING", "PENDING", "IN_PROGRESS"):
                    risks.append(
                        (
                            "REPORT_ACTIVE_DATA_FLOW",
                            act.system_id,
                            act.resource_id or act.system_id,
                            act.activity_id,
                            "ACTIVE",
                        )
                    )

            if any(
                w in act_type_upper for w in ("RESTORE", "BACKUP_RESTORE", "RECOVERY")
            ):
                if act.status in ("ACTIVE", "RUNNING", "SCHEDULED", "PENDING"):
                    risks.append(
                        (
                            "REPORT_RESTORE_RISK",
                            act.system_id,
                            act.resource_id or act.system_id,
                            act.activity_id,
                            "ACTIVE",
                        )
                    )

        return risks

    def inspect_file_evidence(
        self, profile: UserProfile, audit_at: datetime
    ) -> List[Dict[str, Any]]:
        """Inspect multi-modal evidence files created at or before audit_at for remaining PII/records."""
        findings: List[Dict[str, Any]] = []
        user_tokens = (
            {profile.user_id}
            | profile.emails
            | profile.phones
            | profile.email_hashes
        )
        direct_pii_tokens = (
            profile.emails | profile.phones | profile.names | profile.email_hashes
        )

        for e_id, item in self.evidence_manifest.items():
            if item.created_at and item.created_at > audit_at:
                continue

            full_path = (
                item.file_path
                if os.path.isabs(item.file_path)
                else os.path.join(self.evidence_dir, item.file_path)
            )

            if not os.path.exists(full_path):
                continue

            # 1. Parse JSON files
            if item.file_path.endswith(".json"):
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        raw_str = json.dumps(data)
                        found_tokens = [t for t in user_tokens if t and t in raw_str]
                        if found_tokens:
                            has_direct_pii = any(
                                p for p in direct_pii_tokens if p and p in raw_str
                            )
                            findings.append(
                                {
                                    "evidence_id": e_id,
                                    "system_id": item.system_id,
                                    "resource_id": item.resource_id
                                    or item.system_id,
                                    "has_record": True,
                                    "has_exposed_pii": has_direct_pii,
                                    "is_tombstone": (
                                        profile.user_id in raw_str
                                        and not has_direct_pii
                                    ),
                                }
                            )
                except Exception:
                    pass

            # 2. Parse SQLite database files or SQL dump exports
            elif item.file_path.endswith((".db", ".sqlite", ".sql")):
                try:
                    if item.file_path.endswith(".sql"):
                        with open(
                            full_path, "r", encoding="utf-8", errors="ignore"
                        ) as f:
                            sql_text = f.read()
                        found_tokens = [
                            t for t in user_tokens if t and t in sql_text
                        ]
                        if found_tokens:
                            has_direct_pii = any(
                                p
                                for p in direct_pii_tokens
                                if p and p in sql_text
                            )
                            findings.append(
                                {
                                    "evidence_id": e_id,
                                    "system_id": item.system_id,
                                    "resource_id": item.resource_id
                                    or item.system_id,
                                    "has_record": True,
                                    "has_exposed_pii": has_direct_pii,
                                    "is_tombstone": (
                                        profile.user_id in sql_text
                                        and not has_direct_pii
                                    ),
                                }
                            )
                    else:
                        conn = sqlite3.connect(full_path)
                        cursor = conn.cursor()
                        cursor.execute(
                            "SELECT name FROM sqlite_master WHERE type='table';"
                        )
                        tables = cursor.fetchall()
                        matched_in_db = False
                        direct_pii_in_db = False

                        for (t_name,) in tables:
                            cursor.execute(f"PRAGMA table_info({t_name});")
                            cols = [c[1] for c in cursor.fetchall()]
                            cursor.execute(f"SELECT * FROM {t_name}")
                            rows = cursor.fetchall()
                            for r in rows:
                                row_str = " ".join(str(val) for val in r)
                                if any(t for t in user_tokens if t and t in row_str):
                                    matched_in_db = True
                                    if any(
                                        p
                                        for p in direct_pii_tokens
                                        if p and p in row_str
                                    ):
                                        direct_pii_in_db = True
                                        break
                            if direct_pii_in_db:
                                break
                        conn.close()

                        if matched_in_db:
                            findings.append(
                                {
                                    "evidence_id": e_id,
                                    "system_id": item.system_id,
                                    "resource_id": item.resource_id
                                    or item.system_id,
                                    "has_record": True,
                                    "has_exposed_pii": direct_pii_in_db,
                                    "is_tombstone": not direct_pii_in_db,
                                }
                            )
                except Exception:
                    pass

            # 3. Plain text / logs / Markdown
            else:
                try:
                    with open(
                        full_path, "r", encoding="utf-8", errors="ignore"
                    ) as f:
                        text = f.read()
                        if any(t for t in user_tokens if t and t in text):
                            has_direct_pii = any(
                                p for p in direct_pii_tokens if p and p in text
                            )
                            findings.append(
                                {
                                    "evidence_id": e_id,
                                    "system_id": item.system_id,
                                    "resource_id": item.resource_id
                                    or item.system_id,
                                    "has_record": True,
                                    "has_exposed_pii": has_direct_pii,
                                    "is_tombstone": not has_direct_pii,
                                }
                            )
                except Exception:
                    pass

        return findings
