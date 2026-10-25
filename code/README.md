# Ghost Data Still Exists: Deletion Audit Agent

## Architecture Overview
The system provides a deterministic audit pipeline to verify whether GDPR/CCPA personal data deletion requests are genuinely fulfilled across distributed microservices, replicas, logs, backups, and active synchronization pipelines.

### Modules:
1. **`identity_resolver.py`**: Resolves historical and current identity graphs (aliases, former emails, phone numbers, SHA256 email hashes).
2. **`evidence_parser.py`**: Ingests multi-modal database snapshots (`.sqlite`/`.db`/`.sql`), JSON logs, unstructured support attachments, and cross-references active synchronization or restore jobs in `system_activity.csv`.
3. **`policy_engine.py`**: Evaluates compliance against `deletion_rules.csv`, accounting for tombstones and legal retention mandates.
4. **`agent.py`**: Classifies request intent (`COMPLETE`, `INCOMPLETE`, `NOT_APPLICABLE`) and generates strictly ordered steps adhering to the operational hierarchy and 4-tuple sorting key: `(phase_order, operation_order, system_id, resource_id)`.
5. **`main.py`**: Batch CLI runner producing the sorted 518-row `output.csv`.
6. **`validate_sample.py`**: Regression verification against sample benchmarks.
7. **`verify_output.py`**: Invariant validator for `output.csv` (row count, status enum, sorting, JSON validity).
8. **`pre_flight_check.py`**: End-to-end verification script for validation criteria.

## Setup and Execution
```bash
# Install optional dependencies
pip install -r code/requirements.txt

# 1. Run Sample Validation
python3 code/validate_sample.py

# 2. Run Full Audit
python3 code/main.py

# 3. Verify Output
python3 code/verify_output.py

# 4. Run Pre-Flight Checks
python3 code/pre_flight_check.py
```
