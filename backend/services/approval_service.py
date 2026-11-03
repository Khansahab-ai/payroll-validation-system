from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4

from sqlmodel import Session, select

from backend.models.models import (
    PayrollInput,
    ExceptionRecord,
    Approval,
    PayPeriod,
    TimeEntry,
    Allowance,
    Deduction
)
from backend.services.audit_service import log_audit_event


def exception_belongs_to_payroll(
    session: Session,
    exception: ExceptionRecord,
    payroll: PayrollInput,
    period: PayPeriod
) -> bool:
    """
    Check whether an open exception belongs to this exact employee and pay period.
    """
    if exception.employee_id != payroll.employee_id:
        return False

    # Bank and Tax exceptions affect all payroll periods for this employee
    if exception.issue_type in ["MISSING_BANK_ACCOUNT", "MISSING_TAX_ID"]:
        return True

    # Directly linked to payroll record
    if exception.payroll_input_id is not None:
        return exception.payroll_input_id == payroll.id

    # Unapproved time entries are scoped to pay period
    if exception.issue_type == "UNAPPROVED_TIME_ENTRY":
        return exception.source_record_id == period.period_code or period.period_code in exception.exception_id

    # Excessive hours exception contains the period code
    if exception.issue_type == "EXCESSIVE_WORKING_HOURS":
        return period.period_code in exception.exception_id

    # Duplicate time entry: verify pay period of source entry
    if exception.issue_type == "DUPLICATE_TIME_ENTRY":
        entry = session.exec(
            select(TimeEntry).where(TimeEntry.time_id == exception.source_record_id)
        ).first()
        return entry is not None and entry.pay_period_id == payroll.pay_period_id

    # Duplicate allowance: verify pay period of source allowance
    if exception.issue_type == "DUPLICATE_ALLOWANCE":
        allowance = session.exec(
            select(Allowance).where(Allowance.allowance_id == exception.source_record_id)
        ).first()
        return allowance is not None and allowance.pay_period_id == payroll.pay_period_id

    # Duplicate leave deduction: verify pay period of source deduction
    if exception.issue_type == "DUPLICATE_LEAVE_DEDUCTION":
        deduction = session.exec(
            select(Deduction).where(Deduction.deduction_id == exception.source_record_id)
        ).first()
        return deduction is not None and deduction.pay_period_id == payroll.pay_period_id

    # Reconciliation mismatch is linked to payroll
    if exception.issue_type == "PAYROLL_RECONCILIATION_MISMATCH":
        return exception.payroll_input_id == payroll.id or payroll.payroll_input_id in exception.exception_id

    return True


def process_payroll_approval(
    session: Session,
    payroll_record_id: int,
    approver_name: str,
    approver_role: str,
    decision: str,
    comments: str = ""
) -> Dict[str, Any]:
    """
    Process an approval decision (APPROVED or REJECTED) for a payroll input.
    Enforces governance by strictly blocking approval if any open HIGH severity
    exceptions belong to this employee and pay period.
    """
    payroll = session.get(PayrollInput, payroll_record_id)
    if not payroll:
        return {
            "success": False,
            "message": f"Payroll record ID {payroll_record_id} not found."
        }

    # Normalize decision
    decision_norm = decision.strip().upper()
    if decision_norm in ["APPROVE", "APPROVED"]:
        decision_norm = "APPROVED"
    elif decision_norm in ["REJECT", "REJECTED"]:
        decision_norm = "REJECTED"
    else:
        return {
            "success": False,
            "message": "Decision must be APPROVED or REJECTED."
        }

    period = session.get(PayPeriod, payroll.pay_period_id)
    if not period:
        return {
            "success": False,
            "message": "Pay period not found for this payroll record."
        }

    # If approving, check for blocking open exceptions
    if decision_norm == "APPROVED":
        employee_exceptions = session.exec(
            select(ExceptionRecord).where(
                ExceptionRecord.employee_id == payroll.employee_id,
                ExceptionRecord.status == "OPEN",
                ExceptionRecord.severity == "HIGH"
            )
        ).all()

        blocking_exceptions = [
            exc for exc in employee_exceptions
            if exception_belongs_to_payroll(session, exc, payroll, period)
        ]

        if blocking_exceptions:
            return {
                "success": False,
                "status": "BLOCKED",
                "message": (
                    f"Payroll cannot be approved: {len(blocking_exceptions)} open HIGH-severity "
                    f"exception(s) must be resolved first."
                ),
                "blocking_exceptions": len(blocking_exceptions),
                "exception_ids": [e.exception_id for e in blocking_exceptions],
                "issues": [f"{e.issue_type}: {e.description}" for e in blocking_exceptions]
            }

    # Generate deterministic/standard approval ID
    approval_seq = session.exec(select(Approval)).all()
    approval_id = f"APR-{period.period_code.replace('PP-', '')}-{len(approval_seq) + 1:06d}"

    approval_record = Approval(
        approval_id=approval_id,
        payroll_input_id=payroll.id,
        approver_name=approver_name,
        approver_role=approver_role.upper(),
        decision=decision_norm,
        comments=comments,
        created_at=datetime.now(timezone.utc)
    )
    session.add(approval_record)

    old_status = payroll.status
    payroll.status = decision_norm
    session.add(payroll)
    session.commit()
    session.refresh(payroll)

    log_audit_event(
        session=session,
        entity_name="PayrollInput",
        record_id=payroll.payroll_input_id,
        action="APPROVE" if decision_norm == "APPROVED" else "REJECT",
        actor_role=approver_role,
        actor_name=approver_name,
        old_values={"status": old_status},
        new_values={"status": decision_norm, "approval_id": approval_id},
        reason=comments or f"Payroll {decision_norm.lower()} by {approver_role}",
        commit=True
    )

    return {
        "success": True,
        "payroll_id": payroll.payroll_input_id,
        "decision": decision_norm,
        "approval_id": approval_id,
        "message": f"Payroll {payroll.payroll_input_id} {decision_norm.lower()} successfully."
    }
