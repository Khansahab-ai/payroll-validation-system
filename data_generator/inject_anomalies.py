import csv
from datetime import date
import json
from pathlib import Path
from typing import Any, Dict, List
from sqlmodel import Session, select

from backend.models.models import (
    Employee,
    PayGroup,
    PayPeriod,
    TimeEntry,
    Allowance,
    Deduction,
    PayrollInput,
    LeaveRecord
)


def inject_edge_cases_and_ground_truth(session: Session) -> List[Dict[str, Any]]:
    """
    Inject the 8 required labelled edge cases into the dataset and generate
    separate ground_truth.json and ground_truth.csv records without leaking into features.

    Planted Edge Cases:
    1. Missing bank account (RULE-BANK-001)
    2. Missing tax ID (RULE-TAX-001)
    3. Duplicate time entry submission (RULE-TIME-DUP-001)
    4. Hours exceed period maximum (RULE-TIME-EXC-001)
    5. Same allowance duplicated (RULE-ALW-DUP-001)
    6. Unapproved time entries pending (RULE-TIME-UNAPP-001)
    7. Leave deduction applied twice (RULE-LEV-DUP-001)
    8. Payroll totals fail to reconcile (RULE-PAY-RECON-001)
    """
    ground_truth: List[Dict[str, Any]] = []

    employees = session.exec(select(Employee).order_by(Employee.id)).all()
    periods = session.exec(select(PayPeriod).order_by(PayPeriod.start_date)).all()
    period_1 = periods[0] if len(periods) > 0 else None
    period_2 = periods[1] if len(periods) > 1 else period_1

    # =========================================================
    # 1. Missing Bank Accounts (RULE-BANK-001)
    # =========================================================
    if len(employees) >= 3:
        target_bank = employees[1:3]  # EMP-000002, EMP-000003
        for emp in target_bank:
            emp.bank_account = None
            session.add(emp)
            ground_truth.append({
                "record_id": emp.employee_id,
                "entity_type": "Employee",
                "pay_period": "ALL",
                "rule_code": "RULE-BANK-001",
                "issue_type": "MISSING_BANK_ACCOUNT",
                "expected_decision": "BLOCK_APPROVAL",
                "description": f"Planted null bank account for active employee {emp.employee_id}",
                "ground_truth_label": "ANOMALY"
            })

    # =========================================================
    # 2. Missing Tax IDs (RULE-TAX-001)
    # =========================================================
    if len(employees) >= 6:
        target_tax = employees[3:5]  # EMP-000004, EMP-000005
        for emp in target_tax:
            emp.tax_id = None
            session.add(emp)
            ground_truth.append({
                "record_id": emp.employee_id,
                "entity_type": "Employee",
                "pay_period": "ALL",
                "rule_code": "RULE-TAX-001",
                "issue_type": "MISSING_TAX_ID",
                "expected_decision": "BLOCK_APPROVAL",
                "description": f"Planted null tax ID for active employee {emp.employee_id}",
                "ground_truth_label": "ANOMALY"
            })

    # =========================================================
    # 3. Duplicate Time Entry Submission (RULE-TIME-DUP-001)
    # =========================================================
    first_time_entry = session.exec(
        select(TimeEntry).where(TimeEntry.approval_status == "APPROVED").order_by(TimeEntry.id)
    ).first()

    if first_time_entry:
        dup_time_id = f"{first_time_entry.time_id}-DUP"
        existing_dup = session.exec(select(TimeEntry).where(TimeEntry.time_id == dup_time_id)).first()
        if not existing_dup:
            dup_entry = TimeEntry(
                time_id=dup_time_id,
                employee_id=first_time_entry.employee_id,
                pay_period_id=first_time_entry.pay_period_id,
                work_date=first_time_entry.work_date,
                hours_worked=first_time_entry.hours_worked,
                approval_status="APPROVED",
                submission_ref=first_time_entry.submission_ref  # Duplicate reference!
            )
            session.add(dup_entry)
            ground_truth.append({
                "record_id": dup_time_id,
                "entity_type": "TimeEntry",
                "pay_period": period_1.period_code if period_1 else "PP-2026-01",
                "rule_code": "RULE-TIME-DUP-001",
                "issue_type": "DUPLICATE_TIME_ENTRY",
                "expected_decision": "FLAG_EXCEPTION",
                "description": f"Planted duplicate time submission with reference {first_time_entry.submission_ref}",
                "ground_truth_label": "ANOMALY"
            })

    # =========================================================
    # 4. Hours Exceed Period Maximum (RULE-TIME-EXC-001)
    # =========================================================
    part_time_group = session.exec(
        select(PayGroup).where(PayGroup.group_code == "PG-003")
    ).first()

    if part_time_group:
        pt_emp = session.exec(
            select(Employee).where(Employee.pay_group_id == part_time_group.id)
        ).first()

        if pt_emp and period_1:
            # Inject an extra shift pushing total over 100 hours or a 20h shift
            excess_time_id = f"TIME-{pt_emp.employee_id}-2026-01-28-EXCESS"
            existing_excess = session.exec(select(TimeEntry).where(TimeEntry.time_id == excess_time_id)).first()
            if not existing_excess:
                excess_entry = TimeEntry(
                    time_id=excess_time_id,
                    employee_id=pt_emp.id,
                    pay_period_id=period_1.id,
                    work_date=date(2026, 1, 28),
                    hours_worked=20.0,  # Extreme shift outlier + period max exceeded
                    approval_status="APPROVED",
                    submission_ref=f"SUB-{pt_emp.employee_id}-2026-01-28-EXCESS"
                )
                session.add(excess_entry)
                ground_truth.append({
                    "record_id": pt_emp.employee_id,
                    "entity_type": "TimeEntry",
                    "pay_period": period_1.period_code,
                    "rule_code": "RULE-TIME-EXC-001",
                    "issue_type": "EXCESSIVE_WORKING_HOURS",
                    "expected_decision": "FLAG_EXCEPTION",
                    "description": f"Planted 20.0h excessive hours for part-time employee {pt_emp.employee_id}",
                    "ground_truth_label": "ANOMALY"
                })

    # =========================================================
    # 5. Same Allowance Duplicated (RULE-ALW-DUP-001)
    # =========================================================
    first_alw = session.exec(select(Allowance).order_by(Allowance.id)).first()
    if first_alw:
        dup_alw_id = f"{first_alw.allowance_id}-DUP"
        existing_alw_dup = session.exec(select(Allowance).where(Allowance.allowance_id == dup_alw_id)).first()
        if not existing_alw_dup:
            dup_alw = Allowance(
                allowance_id=dup_alw_id,
                employee_id=first_alw.employee_id,
                pay_period_id=first_alw.pay_period_id,
                allowance_type=first_alw.allowance_type,
                amount=first_alw.amount,
                effective_date=first_alw.effective_date,
                reference_code=first_alw.reference_code  # Same reference code!
            )
            session.add(dup_alw)
            ground_truth.append({
                "record_id": dup_alw_id,
                "entity_type": "Allowance",
                "pay_period": period_1.period_code if period_1 else "PP-2026-01",
                "rule_code": "RULE-ALW-DUP-001",
                "issue_type": "DUPLICATE_ALLOWANCE",
                "expected_decision": "FLAG_EXCEPTION",
                "description": f"Planted duplicate allowance with reference {first_alw.reference_code}",
                "ground_truth_label": "ANOMALY"
            })

    # =========================================================
    # 6. Unapproved Time Entries Pending (RULE-TIME-UNAPP-001)
    # =========================================================
    unapp_entry = session.exec(
        select(TimeEntry).where(TimeEntry.approval_status == "PENDING").order_by(TimeEntry.id)
    ).first()

    if unapp_entry:
        emp_unapp = session.get(Employee, unapp_entry.employee_id)
        per_unapp = session.get(PayPeriod, unapp_entry.pay_period_id)
        if emp_unapp and per_unapp:
            ground_truth.append({
                "record_id": per_unapp.period_code,
                "entity_type": "TimeEntry",
                "pay_period": per_unapp.period_code,
                "rule_code": "RULE-TIME-UNAPP-001",
                "issue_type": "UNAPPROVED_TIME_ENTRY",
                "expected_decision": "BLOCK_APPROVAL",
                "description": f"Planted pending unapproved time entry for {emp_unapp.employee_id} in {per_unapp.period_code}",
                "ground_truth_label": "ANOMALY"
            })

    # =========================================================
    # 7. Leave Deduction Applied Twice (RULE-LEV-DUP-001)
    # =========================================================
    first_leave_ded = session.exec(
        select(Deduction).where(Deduction.deduction_type == "UNPAID_LEAVE").order_by(Deduction.id)
    ).first()

    if not first_leave_ded and len(employees) > 0 and period_1:
        # Create an unpaid leave and deduction to test double deduction
        emp_for_leave = employees[0]
        test_leave = LeaveRecord(
            leave_id=f"LEV-{emp_for_leave.employee_id}-2026-01-15-TEST",
            employee_id=emp_for_leave.id,
            pay_period_id=period_1.id,
            leave_type="UNPAID",
            start_date=date(2026, 1, 15),
            end_date=date(2026, 1, 16),
            days=2.0,
            approval_status="APPROVED",
            is_unpaid=True
        )
        session.add(test_leave)
        session.flush()

        first_leave_ded = Deduction(
            deduction_id=f"DED-{emp_for_leave.employee_id}-2026-01-TEST-01",
            employee_id=emp_for_leave.id,
            pay_period_id=period_1.id,
            deduction_type="UNPAID_LEAVE",
            amount=round(2.0 * (emp_for_leave.basic_salary / 30.0), 2),
            effective_date=date(2026, 1, 15),
            reference_code=f"REF-DED-{emp_for_leave.employee_id}-2026-01-UNPAID-TEST",
            leave_record_id=test_leave.id
        )
        session.add(first_leave_ded)
        session.flush()

    if first_leave_ded:
        dup_ded_id = f"{first_leave_ded.deduction_id}-DUP"
        existing_dup_ded = session.exec(select(Deduction).where(Deduction.deduction_id == dup_ded_id)).first()
        if not existing_dup_ded:
            dup_leave_ded = Deduction(
                deduction_id=dup_ded_id,
                employee_id=first_leave_ded.employee_id,
                pay_period_id=first_leave_ded.pay_period_id,
                deduction_type="UNPAID_LEAVE",
                amount=first_leave_ded.amount,
                effective_date=first_leave_ded.effective_date,
                reference_code=first_leave_ded.reference_code,  # Duplicate reference and leave_record_id!
                leave_record_id=first_leave_ded.leave_record_id
            )
            session.add(dup_leave_ded)
            ground_truth.append({
                "record_id": dup_ded_id,
                "entity_type": "Deduction",
                "pay_period": period_1.period_code if period_1 else "PP-2026-01",
                "rule_code": "RULE-LEV-DUP-001",
                "issue_type": "DUPLICATE_LEAVE_DEDUCTION",
                "expected_decision": "FLAG_EXCEPTION",
                "description": f"Planted double leave deduction {dup_ded_id} for leave record ID {first_leave_ded.leave_record_id}",
                "ground_truth_label": "ANOMALY"
            })

    session.commit()

    # =========================================================
    # 8. Payroll Totals Fail to Reconcile (RULE-PAY-RECON-001)
    # =========================================================
    # We will corrupt one payroll input net pay after payroll is generated
    sample_payroll = session.exec(select(PayrollInput).order_by(PayrollInput.id.desc())).first()
    if sample_payroll:
        sample_payroll.net_pay = round(sample_payroll.net_pay + 5000.0, 2)  # Planted reconciliation error!
        session.add(sample_payroll)
        session.commit()
        ground_truth.append({
            "record_id": sample_payroll.payroll_input_id,
            "entity_type": "PayrollInput",
            "pay_period": period_1.period_code if period_1 else "PP-2026-01",
            "rule_code": "RULE-PAY-RECON-001",
            "issue_type": "PAYROLL_RECONCILIATION_MISMATCH",
            "expected_decision": "FLAG_EXCEPTION",
            "description": f"Planted net pay calculation discrepancy (+₹5,000) on {sample_payroll.payroll_input_id}",
            "ground_truth_label": "ANOMALY"
        })

    # Save Ground Truth to datasets/ground_truth.json and datasets/ground_truth.csv
    datasets_dir = Path("datasets")
    datasets_dir.mkdir(exist_ok=True)

    gt_json_path = datasets_dir / "ground_truth.json"
    with open(gt_json_path, "w", encoding="utf-8") as f:
        json.dump(ground_truth, f, indent=2)

    gt_csv_path = datasets_dir / "ground_truth.csv"
    if ground_truth:
        keys = list(ground_truth[0].keys())
        with open(gt_csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(ground_truth)

    # Also place at root for convenient accessibility
    with open("ground_truth.json", "w", encoding="utf-8") as f:
        json.dump(ground_truth, f, indent=2)

    return ground_truth
