"""Policy Enforcement Engine.

Validates compliant states according to regulatory and tombstone policies.
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class RuleDefinition:
    data_category: str
    system_id: str
    required_treatment: (
        str  # ABSENT, REDACTED, ANONYMIZED, RETAIN_TOMBSTONE, RETAIN_COMPLIANCE
    )
    permitted_fields: str
    prohibited_fields: str


class PolicyEngine:
    """Enforces deletion rules and treatment policies across data categories."""

    def __init__(self, rules_path: str) -> None:
        self.rules_path = rules_path
        self.rules: Dict[str, RuleDefinition] = {}
        self._load_rules()

    def _load_rules(self) -> None:
        if not os.path.exists(self.rules_path):
            return

        with open(self.rules_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cat = (
                    row.get("data_category")
                    or row.get("category", "")
                ).strip()
                sys_id = row.get("system_id", "").strip()
                treatment = (
                    row.get("required_treatment")
                    or row.get("treatment", "")
                ).strip().upper()
                permitted = row.get("permitted_fields", "").strip()
                prohibited = row.get("prohibited_fields", "").strip()

                key = f"{sys_id}:{cat}" if sys_id and cat else (sys_id or cat)
                rule = RuleDefinition(
                    data_category=cat,
                    system_id=sys_id,
                    required_treatment=treatment,
                    permitted_fields=permitted,
                    prohibited_fields=prohibited,
                )
                if key:
                    self.rules[key] = rule
                if sys_id:
                    self.rules[sys_id] = rule

    def get_treatment(
        self, system_id: str, data_category: str = ""
    ) -> str:
        """Fetch required treatment; defaults to ABSENT if not explicitly exempted."""
        key = f"{system_id}:{data_category}"
        if key in self.rules:
            return self.rules[key].required_treatment
        if system_id in self.rules:
            return self.rules[system_id].required_treatment
        if data_category in self.rules:
            return self.rules[data_category].required_treatment
        return "ABSENT"
