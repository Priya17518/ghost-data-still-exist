"""Output Verifier.

Validates that output.csv contains exactly 518 rows, is sorted by case_id,
and adheres to the required schema and constraints.
"""

from __future__ import annotations

import csv
import json
import os
import sys

REQUIRED_HEADERS = ["case_id", "deletion_status", "steps_json"]
VALID_STATUSES = {"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"}
EXPECTED_ROW_COUNT = 518


def verify_output(output_csv_path: str) -> bool:
    if not os.path.exists(output_csv_path):
        print(f"[ERROR] {output_csv_path} does not exist.")
        return False

    with open(output_csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != REQUIRED_HEADERS:
            print(f"[ERROR] Invalid CSV headers: got {reader.fieldnames}, expected {REQUIRED_HEADERS}")
            return False

        rows = list(reader)

    row_count = len(rows)
    print(f"Total rows found in output.csv: {row_count} (Expected: {EXPECTED_ROW_COUNT})")
    if row_count != EXPECTED_ROW_COUNT:
        print(f"[ERROR] Row count mismatch! Expected {EXPECTED_ROW_COUNT}, got {row_count}")
        return False

    previous_case_id = ""
    for idx, r in enumerate(rows, start=1):
        cid = r.get("case_id", "")
        status = r.get("deletion_status", "")
        steps_raw = r.get("steps_json", "")

        # 1. Check case_id ascending order
        if cid <= previous_case_id:
            print(f"[ERROR] Row {idx}: case_id '{cid}' is not strictly greater than previous '{previous_case_id}' (Sorting failure).")
            return False
        previous_case_id = cid

        # 2. Check deletion status enum
        if status not in VALID_STATUSES:
            print(f"[ERROR] Row {idx} ({cid}): invalid deletion_status '{status}'.")
            return False

        # 3. Check JSON validity
        try:
            steps = json.loads(steps_raw)
            if not isinstance(steps, list):
                print(f"[ERROR] Row {idx} ({cid}): steps_json is not a valid list.")
                return False
        except Exception as e:
            print(f"[ERROR] Row {idx} ({cid}): JSON parse failure: {e}")
            return False

        # 4. Check NOT_APPLICABLE empty array requirement
        if status == "NOT_APPLICABLE" and len(steps) != 0:
            print(f"[ERROR] Row {idx} ({cid}): NOT_APPLICABLE must have an empty JSON array '[]'.")
            return False

    print("[SUCCESS] All 518 rows verified: correct schema, sorted case_id, valid status, and compliant JSON.")
    return True


if __name__ == "__main__":
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_csv = os.path.join(repo_root, "output.csv")
    ok = verify_output(target_csv)
    sys.exit(0 if ok else 1)
