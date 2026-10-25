"""Export cases to JSON for web interface."""

import csv
import json
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_DIR = os.path.join(REPO_ROOT, "dataset")
OUT_JSON_DIR = os.path.join(REPO_ROOT, "src", "data")
os.makedirs(OUT_JSON_DIR, exist_ok=True)

requests = {}
with open(os.path.join(DATASET_DIR, "deletion_requests.csv"), "r", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        requests[row["case_id"]] = row

identities = {}
with open(os.path.join(DATASET_DIR, "user_identities.csv"), "r", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        identities[row["email"].lower()] = row

audit_logs = {}
with open(os.path.join(DATASET_DIR, "user_audit_log.csv"), "r", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        uid = row["user_id"]
        audit_logs.setdefault(uid, []).append(row)

output_rows = {}
with open(os.path.join(REPO_ROOT, "output.csv"), "r", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        output_rows[row["case_id"]] = row

merged = []
for cid, out_row in sorted(output_rows.items()):
    req = requests.get(cid, {})
    email = req.get("email", "")
    ident = identities.get(email.lower(), {})
    uid = ident.get("user_id", "")
    user_logs = audit_logs.get(uid, [])

    try:
        steps = json.loads(out_row["steps_json"])
    except Exception:
        steps = []

    merged.append({
        "case_id": cid,
        "deletion_status": out_row["deletion_status"],
        "email": email,
        "request_text": req.get("request_text", ""),
        "audit_at": req.get("audit_at", ""),
        "user_id": uid,
        "name": ident.get("name", ""),
        "phone": ident.get("phone", ""),
        "email_hash": ident.get("email_hash", ""),
        "historical_logs": user_logs,
        "steps": steps,
        "step_count": len(steps)
    })

out_path = os.path.join(OUT_JSON_DIR, "audit_cases.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(merged, f, indent=2)

print(f"Exported {len(merged)} cases to {out_path}")
