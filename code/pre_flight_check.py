"""Automated Pre-Flight Checklist Validator for Final Submission."""

from __future__ import annotations

import csv
import json
import os
import sys

REQUIRED_CSV_HEADERS = ["case_id", "deletion_status", "steps_json"]
VALID_STATUSES = {"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"}
EXPECTED_ROW_COUNT = 518

PHASE_ORDER = {"FINDING": 0, "REMEDIATION": 1, "VERIFICATION": 2}
FINDING_ORDER = {
    "REPORT_REMAINING_RECORD": 0,
    "REPORT_EXPOSED_PII": 1,
    "REPORT_ACTIVE_DATA_FLOW": 2,
    "REPORT_RESTORE_RISK": 3,
}
REMEDIATION_ORDER = {
    "DISABLE_DATA_FLOW": 0,
    "BLOCK_RESTORE": 1,
    "DELETE_RECORD": 2,
    "REDACT_RECORD": 3,
    "ANONYMIZE_RECORD": 4,
}
VERIFICATION_ORDER = {
    "VERIFY_RECORD_ABSENT": 0,
    "VERIFY_RECORD_PRESENT": 1,
    "VERIFY_RECORD_REDACTED": 2,
    "VERIFY_RECORD_ANONYMIZED": 3,
    "VERIFY_DATA_FLOW_DISABLED": 4,
    "VERIFY_RESTORE_BLOCKED": 5,
}


def run_preflight_checks() -> bool:
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_path = os.path.join(repo_root, "output.csv")
    
    # Reports may be in root or inside code/
    eval_rep_paths = [
        os.path.join(repo_root, "evaluation", "evaluation_report.md"),
        os.path.join(repo_root, "code", "evaluation", "evaluation_report.md"),
    ]
    usage_rep_paths = [
        os.path.join(repo_root, "evaluation", "usage_report.md"),
        os.path.join(repo_root, "code", "evaluation", "usage_report.md"),
    ]
    log_path = os.path.join(repo_root, "log.txt")

    print("=" * 60)
    print("RUNNING FINAL PRE-SUBMISSION VERIFICATION CHECKS")
    print("=" * 60)

    all_passed = True

    # 1. Verify output.csv exists at root
    if not os.path.exists(output_path):
        print(f"[FAIL] output.csv not found at root path: {output_path}")
        return False
    print("[PASS] output.csv found at repo root.")

    # 2. Inspect output.csv schema, sorting, and row count
    with open(output_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != REQUIRED_CSV_HEADERS:
            print(f"[FAIL] Invalid headers: got {reader.fieldnames}, expected {REQUIRED_CSV_HEADERS}")
            all_passed = False
        else:
            print(f"[PASS] CSV schema matches exactly: {REQUIRED_CSV_HEADERS}")

        rows = list(reader)

    if len(rows) != EXPECTED_ROW_COUNT:
        print(f"[FAIL] Row count mismatch: found {len(rows)}, expected {EXPECTED_ROW_COUNT}")
        all_passed = False
    else:
        print(f"[PASS] Row count matches exactly: {EXPECTED_ROW_COUNT} data rows.")

    last_case_id = ""
    for idx, r in enumerate(rows, start=1):
        cid = r.get("case_id", "")
        status = r.get("deletion_status", "")
        steps_str = r.get("steps_json", "")

        # Ascending sort check
        if cid <= last_case_id:
            print(f"[FAIL] Row {idx}: case_id '{cid}' is not strictly ascending after '{last_case_id}'.")
            all_passed = False
        last_case_id = cid

        # Status validity
        if status not in VALID_STATUSES:
            print(f"[FAIL] Row {idx} ({cid}): invalid status '{status}'.")
            all_passed = False

        # JSON parsing & invariant validation
        try:
            steps = json.loads(steps_str)
        except Exception as e:
            print(f"[FAIL] Row {idx} ({cid}): malformed JSON: {e}")
            all_passed = False
            continue

        if status == "NOT_APPLICABLE":
            if len(steps) != 0:
                print(f"[FAIL] Row {idx} ({cid}): NOT_APPLICABLE must have steps_json '[]', got {len(steps)} items.")
                all_passed = False
        elif status == "COMPLETE":
            for s in steps:
                if s.get("phase") != "VERIFICATION":
                    print(f"[FAIL] Row {idx} ({cid}): COMPLETE case has non-VERIFICATION step: {s}")
                    all_passed = False
                if not s.get("evidence_id"):
                    print(f"[FAIL] Row {idx} ({cid}): COMPLETE verification step missing evidence_id: {s}")
                    all_passed = False
        elif status == "INCOMPLETE":
            cur_phase_rank = -1
            cur_op_rank = -1
            cur_sort_key = ""
            for s_idx, s in enumerate(steps, start=1):
                phase = s.get("phase")
                op = s.get("operation")
                evid = s.get("evidence_id")
                sys_id = s.get("system_id", "")
                res_id = s.get("resource_id", "")
                sort_key = f"{sys_id}:{res_id}"

                phase_rank = PHASE_ORDER.get(phase, 99)
                if phase_rank < cur_phase_rank:
                    print(f"[FAIL] Row {idx} ({cid}) step {s_idx}: Phase sequence inverted ({phase}).")
                    all_passed = False
                elif phase_rank > cur_phase_rank:
                    cur_phase_rank = phase_rank
                    cur_op_rank = -1
                    cur_sort_key = ""

                # Hierarchy check
                if phase == "FINDING":
                    op_rank = FINDING_ORDER.get(op, 99)
                    if not evid:
                        print(f"[FAIL] Row {idx} ({cid}) step {s_idx}: FINDING step requires non-empty evidence_id.")
                        all_passed = False
                elif phase == "REMEDIATION":
                    op_rank = REMEDIATION_ORDER.get(op, 99)
                    if evid != "":
                        print(f"[FAIL] Row {idx} ({cid}) step {s_idx}: REMEDIATION step requires evidence_id ''.")
                        all_passed = False
                elif phase == "VERIFICATION":
                    op_rank = VERIFICATION_ORDER.get(op, 99)
                    if evid != "":
                        print(f"[FAIL] Row {idx} ({cid}) step {s_idx}: INCOMPLETE VERIFICATION step requires evidence_id ''.")
                        all_passed = False

                if op_rank < cur_op_rank:
                    print(f"[FAIL] Row {idx} ({cid}) step {s_idx}: Operational precedence violated for '{op}'.")
                    all_passed = False
                elif op_rank == cur_op_rank:
                    if sort_key < cur_sort_key:
                        print(f"[FAIL] Row {idx} ({cid}) step {s_idx}: Tie-breaker sort violated ('{sort_key}' < '{cur_sort_key}').")
                        all_passed = False
                    cur_sort_key = sort_key
                else:
                    cur_op_rank = op_rank
                    cur_sort_key = sort_key

    # 3. Check documentation and logs
    eval_ok = any(os.path.exists(p) and os.path.getsize(p) > 0 for p in eval_rep_paths)
    if not eval_ok:
        print("[FAIL] evaluation_report.md missing or empty in evaluation/ or code/evaluation/.")
        all_passed = False
    else:
        print("[PASS] Verified presence of evaluation_report.md.")

    usage_ok = any(os.path.exists(p) and os.path.getsize(p) > 0 for p in usage_rep_paths)
    if not usage_ok:
        print("[FAIL] usage_report.md missing or empty in evaluation/ or code/evaluation/.")
        all_passed = False
    else:
        print("[PASS] Verified presence of usage_report.md.")

    if not os.path.exists(log_path) or os.path.getsize(log_path) == 0:
        print(f"[FAIL] Required file missing or empty: {log_path}")
        all_passed = False
    else:
        print("[PASS] Verified presence of log.txt.")

    print("=" * 60)
    if all_passed:
        print("[SUCCESS] ALL PRE-FLIGHT VERIFICATION CHECKS PASSED PERFECTLY!")
    else:
        print("[ERROR] ONE OR MORE VERIFICATION CHECKS FAILED. REVIEW LOGS ABOVE.")
    print("=" * 60)

    return all_passed


if __name__ == "__main__":
    success = run_preflight_checks()
    sys.exit(0 if success else 1)
