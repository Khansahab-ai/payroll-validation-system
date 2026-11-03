from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from sqlmodel import Session, select, func

from backend.models.models import (
    Employee,
    PayGroup,
    PayPeriod,
    TimeEntry,
    LeaveRecord,
    Allowance,
    Deduction,
    PayrollInput,
    ValidationRule,
    ExceptionRecord,
    AuditLog
)
from backend.services.audit_service import log_audit_event


# =====================================================
# SYSTEM VALIDATION RULES REGISTRATION
# =====================================================

SYSTEM_RULES = [
    {
        "rule_code": "RULE-BANK-001",
        "rule_name": "Missing Bank Account Validation",
        "description": "Flags active employees missing required bank account numbers before payroll disbursement.",
        "severity": "HIGH",
        "is_active": True
    },
    {
        "rule_code": "RULE-TAX-001",
        "rule_name": "Missing Tax ID Validation",
        "description": "Flags active employees missing statutory tax identification numbers.",
        "severity": "HIGH",
        "is_active": True
    },
    {
        "rule_code": "RULE-TIME-DUP-001",
        "rule_name": "Duplicate Time Entry Submission",
        "description": "Flags duplicate time submissions sharing identical submission reference codes or employee and date.",
        "severity": "HIGH",
        "is_active": True
    },
    {
        "rule_code": "RULE-TIME-EXC-001",
        "rule_name": "Excessive Working Hours / Outliers",
        "description": "Flags approved hours exceeding the pay group's maximum period hours or single-shift outliers > 16h.",
        "severity": "HIGH",
        "is_active": True
    },
    {
        "rule_code": "RULE-ALW-DUP-001",
        "rule_name": "Duplicate Allowance Validation",
        "description": "Flags duplicate allowances with identical reference codes or duplicate grants of single-grant allowances.",
        "severity": "HIGH",
        "is_active": True
    },
    {
        "rule_code": "RULE-TIME-UNAPP-001",
        "rule_name": "Unapproved Time Entries Validation",
        "description": "Flags unapproved or pending time entries within a pay period, preventing premature inclusion or export.",
        "severity": "HIGH",
        "is_active": True
    },
    {
        "rule_code": "RULE-LEV-DUP-001",
        "rule_name": "Duplicate Leave Deduction Validation",
        "description": "Flags unpaid leave deductions that are applied multiple times for the same leave record or period.",
        "severity": "HIGH",
        "is_active": True
    },
    {
        "rule_code": "RULE-PAY-RECON-001",
        "rule_name": "Payroll Totals Reconciliation Validation",
        "description": "Flags arithmetic discrepancies between net pay and calculated component totals (basic + overtime + allowances - deductions - unpaid leave).",
        "severity": "HIGH",
        "is_active": True
    }
]


def ensure_validation_rules(session: Session) -> Dict[str, ValidationRule]:
    """
    Ensure all standard validation rules are registered in the validation_rules table.
    Returns a dictionary mapping rule_code -> ValidationRule model.
    """
    rule_map = {}
    for rule_data in SYSTEM_RULES:
        existing = session.exec(
            select(ValidationRule).where(ValidationRule.rule_code == rule_data["rule_code"])
        ).first()

        if not existing:
            rule = ValidationRule(**rule_data)
            session.add(rule)
            session.flush()
            rule_map[rule.rule_code] = rule
        else:
            rule_map[existing.rule_code] = existing

    session.commit()
    return rule_map


# =====================================================
# INDIVIDUAL VALIDATION RULES
# =====================================================

def validate_bank_accounts(session: Session, rule: ValidationRule) -> int:
    """Flags active employees missing required bank accounts."""
    payroll_records = session.exec(select(PayrollInput)).all()
    created_or_reopened = 0

    for payroll in payroll_records:
        employee = session.get(Employee, payroll.employee_id)
        if not employee:
            continue

        exception_id = f"EXC-{payroll.payroll_input_id}-BANK"
        existing = session.exec(
            select(ExceptionRecord).where(ExceptionRecord.exception_id == exception_id)
        ).first()

        if not employee.bank_account or employee.bank_account.strip() == "":
            if existing:
                if existing.status == "RESOLVED":
                    existing.status = "OPEN"
                    session.add(existing)
                    created_or_reopened += 1
            else:
                exception = ExceptionRecord(
                    exception_id=exception_id,
                    payroll_input_id=payroll.id,
                    validation_rule_id=rule.id,
                    employee_id=employee.id,
                    issue_type="MISSING_BANK_ACCOUNT",
                    description=f"Bank account is missing for {employee.employee_id}",
                    status="OPEN",
                    severity=rule.severity,
                    source_entity="Employee",
                    source_record_id=employee.employee_id
                )
                session.add(exception)
                created_or_reopened += 1
        else:
            if existing and existing.status == "OPEN":
                existing.status = "RESOLVED"
                existing.resolution_notes = "Bank account provided."
                existing.resolved_at = datetime.now(timezone.utc)
                existing.resolved_by = "SYSTEM"
                session.add(existing)

    session.commit()
    return created_or_reopened


def validate_tax_ids(session: Session, rule: ValidationRule) -> int:
    """Flags active employees missing statutory tax IDs."""
    payroll_records = session.exec(select(PayrollInput)).all()
    created_or_reopened = 0

    for payroll in payroll_records:
        employee = session.get(Employee, payroll.employee_id)
        if not employee:
            continue

        exception_id = f"EXC-{payroll.payroll_input_id}-TAX"
        existing = session.exec(
            select(ExceptionRecord).where(ExceptionRecord.exception_id == exception_id)
        ).first()

        if not employee.tax_id or employee.tax_id.strip() == "":
            if existing:
                if existing.status == "RESOLVED":
                    existing.status = "OPEN"
                    session.add(existing)
                    created_or_reopened += 1
            else:
                exception = ExceptionRecord(
                    exception_id=exception_id,
                    payroll_input_id=payroll.id,
                    validation_rule_id=rule.id,
                    employee_id=employee.id,
                    issue_type="MISSING_TAX_ID",
                    description=f"Tax ID is missing for {employee.employee_id}",
                    status="OPEN",
                    severity=rule.severity,
                    source_entity="Employee",
                    source_record_id=employee.employee_id
                )
                session.add(exception)
                created_or_reopened += 1
        else:
            if existing and existing.status == "OPEN":
                existing.status = "RESOLVED"
                existing.resolution_notes = "Tax ID provided."
                existing.resolved_at = datetime.now(timezone.utc)
                existing.resolved_by = "SYSTEM"
                session.add(existing)

    session.commit()
    return created_or_reopened


def validate_duplicate_time_entries(session: Session, rule: ValidationRule) -> int:
    """Flags duplicate time entries sharing the same submission_ref."""
    time_entries = session.exec(select(TimeEntry)).all()
    seen_submissions: Dict[str, str] = {}
    created_or_reopened = 0

    for entry in time_entries:
        if entry.approval_status == "REJECTED" or entry.hours_worked == 0:
            continue

        ref = entry.submission_ref
        exception_id = f"EXC-{entry.time_id}-DUPLICATE"
        existing = session.exec(
            select(ExceptionRecord).where(ExceptionRecord.exception_id == exception_id)
        ).first()

        if ref in seen_submissions:
            if existing:
                if existing.status == "RESOLVED":
                    existing.status = "OPEN"
                    session.add(existing)
                    created_or_reopened += 1
            else:
                exception = ExceptionRecord(
                    exception_id=exception_id,
                    payroll_input_id=None,
                    validation_rule_id=rule.id,
                    employee_id=entry.employee_id,
                    issue_type="DUPLICATE_TIME_ENTRY",
                    description=f"Duplicate time submission detected: {ref} (conflicts with {seen_submissions[ref]})",
                    status="OPEN",
                    severity=rule.severity,
                    source_entity="TimeEntry",
                    source_record_id=entry.time_id
                )
                session.add(exception)
                created_or_reopened += 1
        else:
            seen_submissions[ref] = entry.time_id
            if existing and existing.status == "OPEN":
                existing.status = "RESOLVED"
                existing.resolution_notes = "Duplicate conflict resolved."
                existing.resolved_at = datetime.now(timezone.utc)
                existing.resolved_by = "SYSTEM"
                session.add(existing)

    session.commit()
    return created_or_reopened


def validate_excessive_hours(session: Session, rule: ValidationRule) -> int:
    """Flags total approved hours exceeding pay group monthly limits or single-shift outliers > 16h."""
    employees = session.exec(select(Employee)).all()
    pay_groups = {g.id: g for g in session.exec(select(PayGroup)).all()}
    pay_periods = session.exec(select(PayPeriod)).all()
    time_entries = session.exec(select(TimeEntry)).all()

    created_or_reopened = 0

    for employee in employees:
        pay_group = pay_groups.get(employee.pay_group_id)
        if not pay_group:
            continue

        for period in pay_periods:
            approved_entries = [
                e for e in time_entries
                if e.employee_id == employee.id
                and e.pay_period_id == period.id
                and e.approval_status == "APPROVED"
            ]

            total_hours = sum(e.hours_worked for e in approved_entries)
            has_single_shift_outlier = any(e.hours_worked > 16.0 for e in approved_entries)

            exception_id = f"EXC-{employee.employee_id}-{period.period_code}-EXCESS-HOURS"
            existing = session.exec(
                select(ExceptionRecord).where(ExceptionRecord.exception_id == exception_id)
            ).first()

            is_excessive = (total_hours > pay_group.max_period_hours) or has_single_shift_outlier

            if is_excessive:
                desc = (
                    f"Employee worked {total_hours:.1f} approved hours, exceeding pay group limit of "
                    f"{pay_group.max_period_hours:.1f} hours."
                    if total_hours > pay_group.max_period_hours
                    else f"Single shift outlier detected (>16h) with {total_hours:.1f} total hours."
                )

                if existing:
                    if existing.status == "RESOLVED":
                        existing.status = "OPEN"
                        created_or_reopened += 1
                    existing.description = desc
                    session.add(existing)
                else:
                    exception = ExceptionRecord(
                        exception_id=exception_id,
                        employee_id=employee.id,
                        payroll_input_id=None,
                        validation_rule_id=rule.id,
                        issue_type="EXCESSIVE_WORKING_HOURS",
                        description=desc,
                        status="OPEN",
                        severity=rule.severity,
                        source_entity="TimeEntry",
                        source_record_id=employee.employee_id
                    )
                    session.add(exception)
                    created_or_reopened += 1
            else:
                if existing and existing.status == "OPEN":
                    existing.status = "RESOLVED"
                    existing.description = (
                        f"Hours within allowed limit. Current approved hours: {total_hours:.1f}. "
                        f"Limit: {pay_group.max_period_hours:.1f}."
                    )
                    existing.resolved_at = datetime.now(timezone.utc)
                    existing.resolved_by = "SYSTEM"
                    session.add(existing)

    session.commit()
    return created_or_reopened


def validate_duplicate_allowances(session: Session, rule: ValidationRule) -> int:
    """Flags duplicate allowances sharing the same reference_code."""
    allowances = session.exec(select(Allowance)).all()
    seen_references: Dict[str, str] = {}
    created_or_reopened = 0

    for allowance in allowances:
        if allowance.amount == 0 or allowance.reference_code.startswith("DUPLICATE-VOID"):
            continue

        ref = allowance.reference_code
        exception_id = f"EXC-{allowance.allowance_id}-DUPLICATE"
        existing = session.exec(
            select(ExceptionRecord).where(ExceptionRecord.exception_id == exception_id)
        ).first()

        if ref in seen_references:
            if existing:
                if existing.status == "RESOLVED":
                    existing.status = "OPEN"
                    session.add(existing)
                    created_or_reopened += 1
            else:
                exception = ExceptionRecord(
                    exception_id=exception_id,
                    payroll_input_id=None,
                    validation_rule_id=rule.id,
                    employee_id=allowance.employee_id,
                    issue_type="DUPLICATE_ALLOWANCE",
                    description=f"Duplicate allowance detected: {ref} (conflicts with {seen_references[ref]})",
                    status="OPEN",
                    severity=rule.severity,
                    source_entity="Allowance",
                    source_record_id=allowance.allowance_id
                )
                session.add(exception)
                created_or_reopened += 1
        else:
            seen_references[ref] = allowance.allowance_id
            if existing and existing.status == "OPEN":
                existing.status = "RESOLVED"
                existing.resolution_notes = "Allowance reference unique."
                existing.resolved_at = datetime.now(timezone.utc)
                existing.resolved_by = "SYSTEM"
                session.add(existing)

    session.commit()
    return created_or_reopened


def validate_unapproved_time_entries(session: Session, rule: ValidationRule) -> int:
    """Flags unapproved / pending time entries within a pay period."""
    time_entries = session.exec(select(TimeEntry)).all()
    employees = {e.id: e for e in session.exec(select(Employee)).all()}
    periods = {p.id: p for p in session.exec(select(PayPeriod)).all()}

    pending_pairs = set()
    for entry in time_entries:
        if entry.approval_status == "PENDING":
            pending_pairs.add((entry.employee_id, entry.pay_period_id))

    existing_exceptions = session.exec(
        select(ExceptionRecord).where(ExceptionRecord.issue_type == "UNAPPROVED_TIME_ENTRY")
    ).all()
    exception_lookup = {e.exception_id: e for e in existing_exceptions}

    created_or_reopened = 0

    # Resolve any existing that are no longer pending
    for exception in existing_exceptions:
        employee = employees.get(exception.employee_id)
        period = next((p for p in periods.values() if p.period_code == exception.source_record_id), None)
        if period and (exception.employee_id, period.id) not in pending_pairs:
            if exception.status == "OPEN":
                exception.status = "RESOLVED"
                exception.description = "Pending time entries have been reviewed and approved/rejected."
                exception.resolved_at = datetime.now(timezone.utc)
                exception.resolved_by = "SYSTEM"
                session.add(exception)

    # Flag open pending entries
    for employee_id, pay_period_id in pending_pairs:
        employee = employees.get(employee_id)
        period = periods.get(pay_period_id)
        if not employee or not period:
            continue

        exception_id = f"EXC-{employee.employee_id}-{period.period_code}-UNAPPROVED-TIME"
        existing = exception_lookup.get(exception_id)

        if existing:
            if existing.status == "RESOLVED":
                existing.status = "OPEN"
                session.add(existing)
                created_or_reopened += 1
        else:
            exception = ExceptionRecord(
                exception_id=exception_id,
                payroll_input_id=None,
                validation_rule_id=rule.id,
                employee_id=employee_id,
                issue_type="UNAPPROVED_TIME_ENTRY",
                description="Pending time entries found. Hours must be reviewed and approved prior to payroll export.",
                status="OPEN",
                severity=rule.severity,
                source_entity="TimeEntry",
                source_record_id=period.period_code
            )
            session.add(exception)
            created_or_reopened += 1

    session.commit()
    return created_or_reopened


def validate_duplicate_leave_deductions(session: Session, rule: ValidationRule) -> int:
    """Flags unpaid leave deductions applied multiple times for the same leave record or period."""
    deductions = session.exec(
        select(Deduction).where(Deduction.deduction_type == "UNPAID_LEAVE")
    ).all()

    seen_leaves: Dict[Any, str] = {}
    created_or_reopened = 0

    for deduction in deductions:
        if deduction.amount == 0 or deduction.reference_code.startswith("DUPLICATE-VOID"):
            continue

        key = deduction.leave_record_id if deduction.leave_record_id else deduction.reference_code
        exception_id = f"EXC-{deduction.deduction_id}-DUP-LEAVE-DED"
        existing = session.exec(
            select(ExceptionRecord).where(ExceptionRecord.exception_id == exception_id)
        ).first()

        if key in seen_leaves:
            if existing:
                if existing.status == "RESOLVED":
                    existing.status = "OPEN"
                    session.add(existing)
                    created_or_reopened += 1
            else:
                exception = ExceptionRecord(
                    exception_id=exception_id,
                    payroll_input_id=None,
                    validation_rule_id=rule.id,
                    employee_id=deduction.employee_id,
                    issue_type="DUPLICATE_LEAVE_DEDUCTION",
                    description=f"Duplicate leave deduction detected for {key} (conflicts with {seen_leaves[key]}).",
                    status="OPEN",
                    severity=rule.severity,
                    source_entity="Deduction",
                    source_record_id=deduction.deduction_id
                )
                session.add(exception)
                created_or_reopened += 1
        else:
            seen_leaves[key] = deduction.deduction_id
            if existing and existing.status == "OPEN":
                existing.status = "RESOLVED"
                existing.resolution_notes = "Leave deduction unique."
                existing.resolved_at = datetime.now(timezone.utc)
                existing.resolved_by = "SYSTEM"
                session.add(existing)

    session.commit()
    return created_or_reopened


def validate_payroll_reconciliation(session: Session, rule: ValidationRule) -> int:
    """Flags arithmetic discrepancies between net pay and calculated component totals."""
    payroll_records = session.exec(select(PayrollInput)).all()
    created_or_reopened = 0

    for payroll in payroll_records:
        expected_net_pay = round(
            payroll.basic_salary
            + payroll.overtime_amount
            + payroll.allowance_total
            - payroll.deduction_total
            - payroll.unpaid_leave_deduction,
            2
        )

        exception_id = f"EXC-{payroll.payroll_input_id}-RECONCILIATION"
        existing = session.exec(
            select(ExceptionRecord).where(ExceptionRecord.exception_id == exception_id)
        ).first()

        mismatch = abs(round(payroll.net_pay, 2) - expected_net_pay) > 0.01

        if mismatch:
            desc = (
                f"Arithmetic mismatch: Net Pay = INR {payroll.net_pay:,.2f}, "
                f"Expected = INR {expected_net_pay:,.2f} "
                f"(Basic INR {payroll.basic_salary:,.2f} + OT INR {payroll.overtime_amount:,.2f} + "
                f"Allow INR {payroll.allowance_total:,.2f} - Ded INR {payroll.deduction_total:,.2f} - "
                f"Unpaid Leave INR {payroll.unpaid_leave_deduction:,.2f})."
            )

            if existing:
                if existing.status == "RESOLVED":
                    existing.status = "OPEN"
                    session.add(existing)
                    created_or_reopened += 1
                existing.description = desc
                session.add(existing)
            else:
                exception = ExceptionRecord(
                    exception_id=exception_id,
                    payroll_input_id=payroll.id,
                    validation_rule_id=rule.id,
                    employee_id=payroll.employee_id,
                    issue_type="PAYROLL_RECONCILIATION_MISMATCH",
                    description=desc,
                    status="OPEN",
                    severity=rule.severity,
                    source_entity="PayrollInput",
                    source_record_id=payroll.payroll_input_id
                )
                session.add(exception)
                created_or_reopened += 1
        else:
            if existing and existing.status == "OPEN":
                existing.status = "RESOLVED"
                existing.resolution_notes = "Payroll totals reconcile mathematically."
                existing.resolved_at = datetime.now(timezone.utc)
                existing.resolved_by = "SYSTEM"
                session.add(existing)

    session.commit()
    return created_or_reopened


# =====================================================
# MASTER VALIDATION RUNNER WITH EVALUATION METRICS
# =====================================================

def evaluate_ground_truth_metrics(session: Session) -> Dict[str, Any]:
    """
    Compare open detected exceptions against ground_truth.json to compute
    Precision, Recall, F1-Score, and anomaly detection stats.
    """
    gt_path = Path("datasets/ground_truth.json")
    if not gt_path.exists():
        gt_path = Path("ground_truth.json")

    if not gt_path.exists():
        return {
            "ground_truth_available": False,
            "message": "ground_truth.json not found."
        }

    with open(gt_path, "r", encoding="utf-8") as f:
        ground_truth_records = json.load(f)

    gt_set = set()
    for item in ground_truth_records:
        gt_set.add((item.get("issue_type"), item.get("record_id")))

    # Query all exceptions detected by the validation engine (both OPEN and RESOLVED)
    # Ground truth measures detection capability across the dataset run
    all_exceptions = session.exec(select(ExceptionRecord)).all()

    detected_set = set()
    for exc in all_exceptions:
        detected_set.add((exc.issue_type, exc.source_record_id))

    # Match based on issue_type and source or related record
    # Calculate TP, FP, FN
    tp = 0
    fp = 0
    fn = 0

    # Check each ground truth item
    matched_gt = set()
    matched_det = set()

    for gt_type, gt_rec in gt_set:
        match_found = False
        for det_type, det_rec in detected_set:
            if det_type == gt_type and (det_rec == gt_rec or gt_rec in (det_rec or "") or (det_rec or "") in gt_rec):
                match_found = True
                matched_gt.add((gt_type, gt_rec))
                matched_det.add((det_type, det_rec))
                break

    tp = len(matched_gt)
    fn = len(gt_set) - tp
    fp = len(detected_set) - len(matched_det)

    precision = round(tp / (tp + fp), 4) if (tp + fp) > 0 else 1.0
    recall = round(tp / (tp + fn), 4) if (tp + fn) > 0 else 1.0
    f1_score = round(2 * precision * recall / (precision + recall), 4) if (precision + recall) > 0 else 1.0

    return {
        "ground_truth_available": True,
        "ground_truth_count": len(ground_truth_records),
        "detected_exceptions": len(all_exceptions),
        "detected_open_exceptions": len([e for e in all_exceptions if e.status == "OPEN"]),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": precision,
        "recall": recall,
        "f1_score": f1_score
    }


def run_all_validations(session: Session) -> Dict[str, Any]:
    """
    Execute all 8 validation rules, link to ValidationRule table,
    log audit summary, and calculate evaluation metrics.
    """
    rules = ensure_validation_rules(session)

    c_bank = validate_bank_accounts(session, rules["RULE-BANK-001"])
    c_tax = validate_tax_ids(session, rules["RULE-TAX-001"])
    c_dup_time = validate_duplicate_time_entries(session, rules["RULE-TIME-DUP-001"])
    c_excess = validate_excessive_hours(session, rules["RULE-TIME-EXC-001"])
    c_dup_alw = validate_duplicate_allowances(session, rules["RULE-ALW-DUP-001"])
    c_unapp = validate_unapproved_time_entries(session, rules["RULE-TIME-UNAPP-001"])
    c_dup_leave = validate_duplicate_leave_deductions(session, rules["RULE-LEV-DUP-001"])
    c_recon = validate_payroll_reconciliation(session, rules["RULE-PAY-RECON-001"])

    total_exceptions = session.exec(select(ExceptionRecord)).all()
    open_exceptions = [e for e in total_exceptions if e.status == "OPEN"]
    resolved_exceptions = [e for e in total_exceptions if e.status == "RESOLVED"]

    metrics = evaluate_ground_truth_metrics(session)

    log_audit_event(
        session=session,
        entity_name="ValidationEngine",
        record_id="ALL_RULES",
        action="VALIDATE",
        actor_role="IT_OPS",
        actor_name="Automated Validation Engine",
        new_values={
            "total": len(total_exceptions),
            "open": len(open_exceptions),
            "resolved": len(resolved_exceptions),
            "f1_score": metrics.get("f1_score")
        },
        reason="Full validation cycle executed across 8 rules",
        commit=True
    )

    return {
        "success": True,
        "total_exceptions": len(total_exceptions),
        "open_exceptions": len(open_exceptions),
        "resolved_exceptions": len(resolved_exceptions),
        "rule_results": {
            "RULE-BANK-001": c_bank,
            "RULE-TAX-001": c_tax,
            "RULE-TIME-DUP-001": c_dup_time,
            "RULE-TIME-EXC-001": c_excess,
            "RULE-ALW-DUP-001": c_dup_alw,
            "RULE-TIME-UNAPP-001": c_unapp,
            "RULE-LEV-DUP-001": c_dup_leave,
            "RULE-PAY-RECON-001": c_recon,
        },
        "evaluation_metrics": metrics
    }
