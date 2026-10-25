"""Deterministic Deletion Audit Agent (Hardened).

Strictly enforces:
1. NOT_APPLICABLE -> steps_json = "[]"
2. 4-Tuple Sorting Key: (phase_order, operation_order, system_id, resource_id)
3. Evidence Citation Invariant:
   - COMPLETE cases: all steps cite non-empty evidence_id
   - INCOMPLETE cases: FINDING cites evidence_id; REMEDIATION and VERIFICATION use ""
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from evidence_parser import EvidenceParser
from identity_resolver import IdentityResolver, UserProfile, parse_timestamp
from policy_engine import PolicyEngine


class DeletionAuditAgent:
    """Enterprise Audit Agent enforcing deterministic deletion policy compliance."""

    # 1. Official Phase Hierarchy Index
    PHASE_ORDER = {
        "FINDING": 0,
        "REMEDIATION": 1,
        "VERIFICATION": 2,
    }

    # 2. Official Operation Hierarchy Indices (Table Order)
    OPERATION_ORDER = {
        # Phase 0: FINDING
        "REPORT_REMAINING_RECORD": 0,
        "REPORT_EXPOSED_PII": 1,
        "REPORT_ACTIVE_DATA_FLOW": 2,
        "REPORT_RESTORE_RISK": 3,
        # Phase 1: REMEDIATION
        "DISABLE_DATA_FLOW": 0,
        "BLOCK_RESTORE": 1,
        "DELETE_RECORD": 2,
        "REDACT_RECORD": 3,
        "ANONYMIZE_RECORD": 4,
        # Phase 2: VERIFICATION
        "VERIFY_RECORD_ABSENT": 0,
        "VERIFY_RECORD_PRESENT": 1,
        "VERIFY_RECORD_REDACTED": 2,
        "VERIFY_RECORD_ANONYMIZED": 3,
        "VERIFY_DATA_FLOW_DISABLED": 4,
        "VERIFY_RESTORE_BLOCKED": 5,
    }

    # Intent Detection Regexes
    NON_DELETION_PATTERNS = [
        r"\b(export|download|view|copy|get|request|portability)\s+(my\s+)?(data|records?|archive|profile)\b",
        r"\b(rectify|rectification|update|change|correct|edit)\s+(my\s+)?(email|phone|name|address)\b",
        r"\b(unsubscribe|opt[- ]?out)\s+from\s+(marketing|emails?|newsletters?)\b",
        r"\b(help|support|question|inquiry|status)\s+regarding\b",
    ]

    DELETION_PATTERNS = [
        r"\b(delete|erasure|erase|purge|remove|forget|destroy)\b",
        r"\b(close|terminate|cancel)\s+(my\s+)?(account|membership|profile)\b",
        r"\bright\s+to\s+be\s+forgotten\b",
        r"\bgdpr\s+art(icle)?\.?\s*17\b",
        r"\b(suprimer|eliminar|löschen|borrar|cancellare)\b",  # Multilingual support
    ]

    def __init__(
        self,
        resolver: IdentityResolver,
        evidence_parser: EvidenceParser,
        policy_engine: PolicyEngine,
    ) -> None:
        self.resolver = resolver
        self.evidence_parser = evidence_parser
        self.policy_engine = policy_engine

    def is_valid_deletion_request(self, request_text: str) -> bool:
        """Verify if the request explicitly authorizes deletion.
        
        If it's an export, rectification, or opt-out without deletion authorization,
        it is considered NOT_APPLICABLE.
        """
        if not request_text or not request_text.strip():
            return False

        text = request_text.lower().strip()

        has_deletion_intent = any(re.search(pat, text, re.IGNORECASE) for pat in self.DELETION_PATTERNS)
        has_non_deletion_intent = any(re.search(pat, text, re.IGNORECASE) for pat in self.NON_DELETION_PATTERNS)

        if has_non_deletion_intent and not has_deletion_intent:
            return False

        return has_deletion_intent

    def _make_sort_key(self, step: Dict[str, Any]) -> Tuple[int, int, str, str]:
        """Construct the official 4-tuple sorting key:
        
        (phase_order, operation_order, system_id, resource_id)
        """
        phase_idx = self.PHASE_ORDER.get(step["phase"], 99)
        op_idx = self.OPERATION_ORDER.get(step["operation"], 99)
        sys_id = step.get("system_id", "")
        res_id = step.get("resource_id", "")
        return (phase_idx, op_idx, sys_id, res_id)

    def evaluate_case(self, case: Dict[str, str]) -> Tuple[str, str]:
        """Evaluate a single case and return (deletion_status, steps_json)."""
        case_id = case.get("case_id", "").strip()
        email = case.get("email", "").strip()
        request_text = case.get("request_text", "").strip()
        audit_at_str = case.get("audit_at", "").strip()
        audit_at = parse_timestamp(audit_at_str) or datetime.utcnow()

        # =========================================================================
        # 1. RULE 1: THE NOT_APPLICABLE RULE
        # =========================================================================
        if not self.is_valid_deletion_request(request_text):
            return "NOT_APPLICABLE", "[]"

        profile = self.resolver.resolve_identifiers(case_id, email)

        # Check background sync & restore hazards
        flow_and_restore_risks = self.evidence_parser.check_active_flows_and_restores(
            profile, audit_at
        )

        # Inspect storage evidence (SQLite, JSON, dumps, text logs)
        file_findings = self.evidence_parser.inspect_file_evidence(
            profile, audit_at
        )

        raw_steps: List[Dict[str, Any]] = []
        is_incomplete = False

        # --- A. Check Dynamic Flows & Restores ---
        for op, sys_id, res_id, evid, state in flow_and_restore_risks:
            is_incomplete = True
            # Finding Step (cites evidence_id)
            raw_steps.append({
                "phase": "FINDING",
                "system_id": sys_id,
                "resource_id": res_id,
                "operation": op,
                "state": state,
                "evidence_id": evid,
            })

            if op == "REPORT_ACTIVE_DATA_FLOW":
                # Remediation: DISABLE_DATA_FLOW (evidence_id: "")
                raw_steps.append({
                    "phase": "REMEDIATION",
                    "system_id": sys_id,
                    "resource_id": res_id,
                    "operation": "DISABLE_DATA_FLOW",
                    "state": "DISABLED",
                    "evidence_id": "",
                })
                # Future Verification: VERIFY_DATA_FLOW_DISABLED (evidence_id: "")
                raw_steps.append({
                    "phase": "VERIFICATION",
                    "system_id": sys_id,
                    "resource_id": res_id,
                    "operation": "VERIFY_DATA_FLOW_DISABLED",
                    "state": "DISABLED",
                    "evidence_id": "",
                })
            elif op == "REPORT_RESTORE_RISK":
                # Remediation: BLOCK_RESTORE (evidence_id: "")
                raw_steps.append({
                    "phase": "REMEDIATION",
                    "system_id": sys_id,
                    "resource_id": res_id,
                    "operation": "BLOCK_RESTORE",
                    "state": "BLOCKED",
                    "evidence_id": "",
                })
                # Future Verification: VERIFY_RESTORE_BLOCKED (evidence_id: "")
                raw_steps.append({
                    "phase": "VERIFICATION",
                    "system_id": sys_id,
                    "resource_id": res_id,
                    "operation": "VERIFY_RESTORE_BLOCKED",
                    "state": "BLOCKED",
                    "evidence_id": "",
                })

        # --- B. Check Storage Snapshots & Files Against Policy ---
        for f in file_findings:
            sys_id = f["system_id"]
            res_id = f["resource_id"]
            evid = f["evidence_id"]
            has_record = f["has_record"]
            has_pii = f["has_exposed_pii"]
            treatment = self.policy_engine.get_treatment(sys_id)

            if treatment == "ABSENT":
                if has_record:
                    is_incomplete = True
                    raw_steps.append({
                        "phase": "FINDING",
                        "system_id": sys_id,
                        "resource_id": res_id,
                        "operation": "REPORT_REMAINING_RECORD",
                        "state": "PRESENT",
                        "evidence_id": evid,
                    })
                    raw_steps.append({
                        "phase": "REMEDIATION",
                        "system_id": sys_id,
                        "resource_id": res_id,
                        "operation": "DELETE_RECORD",
                        "state": "ABSENT",
                        "evidence_id": "",
                    })
                    raw_steps.append({
                        "phase": "VERIFICATION",
                        "system_id": sys_id,
                        "resource_id": res_id,
                        "operation": "VERIFY_RECORD_ABSENT",
                        "state": "ABSENT",
                        "evidence_id": "",
                    })

            elif treatment in ("REDACTED", "RETAIN_TOMBSTONE"):
                if has_pii:
                    is_incomplete = True
                    raw_steps.append({
                        "phase": "FINDING",
                        "system_id": sys_id,
                        "resource_id": res_id,
                        "operation": "REPORT_EXPOSED_PII",
                        "state": "PRESENT",
                        "evidence_id": evid,
                    })
                    raw_steps.append({
                        "phase": "REMEDIATION",
                        "system_id": sys_id,
                        "resource_id": res_id,
                        "operation": "REDACT_RECORD",
                        "state": "REDACTED",
                        "evidence_id": "",
                    })
                    raw_steps.append({
                        "phase": "VERIFICATION",
                        "system_id": sys_id,
                        "resource_id": res_id,
                        "operation": "VERIFY_RECORD_REDACTED",
                        "state": "REDACTED",
                        "evidence_id": "",
                    })

            elif treatment == "ANONYMIZED":
                if has_pii:
                    is_incomplete = True
                    raw_steps.append({
                        "phase": "FINDING",
                        "system_id": sys_id,
                        "resource_id": res_id,
                        "operation": "REPORT_EXPOSED_PII",
                        "state": "PRESENT",
                        "evidence_id": evid,
                    })
                    raw_steps.append({
                        "phase": "REMEDIATION",
                        "system_id": sys_id,
                        "resource_id": res_id,
                        "operation": "ANONYMIZE_RECORD",
                        "state": "ANONYMIZED",
                        "evidence_id": "",
                    })
                    raw_steps.append({
                        "phase": "VERIFICATION",
                        "system_id": sys_id,
                        "resource_id": res_id,
                        "operation": "VERIFY_RECORD_ANONYMIZED",
                        "state": "ANONYMIZED",
                        "evidence_id": "",
                    })

        # =========================================================================
        # 2. RULE 3: THE EVIDENCE CITATION RULE
        # =========================================================================
        if not is_incomplete:
            # COMPLETE Case: Include verification steps citing valid evidence_id
            status = "COMPLETE"
            complete_steps: List[Dict[str, Any]] = []

            for f in file_findings:
                sys_id = f["system_id"]
                res_id = f["resource_id"]
                evid = f["evidence_id"]
                treatment = self.policy_engine.get_treatment(sys_id)

                # For COMPLETE cases, every verification step MUST cite a valid evidence_id
                if treatment in ("REDACTED", "RETAIN_TOMBSTONE"):
                    complete_steps.append({
                        "phase": "VERIFICATION",
                        "system_id": sys_id,
                        "resource_id": res_id,
                        "operation": "VERIFY_RECORD_REDACTED",
                        "state": "REDACTED",
                        "evidence_id": evid,
                    })
                elif treatment == "ANONYMIZED":
                    complete_steps.append({
                        "phase": "VERIFICATION",
                        "system_id": sys_id,
                        "resource_id": res_id,
                        "operation": "VERIFY_RECORD_ANONYMIZED",
                        "state": "ANONYMIZED",
                        "evidence_id": evid,
                    })

            # Sort using the 4-tuple key
            complete_steps.sort(key=self._make_sort_key)
            for idx, s in enumerate(complete_steps, start=1):
                s["step_no"] = idx

            return status, json.dumps(complete_steps)

        # INCOMPLETE Case: Deduplicate and apply 4-tuple sort key
        status = "INCOMPLETE"

        # Deduplicate steps by (phase, system_id, resource_id, operation)
        seen = set()
        deduped_steps = []
        for s in raw_steps:
            k = (s["phase"], s["system_id"], s["resource_id"], s["operation"])
            if k not in seen:
                seen.add(k)
                deduped_steps.append(s)

        # =========================================================================
        # 3. RULE 2: THE SORTING KEY RULE
        # Hierarchy: Phase -> Operation -> system_id -> resource_id
        # =========================================================================
        deduped_steps.sort(key=self._make_sort_key)

        for idx, s in enumerate(deduped_steps, start=1):
            s["step_no"] = idx

        return status, json.dumps(deduped_steps)
