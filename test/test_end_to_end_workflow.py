import requests
import json
from pathlib import Path
import pytest

BASE_URL = "http://127.0.0.1:8000"


def test_full_system_workflow_end_to_end():
    # 1. Health
    health = requests.get(f"{BASE_URL}/health").json()
    assert health["status"] == "healthy"

    # 2. Validation
    val_res = requests.post(f"{BASE_URL}/payroll/validate").json()
    assert val_res["success"] is True

    # 3. Blocking check on record with open exception
    payrolls = requests.get(f"{BASE_URL}/payroll?period_id=1").json()
    blocked_payroll = next((p for p in payrolls if p["payroll_input_id"] == "PIN-EMP-000003-2026-01" or p["payroll_input_id"] == "PIN-EMP-000001-2026-01"), payrolls[0])

    app_res = requests.post(
        f"{BASE_URL}/approvals/{blocked_payroll['id']}",
        json={
            "approver_name": "Demo HR Director",
            "approver_role": "HR",
            "decision": "APPROVED",
            "comments": "Testing safety blocking guardrail"
        }
    ).json()

    # If it has open exceptions, it must be BLOCKED
    exceptions = requests.get(f"{BASE_URL}/exceptions?status=OPEN").json()
    emp_open_excs = [e for e in exceptions if e["employee_id"] == blocked_payroll["employee_id"]]
    if emp_open_excs:
        assert app_res["success"] is False
        assert app_res["status"] == "BLOCKED"

    # 4. Clean Approval & Export
    open_emp_ids = {e["employee_id"] for e in exceptions}
    clean_payroll = next((p for p in payrolls if p["employee_id"] not in open_emp_ids), None)

    if clean_payroll:
        clean_app = requests.post(
            f"{BASE_URL}/approvals/{clean_payroll['id']}",
            json={
                "approver_name": "Sarah Jenkins",
                "approver_role": "HR",
                "decision": "APPROVED",
                "comments": "Approved clean test record"
            }
        ).json()
        assert clean_app["success"] is True

        exp_res = requests.post(
            f"{BASE_URL}/payroll/export/{clean_payroll['pay_period_id']}",
            json={"actor_name": "System Administrator", "actor_role": "SYSTEM"}
        ).json()
        assert exp_res["success"] is True
        assert exp_res["export_id"].startswith("PEX-")

