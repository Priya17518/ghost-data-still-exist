"""Sample Validation & Schema Invariant Verifier.

Runs the DeletionAuditAgent against sample data and verifies that generated output
strictly adheres to challenge sorting, phase ordering, and schema rules.
"""

from __future__ import annotations

import csv
import json
import os
import sys
from typing import Any, Dict, List

from agent import DeletionAuditAgent
from evidence_parser import EvidenceParser
from identity_resolver import IdentityResolver
from policy_engine import PolicyEngine

FINDING_OPS = [
    "REPORT_REMAINING_RECORD",
    "REPORT_EXPOSED_PII",
    "REPORT_ACTIVE_DATA_FLOW",
    "REPORT_RESTORE_RISK",
]
REMEDIATION_OPS = [
    "DISABLE_DATA_FLOW",
    "BLOCK_RESTORE",
    "DELETE_RECORD",
    "REDACT_RECORD",
    "ANONYMIZE_RECORD",
]
VERIFICATION_OPS = [
    "VERIFY_RECORD_ABSENT",
    "VERIFY_RECORD_PRESENT",
    "VERIFY_RECORD_REDACTED",
    "VERIFY_RECORD_ANONYMIZED",
    "VERIFY_DATA_FLOW_DISABLED",
    "VERIFY_RESTORE_BLOCKED",
]

PHASE_ORDER = {"FINDING": 0, "REMEDIATION": 1, "VERIFICATION": 2}
FINDING_ORDER = {op: idx for idx, op in enumerate(FINDING_OPS)}
REMEDIATION_ORDER = {op: idx for idx, op in enumerate(REMEDIATION_OPS)}
VERIFICATION_ORDER = {op: idx for idx, op in enumerate(VERIFICATION_OPS)}


def validate_steps_json_invariants(case_id: str, status: str, steps: List[Dict[str, Any]]) -> List[str]:
    """Strictly assert challenge rules on the steps array."""
    errors = []

    if status == "NOT_APPLICABLE":
        if len(steps) != 0:
            errors.append(f"[{case_id}] NOT_APPLICABLE must have an empty steps_json '[]', found {len(steps)} items.")
        return errors

    if status == "COMPLETE":
        for s in steps:
            if s.get("phase") != "VERIFICATION":
                errors.append(f"[{case_id}] COMPLETE case step {s.get('step_no')} has phase '{s.get('phase')}', expected 'VERIFICATION'.")
            if not s.get("evidence_id"):
                errors.append(f"[{case_id}] COMPLETE case verification step {s.get('step_no')} must cite a valid evidence_id.")
        return errors

    # Status is INCOMPLETE
    current_phase_rank = -1
    current_op_rank = -1
    current_sort_key = ""

    for idx, s in enumerate(steps, start=1):
        if s.get("step_no") != idx:
            errors.append(f"[{case_id}] step_no out of sequence: got {s.get('step_no')}, expected {idx}.")

        phase = s.get("phase")
        op = s.get("operation")
        sys_id = s.get("system_id", "")
        res_id = s.get("resource_id", "")
        evid = s.get("evidence_id")

        if phase not in PHASE_ORDER:
            errors.append(f"[{case_id}] Invalid phase '{phase}' in step {idx}.")
            continue

        phase_rank = PHASE_ORDER[phase]
        if phase_rank < current_phase_rank:
            errors.append(f"[{case_id}] Phase order violation at step {idx}: saw {phase} after higher phase.")
        elif phase_rank > current_phase_rank:
            current_phase_rank = phase_rank
            current_op_rank = -1
            current_sort_key = ""

        # Check operation precedence within phase
        op_rank = 0
        if phase == "FINDING":
            op_rank = FINDING_ORDER.get(op, 999)
            if not evid:
                errors.append(f"[{case_id}] FINDING step {idx} must cite an evidence_id.")
        elif phase == "REMEDIATION":
            op_rank = REMEDIATION_ORDER.get(op, 999)
            if evid != "":
                errors.append(f"[{case_id}] REMEDIATION step {idx} must have empty evidence_id, got '{evid}'.")
        elif phase == "VERIFICATION":
            op_rank = VERIFICATION_ORDER.get(op, 999)
            if evid != "":
                errors.append(f"[{case_id}] Post-remediation VERIFICATION step {idx} must have empty evidence_id, got '{evid}'.")

        sort_key = f"{sys_id}:{res_id}"
        if op_rank < current_op_rank:
            errors.append(f"[{case_id}] Operation hierarchy violation in phase {phase} at step {idx}: {op}.")
        elif op_rank == current_op_rank:
            if sort_key < current_sort_key:
                errors.append(f"[{case_id}] Alphabetical sorting violation at step {idx}: '{sort_key}' < '{current_sort_key}'.")
            current_sort_key = sort_key
        else:
            current_op_rank = op_rank
            current_sort_key = sort_key

    return errors


def run_sample_validation(repo_root: str) -> bool:
    dataset_dir = os.path.join(repo_root, "dataset")
    sample_req_path = os.path.join(dataset_dir, "sample_deletion_requests.csv")
    sample_out_path = os.path.join(dataset_dir, "sample_output.csv")

    if not os.path.exists(sample_req_path):
        print(f"[!] sample_deletion_requests.csv not found at {sample_req_path}")
        return False

    resolver = IdentityResolver(
        os.path.join(dataset_dir, "user_identities.csv"),
        os.path.join(dataset_dir, "user_audit_log.csv"),
    )
    evidence_parser = EvidenceParser(
        os.path.join(dataset_dir, "evidence_files.csv"),
        os.path.join(dataset_dir, "evidence"),
        os.path.join(dataset_dir, "system_activity.csv"),
    )
    policy_engine = PolicyEngine(os.path.join(dataset_dir, "deletion_rules.csv"))
    agent = DeletionAuditAgent(resolver, evidence_parser, policy_engine)

    # Ingest expected ground truth if present
    expected_records = {}
    if os.path.exists(sample_out_path):
        with open(sample_out_path, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                expected_records[row["case_id"]] = row

    all_passed = True
    total_evaluated = 0

    with open(sample_req_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_evaluated += 1
            cid = row["case_id"]
            status, steps_str = agent.evaluate_case(row)
            steps = json.loads(steps_str)

            # Invariant check
            errs = validate_steps_json_invariants(cid, status, steps)
            if errs:
                all_passed = False
                for e in errs:
                    print(f"  [FAIL INVARIANT] {e}")

            # Ground truth sample regression check
            if cid in expected_records:
                exp_status = expected_records[cid]["deletion_status"]
                if status != exp_status:
                    all_passed = False
                    print(f"  [STATUS MISMATCH] Case {cid}: got '{status}', expected '{exp_status}'")

    print(f"Sample Validation Finished. Evaluated: {total_evaluated} cases. All invariants valid: {all_passed}")
    return all_passed


if __name__ == "__main__":
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    success = run_sample_validation(repo)
    sys.exit(0 if success else 1)
