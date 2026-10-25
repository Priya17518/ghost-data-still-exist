"""Benchmark Dataset Synthesizer for Ghost Data Still Exists Challenge.

Generates exactly 518 realistic test cases across various distributed systems,
active replication flows, multi-modal storage evidence, and multilingual requests.
"""

import csv
import hashlib
import json
import os
import random
import sqlite3
from datetime import datetime, timedelta

random.seed(42)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_DIR = os.path.join(REPO_ROOT, "dataset")
EVIDENCE_DIR = os.path.join(DATASET_DIR, "evidence")
os.makedirs(EVIDENCE_DIR, exist_ok=True)

# 1. deletion_rules.csv
rules_data = [
    {
        "data_category": "primary_profile",
        "system_id": "postgres_primary",
        "required_treatment": "ABSENT",
        "permitted_fields": "",
        "prohibited_fields": "email,name,phone,address",
    },
    {
        "data_category": "tombstone_account",
        "system_id": "account_service",
        "required_treatment": "RETAIN_TOMBSTONE",
        "permitted_fields": "user_id,created_at,account_status",
        "prohibited_fields": "email,name,phone,email_hash",
    },
    {
        "data_category": "support_tickets",
        "system_id": "zendesk_support",
        "required_treatment": "REDACTED",
        "permitted_fields": "ticket_id,category,resolution_code",
        "prohibited_fields": "email,phone,name,body_pii",
    },
    {
        "data_category": "clickstream_analytics",
        "system_id": "analytics_warehouse",
        "required_treatment": "ANONYMIZED",
        "permitted_fields": "event_type,session_duration,device_type",
        "prohibited_fields": "user_id,ip_address,email_hash",
    },
    {
        "data_category": "search_catalog",
        "system_id": "elasticsearch_cluster",
        "required_treatment": "ABSENT",
        "permitted_fields": "",
        "prohibited_fields": "user_id,name,email,bio",
    },
    {
        "data_category": "cold_archives",
        "system_id": "backup_s3_glacier",
        "required_treatment": "ABSENT",
        "permitted_fields": "",
        "prohibited_fields": "all_pii",
    },
]

with open(os.path.join(DATASET_DIR, "deletion_rules.csv"), "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["data_category", "system_id", "required_treatment", "permitted_fields", "prohibited_fields"])
    writer.writeheader()
    writer.writerows(rules_data)

# Names, domains, words
FIRST_NAMES = ["Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Sam", "Chris", "Pat", "Robin", "Dana", "Kim", "Avery", "Cameron", "Jesse", "Dakota", "Jamie", "Skyler", "Peyton", "Logan", "Elena", "Marcus", "Kavita", "Liam", "Mei", "Hiroshi", "Chloe", "Mateo", "Fatima", "Lars"]
LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson"]
DOMAINS = ["example.com", "corpmail.io", "techvault.net", "privacyfirst.org", "inboxpulse.co", "datashield.dev", "apexcloud.internal"]

DELETION_TEXTS = [
    "Please delete my account and permanently erase all my personal data pursuant to GDPR Article 17.",
    "I want to exercise my Right to be Forgotten. Please remove all records associated with my profile.",
    "Please close and terminate my account, purging all stored logs, records, and search entries.",
    "Kindly erase my personal information, delete my user profile, and wipe all database traces.",
    "Please destroy all data tied to this email and terminate my active membership immediately.",
    "Veuillez supprimer définitivement mon compte et toutes mes données personnelles.",
    "Bitte löschen Sie alle meine personenbezogenen Daten und schließen Sie mein Benutzerkonto gemäß DSGVO.",
    "Por favor, elimine permanentemente todos mis datos personales y cierre mi cuenta.",
    "Si prega di cancellare tutti i miei dati personali ed eliminare il mio profilo utente.",
]

NON_DELETION_TEXTS = [
    "Please export all my data and download my account history so I can review it.",
    "Can you provide a full copy of my user records for data portability?",
    "I need to update my email address and change my contact phone number.",
    "Please unsubscribe me from marketing emails and newsletter updates.",
    "I have a status inquiry regarding my previous support ticket, can someone help?",
    "Please rectify my billing address and update my legal full name in your files.",
]

requests_rows = []
identities_rows = []
audit_log_rows = []
activity_rows = []
evidence_manifest_rows = []

base_time = datetime(2026, 4, 1, 10, 0, 0)

# Create 518 cases strictly:
# Case distribution:
# ~25% NOT_APPLICABLE (non-deletion)
# ~35% COMPLETE
# ~40% INCOMPLETE (residual file, exposed PII, active sync, or restore risk)

total_cases = 518

for i in range(1, total_cases + 1):
    case_num = f"{i:04d}"
    case_id = f"CASE-{case_num}"
    fn = random.choice(FIRST_NAMES)
    ln = random.choice(LAST_NAMES)
    dom = random.choice(DOMAINS)
    email = f"{fn.lower()}.{ln.lower()}{random.randint(10, 999)}@{dom}"
    user_id = f"usr_{hashlib.md5(email.encode()).hexdigest()[:12]}"
    phone = f"+1-{random.randint(200, 999)}-555-{random.randint(1000, 9999)}"
    email_hash = hashlib.sha256(email.lower().encode()).hexdigest()

    audit_at = base_time + timedelta(hours=i * 2, minutes=random.randint(0, 50))
    audit_at_str = audit_at.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Determine intent category
    cat_roll = (i % 10)
    if cat_roll in (0, 7):
        # NOT_APPLICABLE
        req_type = "NOT_APPLICABLE"
        req_text = random.choice(NON_DELETION_TEXTS)
    elif cat_roll in (1, 4, 8):
        # COMPLETE
        req_type = "COMPLETE"
        req_text = random.choice(DELETION_TEXTS)
    else:
        # INCOMPLETE
        req_type = "INCOMPLETE"
        req_text = random.choice(DELETION_TEXTS)

    requests_rows.append({
        "case_id": case_id,
        "email": email,
        "request_text": req_text,
        "audit_at": audit_at_str,
    })

    # Record identity
    identities_rows.append({
        "user_id": user_id,
        "name": f"{fn} {ln}",
        "email": email,
        "phone": phone,
        "email_hash": email_hash,
        "updated_at": (audit_at - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })

    # Add historical alias in audit log for ~30% of users
    if i % 3 == 0:
        old_email = f"old_{email}"
        audit_log_rows.append({
            "log_id": f"aud_{i:04d}_01",
            "user_id": user_id,
            "field_name": "email",
            "old_value": old_email,
            "new_value": email,
            "timestamp": (audit_at - timedelta(days=45)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })

    # Now create evidence and activities
    if req_type == "COMPLETE":
        # Compliant tombstone in account_service or redacted support ticket
        ev_id = f"ev_{case_num}_01"
        fname = f"account_tombstone_{case_num}.json"
        fpath = os.path.join(EVIDENCE_DIR, fname)
        # Compliant tombstone has user_id but NO email, phone, name, or email_hash
        with open(fpath, "w", encoding="utf-8") as ef:
            json.dump({
                "account_id": user_id,
                "account_status": "DELETED",
                "tombstone_timestamp": (audit_at - timedelta(days=5)).isoformat(),
            }, ef)

        evidence_manifest_rows.append({
            "evidence_id": ev_id,
            "file_path": fname,
            "system_id": "account_service",
            "resource_id": f"account_tombstone_{user_id}",
            "file_type": "json",
            "created_at": (audit_at - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })

    elif req_type == "INCOMPLETE":
        # Give it specific violation(s)
        sub_type = (i % 4)

        if sub_type == 0:
            # Residual record in elasticsearch
            ev_id = f"ev_{case_num}_es"
            fname = f"es_doc_{case_num}.json"
            fpath = os.path.join(EVIDENCE_DIR, fname)
            with open(fpath, "w", encoding="utf-8") as ef:
                json.dump({
                    "doc_id": f"search_{user_id}",
                    "user_id": user_id,
                    "profile_name": f"{fn} {ln}",
                    "search_terms": ["engineer", "compliance"],
                }, ef)

            evidence_manifest_rows.append({
                "evidence_id": ev_id,
                "file_path": fname,
                "system_id": "elasticsearch_cluster",
                "resource_id": f"search_index_{user_id}",
                "file_type": "json",
                "created_at": (audit_at - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            })

        elif sub_type == 1:
            # Exposed PII in zendesk_support
            ev_id = f"ev_{case_num}_zd"
            fname = f"support_ticket_{case_num}.json"
            fpath = os.path.join(EVIDENCE_DIR, fname)
            with open(fpath, "w", encoding="utf-8") as ef:
                json.dump({
                    "ticket_id": f"tkt_{case_num}",
                    "user_id": user_id,
                    "customer_email": email,
                    "phone": phone,
                    "body": "User requested support previously.",
                }, ef)

            evidence_manifest_rows.append({
                "evidence_id": ev_id,
                "file_path": fname,
                "system_id": "zendesk_support",
                "resource_id": f"ticket_{case_num}",
                "file_type": "json",
                "created_at": (audit_at - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            })

        elif sub_type == 2:
            # Active synchronization flow in system_activity
            act_id = f"act_{case_num}_sync"
            activity_rows.append({
                "activity_id": act_id,
                "timestamp": (audit_at - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "system_id": "kafka_stream_sync",
                "resource_id": f"user_events_stream_{user_id}",
                "activity_type": "REPLICATION_SYNC",
                "status": "ACTIVE",
                "user_id": user_id,
                "details": f"Streaming sync job active for {email}",
            })

        elif sub_type == 3:
            # Active restore risk in system_activity
            act_id = f"act_{case_num}_restore"
            activity_rows.append({
                "activity_id": act_id,
                "timestamp": (audit_at - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "system_id": "backup_s3_glacier",
                "resource_id": f"restore_snapshot_{user_id}",
                "activity_type": "BACKUP_RESTORE",
                "status": "ACTIVE",
                "user_id": user_id,
                "details": f"Cold restore job pending recovery for {email}",
            })

# Write deletion_requests.csv
with open(os.path.join(DATASET_DIR, "deletion_requests.csv"), "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["case_id", "email", "request_text", "audit_at"])
    writer.writeheader()
    writer.writerows(requests_rows)

# Write user_identities.csv
with open(os.path.join(DATASET_DIR, "user_identities.csv"), "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["user_id", "name", "email", "phone", "email_hash", "updated_at"])
    writer.writeheader()
    writer.writerows(identities_rows)

# Write user_audit_log.csv
with open(os.path.join(DATASET_DIR, "user_audit_log.csv"), "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["log_id", "user_id", "field_name", "old_value", "new_value", "timestamp"])
    writer.writeheader()
    writer.writerows(audit_log_rows)

# Write system_activity.csv
with open(os.path.join(DATASET_DIR, "system_activity.csv"), "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["activity_id", "timestamp", "system_id", "resource_id", "activity_type", "status", "user_id", "details"])
    writer.writeheader()
    writer.writerows(activity_rows)

# Write evidence_files.csv
with open(os.path.join(DATASET_DIR, "evidence_files.csv"), "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["evidence_id", "file_path", "system_id", "resource_id", "file_type", "created_at"])
    writer.writeheader()
    writer.writerows(evidence_manifest_rows)

# Write sample_deletion_requests.csv (take first 10 rows)
sample_rows = requests_rows[:10]
with open(os.path.join(DATASET_DIR, "sample_deletion_requests.csv"), "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["case_id", "email", "request_text", "audit_at"])
    writer.writeheader()
    writer.writerows(sample_rows)

print(f"Generated benchmark dataset with {len(requests_rows)} cases in {DATASET_DIR}")
