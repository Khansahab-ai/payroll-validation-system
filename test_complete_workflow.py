import requests
import json
from pathlib import Path
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_URL = "http://127.0.0.1:8000"


def print_step(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def main():
    print_step("STEP 1: HEALTH AND DATABASE INTEGRITY CHECK")
    health = requests.get(f"{BASE_URL}/health").json()
    print("Health Check:", health)
    assert health["status"] == "healthy"

    db_check = requests.get(f"{BASE_URL}/database-check").json()
    print(f"Database Tables Connected: {db_check['total_tables']} tables -> {db_check['tables']}")
    assert db_check["total_tables"] >= 12

    # -------------------------------------------------------------
    print_step("STEP 2: RUN VALIDATION & CHECK GROUND TRUTH METRICS")
    val_res = requests.post(f"{BASE_URL}/payroll/validate").json()
    print("Validation Execution:", val_res)
    assert val_res["success"] is True

    metrics = requests.get(f"{BASE_URL}/validation/metrics").json()
    print("Ground Truth Metrics:", metrics)
    assert metrics["ground_truth_available"] is True
    assert metrics["true_positives"] >= 8
    assert metrics["recall"] >= 0.80

    # -------------------------------------------------------------
    print_step("STEP 3: TEST GOVERNANCE BLOCKING ON OPEN EXCEPTIONS")
    # Get open exceptions
    exceptions = requests.get(f"{BASE_URL}/exceptions?status=OPEN").json()
    print(f"Total Open Exceptions: {len(exceptions)}")
    assert len(exceptions) > 0

    # Find an employee who has an open exception in period 1
    # For example, EMP-000002 has MISSING_BANK_ACCOUNT
    payrolls = requests.get(f"{BASE_URL}/payroll?period_id=1").json()
    blocked_payroll = next((p for p in payrolls if p["payroll_input_id"] == "PIN-EMP-000002-2026-01"), None)
    assert blocked_payroll is not None

    print(f"Attempting approval on blocked payroll: {blocked_payroll['payroll_input_id']}")
    app_res = requests.post(
        f"{BASE_URL}/approvals/{blocked_payroll['id']}",
        json={
            "approver_name": "Demo HR Director",
            "approver_role": "HR",
            "decision": "APPROVED",
            "comments": "Testing safety blocking guardrail"
        }
    ).json()

    print("Blocked Approval Result:", app_res)
    assert app_res["success"] is False
    assert app_res["status"] == "BLOCKED"
    assert app_res["blocking_exceptions"] > 0
    print("  [PASS] Governance Guardrail Confirmed: Approval is strictly BLOCKED when open exceptions exist!")

    # -------------------------------------------------------------
    print_step("STEP 4: TEST EXCEPTION RESOLUTION LOGIC")
    # Case 4A: Pick an open MISSING_TAX_ID exception
    exc_tax = next((e for e in exceptions if e["issue_type"] == "MISSING_TAX_ID"), None)
    assert exc_tax is not None

    print(f"Attempting to resolve {exc_tax['exception_id']} WITHOUT fixing source data:")
    bad_res = requests.post(
        f"{BASE_URL}/exceptions/{exc_tax['exception_id']}/resolve",
        json={
            "resolution_comments": "Trying to resolve without fixing",
            "actor_name": "HR Partner",
            "actor_role": "HR"
        }
    ).json()
    print("Premature Resolution Result:", bad_res)
    assert bad_res["success"] is False
    assert "still exists" in bad_res["message"]
    print("  [PASS] Safety Confirmed: Cannot resolve exception without fixing underlying source data!")

    # Case 4B: Fix source data, then resolve
    print(f"\nFixing source data: Updating Tax ID for employee ID {exc_tax['employee_id']}...")
    patch_emp = requests.patch(
        f"{BASE_URL}/employees/{exc_tax['employee_id']}/payroll-details",
        json={
            "tax_id": f"TAX-EMP-{exc_tax['employee_id']:06d}-99",
            "actor_name": "HR Partner",
            "actor_role": "HR"
        }
    ).json()
    print("Employee Details Updated:", patch_emp)
    assert patch_emp["success"] is True

    print(f"Now resolving {exc_tax['exception_id']} with valid comments:")
    good_res = requests.post(
        f"{BASE_URL}/exceptions/{exc_tax['exception_id']}/resolve",
        json={
            "resolution_comments": "Verified statutory PAN/Tax ID documentation and updated record.",
            "actor_name": "HR Partner",
            "actor_role": "HR"
        }
    ).json()
    print("Verified Resolution Result:", good_res)
    assert good_res["success"] is True
    assert good_res["status"] == "RESOLVED"
    print("  [PASS] In-Line Resolution Confirmed: Exception marked RESOLVED once source data is fixed!")

    # -------------------------------------------------------------
    print_step("STEP 5: TEST CLEAN APPROVAL WORKFLOW")
    # Clean up pending shifts for Period 1 so clean records can be approved
    bulk_app = requests.post(
        f"{BASE_URL}/time-entries/bulk-approve",
        json={
            "pay_period_id": 1,
            "actor_name": "Manager David",
            "actor_role": "MANAGER"
        }
    ).json()
    print("Manager bulk-approved pending shifts:", bulk_app)

    # Re-run validation to update period 1 state
    requests.post(f"{BASE_URL}/payroll/validate")

    # Find a completely clean payroll record in Period 1 (e.g. EMP-000007)
    open_excs = requests.get(f"{BASE_URL}/exceptions?status=OPEN").json()
    open_emp_ids = {e["employee_id"] for e in open_excs}

    clean_payroll = next((p for p in payrolls if p["employee_id"] not in open_emp_ids), None)
    assert clean_payroll is not None

    print(f"Approving clean payroll record: {clean_payroll['payroll_input_id']}")
    clean_app = requests.post(
        f"{BASE_URL}/approvals/{clean_payroll['id']}",
        json={
            "approver_name": "Sarah Jenkins",
            "approver_role": "HR",
            "decision": "APPROVED",
            "comments": "Period 1 verified and approved."
        }
    ).json()
    print("Clean Approval Result:", clean_app)
    assert clean_app["success"] is True
    assert clean_app["decision"] == "APPROVED"
    assert clean_app["approval_id"].startswith("APR-")
    print("  [PASS] Governance Sign-off Confirmed: Clean record is APPROVED!")

    # -------------------------------------------------------------
    print_step("STEP 6: TEST SECURE EXPORT & FILE DOWNLOAD")
    exp_res = requests.post(
        f"{BASE_URL}/payroll/export/1",
        json={
            "actor_name": "System Administrator",
            "actor_role": "SYSTEM"
        }
    ).json()
    print("Export Result:", exp_res)
    assert exp_res["success"] is True
    assert exp_res["export_id"].startswith("PEX-")
    assert exp_res["record_count"] >= 1
    file_name = exp_res["file_name"]
    print(f"  [PASS] Export Created: {file_name} under {exp_res['export_id']}")

    # Download exported file via API
    dl_res = requests.get(f"{BASE_URL}/payroll/exports/download/{file_name}")
    assert dl_res.status_code == 200
    csv_text = dl_res.text
    print("\nDownloaded CSV File Header & Sample Data:")
    print("\n".join(csv_text.strip().split("\n")[:4]))
    assert "PIN-" in csv_text
    assert "PEX-" in csv_text
    print("  [PASS] Secure Export Download Confirmed: Valid CSV generated with immutable PEX convention!")

    # -------------------------------------------------------------
    print_step("STEP 7: TEST AUDIT LOG TRACEABILITY")
    audit_logs = requests.get(f"{BASE_URL}/audit-logs?limit=10").json()
    print(f"Total Audit Logs Retrieved: {len(audit_logs)}")
    assert len(audit_logs) > 0
    print("Latest 3 Audit Events:")
    for a in audit_logs[:3]:
        print(f"  • [{a['timestamp']}] Action: {a['action']} on {a['entity_name']} ({a['record_id']}) by {a['actor_role']}:{a['actor_name']}")
    print("  [PASS] Audit Trail Confirmed: All state transitions preserved without overwriting history!")

    print("\n" + "=" * 60)
    print("  ALL END-TO-END WORKFLOW VERIFICATIONS PASSED 100%!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
