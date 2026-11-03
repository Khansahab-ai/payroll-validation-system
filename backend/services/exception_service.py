from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlmodel import Session, select

from backend.models.models import (
    Employee,
    PayGroup,
    PayPeriod,
    TimeEntry,
    Allowance,
    Deduction,
    PayrollInput,
    ExceptionRecord
)
from backend.services.audit_service import log_audit_event


def get_open_exceptions(session: Session) -> List[ExceptionRecord]:
    """Retrieve all open exceptions."""
    return session.exec(
        select(ExceptionRecord).where(ExceptionRecord.status == "OPEN")
    ).all()


def check_exception_is_fixed(session: Session, exception: ExceptionRecord) -> bool:
    """
    Verify whether the underlying source data problem has been corrected
    before permitting resolution of the exception.
    """
    issue_type = exception.issue_type

    # 1. Missing bank account
    if issue_type == "MISSING_BANK_ACCOUNT":
        employee = session.get(Employee, exception.employee_id)
        return bool(employee and employee.bank_account and employee.bank_account.strip() != "")

    # 2. Missing tax ID
    if issue_type == "MISSING_TAX_ID":
        employee = session.get(Employee, exception.employee_id)
        return bool(employee and employee.tax_id and employee.tax_id.strip() != "")

    # 3. Duplicate time entry
    if issue_type == "DUPLICATE_TIME_ENTRY":
        entry = session.exec(
            select(TimeEntry).where(TimeEntry.time_id == exception.source_record_id)
        ).first()
        if not entry or entry.approval_status == "REJECTED" or entry.hours_worked == 0:
            return True

        matching = session.exec(
            select(TimeEntry).where(
                TimeEntry.submission_ref == entry.submission_ref,
                TimeEntry.approval_status != "REJECTED",
                TimeEntry.hours_worked > 0
            )
        ).all()
        return len(matching) <= 1

    # 4. Excessive working hours
    if issue_type == "EXCESSIVE_WORKING_HOURS":
        employee = session.get(Employee, exception.employee_id)
        if not employee:
            return False
        pay_group = session.get(PayGroup, employee.pay_group_id)
        if not pay_group:
            return False

        periods = session.exec(select(PayPeriod)).all()
        period = next((p for p in periods if p.period_code in exception.exception_id), None)
        if not period:
            return False

        entries = session.exec(
            select(TimeEntry).where(
                TimeEntry.employee_id == employee.id,
                TimeEntry.pay_period_id == period.id,
                TimeEntry.approval_status == "APPROVED"
            )
        ).all()
        total_hours = sum(e.hours_worked for e in entries)
        has_outlier = any(e.hours_worked > 16.0 for e in entries)

        return (total_hours <= pay_group.max_period_hours) and not has_outlier

    # 5. Duplicate allowance
    if issue_type == "DUPLICATE_ALLOWANCE":
        allowance = session.exec(
            select(Allowance).where(Allowance.allowance_id == exception.source_record_id)
        ).first()
        if not allowance or allowance.amount == 0 or allowance.reference_code.startswith("DUPLICATE-VOID"):
            return True

        matching = session.exec(
            select(Allowance).where(
                Allowance.reference_code == allowance.reference_code,
                Allowance.amount > 0,
                ~Allowance.reference_code.startswith("DUPLICATE-VOID")
            )
        ).all()
        return len(matching) <= 1

    # 6. Unapproved time entries
    if issue_type == "UNAPPROVED_TIME_ENTRY":
        periods = session.exec(select(PayPeriod)).all()
        period = next((p for p in periods if p.period_code == exception.source_record_id or p.period_code in exception.exception_id), None)
        if not period:
            return False

        pending = session.exec(
            select(TimeEntry).where(
                TimeEntry.employee_id == exception.employee_id,
                TimeEntry.pay_period_id == period.id,
                TimeEntry.approval_status == "PENDING"
            )
        ).all()
        return len(pending) == 0

    # 7. Duplicate leave deduction
    if issue_type == "DUPLICATE_LEAVE_DEDUCTION":
        deduction = session.exec(
            select(Deduction).where(Deduction.deduction_id == exception.source_record_id)
        ).first()
        if not deduction or deduction.amount == 0 or deduction.reference_code.startswith("DUPLICATE-VOID"):
            return True

        key = deduction.leave_record_id if deduction.leave_record_id else deduction.reference_code
        matching = session.exec(
            select(Deduction).where(
                Deduction.deduction_type == "UNPAID_LEAVE",
                Deduction.amount > 0,
                ~Deduction.reference_code.startswith("DUPLICATE-VOID")
            )
        ).all()
        matching_count = sum(
            1 for d in matching
            if (d.leave_record_id == key if deduction.leave_record_id else d.reference_code == key)
        )
        return matching_count <= 1

    # 8. Payroll reconciliation
    if issue_type == "PAYROLL_RECONCILIATION_MISMATCH":
        payroll = session.get(PayrollInput, exception.payroll_input_id)
        if not payroll:
            return False

        expected = round(
            payroll.basic_salary
            + payroll.overtime_amount
            + payroll.allowance_total
            - payroll.deduction_total
            - payroll.unpaid_leave_deduction,
            2
        )
        return abs(round(payroll.net_pay, 2) - expected) <= 0.01

    return False


def resolve_exception(
    session: Session,
    exception_id: str,
    resolution_comments: str,
    actor_name: str = "HR Partner",
    actor_role: str = "HR"
) -> Dict[str, Any]:
    """
    Attempt to resolve an exception. Requires that the underlying source problem
    has been corrected, adds resolution notes, and records an audit log.
    """
    exception = session.exec(
        select(ExceptionRecord).where(ExceptionRecord.exception_id == exception_id)
    ).first()

    if not exception:
        return {"success": False, "message": f"Exception {exception_id} not found."}

    if exception.status != "OPEN":
        return {"success": False, "message": f"Exception {exception_id} is already resolved."}

    if not resolution_comments or not resolution_comments.strip():
        return {"success": False, "message": "Resolution comments are required."}

    # Verify underlying cause is resolved
    is_fixed = check_exception_is_fixed(session, exception)
    if not is_fixed:
        return {
            "success": False,
            "status": "OPEN",
            "message": (
                f"Cannot resolve exception: the root issue ({exception.issue_type}) still exists in source data. "
                f"Please correct the employee, time entry, allowance, or payroll record first."
            )
        }

    exception.status = "RESOLVED"
    exception.resolution_notes = resolution_comments.strip()
    exception.resolved_by = actor_name
    exception.resolved_at = datetime.now(timezone.utc)

    session.add(exception)
    session.commit()
    session.refresh(exception)

    log_audit_event(
        session=session,
        entity_name="ExceptionRecord",
        record_id=exception.exception_id,
        action="RESOLVE",
        actor_role=actor_role,
        actor_name=actor_name,
        old_values={"status": "OPEN"},
        new_values={"status": "RESOLVED", "notes": resolution_comments},
        reason=resolution_comments,
        commit=True
    )

    return {
        "success": True,
        "exception_id": exception.exception_id,
        "status": "RESOLVED",
        "message": f"Exception {exception.exception_id} successfully verified and resolved."
    }
