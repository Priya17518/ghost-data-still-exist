"""Main Execution Runner for Deletion Audit Agent."""

from __future__ import annotations

import csv
import os
import sys
from agent import DeletionAuditAgent
from evidence_parser import EvidenceParser
from identity_resolver import IdentityResolver
from policy_engine import PolicyEngine


def main() -> None:
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dataset_dir = os.path.join(repo_root, "dataset")

    requests_file = os.path.join(dataset_dir, "deletion_requests.csv")
    identities_file = os.path.join(dataset_dir, "user_identities.csv")
    audit_log_file = os.path.join(dataset_dir, "user_audit_log.csv")
    evidence_manifest_file = os.path.join(dataset_dir, "evidence_files.csv")
    evidence_dir = os.path.join(dataset_dir, "evidence")
    activity_file = os.path.join(dataset_dir, "system_activity.csv")
    deletion_rules_file = os.path.join(dataset_dir, "deletion_rules.csv")
    output_file = os.path.join(repo_root, "output.csv")

    if not os.path.exists(requests_file):
        print(f"Error: requests file not found at {requests_file}")
        sys.exit(1)

    print("Initializing Identity Resolver...")
    resolver = IdentityResolver(identities_file, audit_log_file)

    print("Initializing Corpus & Evidence Parser...")
    evidence_parser = EvidenceParser(
        evidence_manifest_file, evidence_dir, activity_file
    )

    print("Initializing Policy Engine...")
    policy_engine = PolicyEngine(deletion_rules_file)

    print("Initializing Deletion Audit Agent...")
    agent = DeletionAuditAgent(resolver, evidence_parser, policy_engine)

    # Ingest deletion requests
    cases = []
    with open(requests_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cases.append(row)

    print(f"Processing {len(cases)} deletion requests...")
    results = []
    for c in cases:
        status, steps_json = agent.evaluate_case(c)
        results.append(
            {
                "case_id": c["case_id"].strip(),
                "deletion_status": status,
                "steps_json": steps_json,
            }
        )

    # Sort strictly ascending by case_id
    results.sort(key=lambda r: r["case_id"])

    # Write output.csv with exact standard CSV escaping
    print(f"Writing {len(results)} rows to {output_file}...")
    with open(output_file, "w", encoding="utf-8", newline="") as f:
        fieldnames = ["case_id", "deletion_status", "steps_json"]
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for r in results:
            writer.writerow(r)

    print("Completed successfully.")


if __name__ == "__main__":
    main()
