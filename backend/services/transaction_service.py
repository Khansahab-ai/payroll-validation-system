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
    LeaveRecord
)
from backend.services.audit_service import log_audit_event


def recalculate_payroll_record(
    session: Session,
    employee_id: int,
    pay_period_id: int,
    commit: bool = True,
    actor_name: str = "SYSTEM",
    actor_role: str = "SYSTEM"
) -> Dict[str, Any]:
    """
    Recalculate an existing payroll record from approved inputs and source transactions.
    Resets status to PENDING/DRAFT if previously approved, requiring re-approval.
    """
    payroll = session.exec(
        select(PayrollInput).where(
            PayrollInput.employee_id == employee_id,
            PayrollInput.pay_period_id == pay_period_id
        )
    ).first()

    if not payroll:
        return {"success": False, "message": "Payroll record not found."}

    employee = session.get(Employee, employee_id)
    if not employee:
        return {"success": False, "message": "Employee not found."}

    pay_group = session.get(PayGroup, employee.pay_group_id)
    standard_hours = pay_group.standard_hours if pay_group else 160.0

    # 1. Total Approved Hours & Overtime
    approved_entries = session.exec(
        select(TimeEntry).where(
            TimeEntry.employee_id == employee_id,
            TimeEntry.pay_period_id == pay_period_id,
            TimeEntry.approval_status == "APPROVED"
        )
    ).all()
    total_approved_hours = sum(e.hours_worked for e in approved_entries)

    overtime_hours = max(0.0, total_approved_hours - standard_hours)
    hourly_rate = employee.basic_salary / standard_hours
    overtime_amount = round(overtime_hours * hourly_rate * 1.5, 2)

    # 2. Allowances
    allowances = session.exec(
        select(Allowance).where(
            Allowance.employee_id == employee_id,
            Allowance.pay_period_id == pay_period_id,
            ~Allowance.reference_code.startswith("DUPLICATE-VOID")
        )
    ).all()
    allowance_total = round(sum(a.amount for a in allowances), 2)

    # 3. Deductions
    deductions = session.exec(
        select(Deduction).where(
            Deduction.employee_id == employee_id,
            Deduction.pay_period_id == pay_period_id,
            Deduction.deduction_type != "UNPAID_LEAVE",
            ~Deduction.reference_code.startswith("DUPLICATE-VOID")
        )
    ).all()
    deduction_total = round(sum(d.amount for d in deductions), 2)

    # 4. Unpaid Leave Deductions
    leave_deductions = session.exec(
        select(Deduction).where(
            Deduction.employee_id == employee_id,
            Deduction.pay_period_id == pay_period_id,
            Deduction.deduction_type == "UNPAID_LEAVE",
            ~Deduction.reference_code.startswith("DUPLICATE-VOID")
        )
    ).all()
    if leave_deductions:
        unpaid_leave_deduction = round(sum(d.amount for d in leave_deductions), 2)
    else:
        unpaid_leaves = session.exec(
            select(LeaveRecord).where(
                LeaveRecord.employee_id == employee_id,
                LeaveRecord.pay_period_id == pay_period_id,
                LeaveRecord.is_unpaid == True,
                LeaveRecord.approval_status == "APPROVED"
            )
        ).all()
        unpaid_days = sum(l.days for l in unpaid_leaves)
        unpaid_leave_deduction = round(unpaid_days * (employee.basic_salary / 30.0), 2)

    net_pay = round(
        employee.basic_salary
        + overtime_amount
        + allowance_total
        - deduction_total
        - unpaid_leave_deduction,
        2
    )

    old_net = payroll.net_pay
    old_status = payroll.status

    payroll.basic_salary = employee.basic_salary
    payroll.overtime_amount = overtime_amount
    payroll.allowance_total = allowance_total
    payroll.deduction_total = deduction_total
    payroll.unpaid_leave_deduction = unpaid_leave_deduction
    payroll.net_pay = net_pay

    # Any change invalidates an existing approval
    if payroll.status in ["APPROVED", "EXPORTED"]:
        payroll.status = "PENDING"

    session.add(payroll)

    if commit:
        session.commit()
        session.refresh(payroll)
    else:
        session.flush()

    log_audit_event(
        session=session,
        entity_name="PayrollInput",
        record_id=payroll.payroll_input_id,
        action="RECALCULATE",
        actor_role=actor_role,
        actor_name=actor_name,
        old_values={"net_pay": old_net, "status": old_status},
        new_values={"net_pay": net_pay, "status": payroll.status},
        reason="Recalculated from updated source inputs",
        commit=commit
    )

    return {
        "success": True,
        "payroll_input_id": payroll.payroll_input_id,
        "total_approved_hours": total_approved_hours,
        "overtime_amount": overtime_amount,
        "allowance_total": allowance_total,
        "deduction_total": deduction_total,
        "unpaid_leave_deduction": unpaid_leave_deduction,
        "net_pay": net_pay,
        "status": payroll.status
    }


def update_time_entry(
    session: Session,
    time_id: str,
    hours_worked: Optional[float] = None,
    approval_status: Optional[str] = None,
    submission_ref: Optional[str] = None,
    actor_name: str = "Manager",
    actor_role: str = "MANAGER",
    reason: str = "Time entry correction"
) -> Dict[str, Any]:
    """Update hours, status, or submission reference on a time entry with audit logging."""
    entry = session.exec(select(TimeEntry).where(TimeEntry.time_id == time_id)).first()
    if not entry:
        return {"success": False, "message": f"Time entry {time_id} not found."}

    old_values = {
        "hours_worked": entry.hours_worked,
        "approval_status": entry.approval_status,
        "submission_ref": entry.submission_ref
    }

    if hours_worked is not None:
        if hours_worked < 0 or hours_worked > 24:
            return {"success": False, "message": "Hours worked must be between 0 and 24."}
        entry.hours_worked = float(hours_worked)

    if approval_status is not None:
        stat_norm = approval_status.strip().upper()
        if stat_norm not in ["PENDING", "APPROVED", "REJECTED"]:
            return {"success": False, "message": "Invalid status. Use PENDING, APPROVED, or REJECTED."}
        entry.approval_status = stat_norm

    if submission_ref is not None:
        entry.submission_ref = submission_ref.strip()

    session.add(entry)
    session.commit()
    session.refresh(entry)

    log_audit_event(
        session=session,
        entity_name="TimeEntry",
        record_id=entry.time_id,
        action="UPDATE",
        actor_role=actor_role,
        actor_name=actor_name,
        old_values=old_values,
        new_values={
            "hours_worked": entry.hours_worked,
            "approval_status": entry.approval_status,
            "submission_ref": entry.submission_ref
        },
        reason=reason,
        commit=True
    )

    recalculation = recalculate_payroll_record(
        session, entry.employee_id, entry.pay_period_id, commit=True, actor_name=actor_name, actor_role=actor_role
    )

    return {
        "success": True,
        "message": f"Time entry {entry.time_id} updated.",
        "time_id": entry.time_id,
        "hours_worked": entry.hours_worked,
        "approval_status": entry.approval_status,
        "payroll_recalculation": recalculation
    }


def mark_duplicate_time_entry(
    session: Session,
    time_id: str,
    actor_name: str = "HR Partner",
    actor_role: str = "HR"
) -> Dict[str, Any]:
    """Void duplicate time entry while preserving record in database for auditability."""
    entry = session.exec(select(TimeEntry).where(TimeEntry.time_id == time_id)).first()
    if not entry:
        return {"success": False, "message": f"Time entry {time_id} not found."}

    old_values = {
        "hours_worked": entry.hours_worked,
        "approval_status": entry.approval_status,
        "submission_ref": entry.submission_ref
    }

    entry.hours_worked = 0.0
    entry.approval_status = "REJECTED"
    entry.submission_ref = f"DUPLICATE-VOID-{entry.time_id}"

    session.add(entry)
    session.commit()
    session.refresh(entry)

    log_audit_event(
        session=session,
        entity_name="TimeEntry",
        record_id=entry.time_id,
        action="DUPLICATE_VOID",
        actor_role=actor_role,
        actor_name=actor_name,
        old_values=old_values,
        new_values={"hours_worked": 0.0, "approval_status": "REJECTED", "submission_ref": entry.submission_ref},
        reason="Duplicate time entry voided and rejected",
        commit=True
    )

    recalculation = recalculate_payroll_record(
        session, entry.employee_id, entry.pay_period_id, commit=True, actor_name=actor_name, actor_role=actor_role
    )

    return {
        "success": True,
        "message": f"Duplicate time entry {entry.time_id} marked as rejected and retained.",
        "time_id": entry.time_id,
        "payroll_recalculation": recalculation
    }


def bulk_approve_pending_time_entries(
    session: Session,
    employee_id: Optional[int] = None,
    pay_period_id: Optional[int] = None,
    actor_name: str = "Manager",
    actor_role: str = "MANAGER"
) -> Dict[str, Any]:
    """Approve all pending time entries for an employee and/or pay period."""
    query = select(TimeEntry).where(TimeEntry.approval_status == "PENDING")
    if employee_id is not None:
        query = query.where(TimeEntry.employee_id == employee_id)
    if pay_period_id is not None:
        query = query.where(TimeEntry.pay_period_id == pay_period_id)

    pending_entries = session.exec(query).all()
    count = 0
    affected_pairs = set()

    for entry in pending_entries:
        entry.approval_status = "APPROVED"
        session.add(entry)
        count += 1
        affected_pairs.add((entry.employee_id, entry.pay_period_id))

    session.commit()

    for emp_id, period_id in affected_pairs:
        recalculate_payroll_record(session, emp_id, period_id, commit=True, actor_name=actor_name, actor_role=actor_role)

    log_audit_event(
        session=session,
        entity_name="TimeEntry",
        record_id=f"BULK_{employee_id}_{pay_period_id}",
        action="BULK_APPROVE",
        actor_role=actor_role,
        actor_name=actor_name,
        new_values={"approved_count": count},
        reason="Manager approved pending time entries",
        commit=True
    )

    return {
        "success": True,
        "approved_count": count,
        "message": f"Approved {count} pending time entries."
    }


def update_allowance(
    session: Session,
    allowance_id: str,
    amount: Optional[float] = None,
    reference_code: Optional[str] = None,
    allowance_type: Optional[str] = None,
    actor_name: str = "HR Partner",
    actor_role: str = "HR",
    reason: str = "Allowance correction"
) -> Dict[str, Any]:
    """Correct an allowance record."""
    allowance = session.exec(select(Allowance).where(Allowance.allowance_id == allowance_id)).first()
    if not allowance:
        return {"success": False, "message": f"Allowance {allowance_id} not found."}

    old_values = {
        "amount": allowance.amount,
        "reference_code": allowance.reference_code,
        "allowance_type": allowance.allowance_type
    }

    if amount is not None:
        if amount < 0:
            return {"success": False, "message": "Allowance amount cannot be negative."}
        allowance.amount = float(amount)
    if reference_code is not None:
        allowance.reference_code = reference_code.strip()
    if allowance_type is not None:
        allowance.allowance_type = allowance_type.strip()

    session.add(allowance)
    session.commit()
    session.refresh(allowance)

    log_audit_event(
        session=session,
        entity_name="Allowance",
        record_id=allowance.allowance_id,
        action="UPDATE",
        actor_role=actor_role,
        actor_name=actor_name,
        old_values=old_values,
        new_values={
            "amount": allowance.amount,
            "reference_code": allowance.reference_code,
            "allowance_type": allowance.allowance_type
        },
        reason=reason,
        commit=True
    )

    recalculation = recalculate_payroll_record(
        session, allowance.employee_id, allowance.pay_period_id, commit=True, actor_name=actor_name, actor_role=actor_role
    )

    return {
        "success": True,
        "message": f"Allowance {allowance.allowance_id} updated.",
        "allowance_id": allowance.allowance_id,
        "amount": allowance.amount,
        "payroll_recalculation": recalculation
    }


def mark_duplicate_allowance(
    session: Session,
    allowance_id: str,
    actor_name: str = "HR Partner",
    actor_role: str = "HR"
) -> Dict[str, Any]:
    """Void duplicate allowance by zeroing amount and updating reference."""
    allowance = session.exec(select(Allowance).where(Allowance.allowance_id == allowance_id)).first()
    if not allowance:
        return {"success": False, "message": f"Allowance {allowance_id} not found."}

    old_values = {"amount": allowance.amount, "reference_code": allowance.reference_code}

    allowance.amount = 0.0
    allowance.reference_code = f"DUPLICATE-VOID-{allowance.allowance_id}"

    session.add(allowance)
    session.commit()
    session.refresh(allowance)

    log_audit_event(
        session=session,
        entity_name="Allowance",
        record_id=allowance.allowance_id,
        action="DUPLICATE_VOID",
        actor_role=actor_role,
        actor_name=actor_name,
        old_values=old_values,
        new_values={"amount": 0.0, "reference_code": allowance.reference_code},
        reason="Duplicate allowance voided",
        commit=True
    )

    recalculation = recalculate_payroll_record(
        session, allowance.employee_id, allowance.pay_period_id, commit=True, actor_name=actor_name, actor_role=actor_role
    )

    return {
        "success": True,
        "message": f"Duplicate allowance {allowance.allowance_id} voided and retained.",
        "payroll_recalculation": recalculation
    }


def mark_duplicate_leave_deduction(
    session: Session,
    deduction_id: str,
    actor_name: str = "HR Partner",
    actor_role: str = "HR"
) -> Dict[str, Any]:
    """Void duplicate unpaid leave deduction."""
    deduction = session.exec(select(Deduction).where(Deduction.deduction_id == deduction_id)).first()
    if not deduction:
        return {"success": False, "message": f"Deduction {deduction_id} not found."}

    old_values = {"amount": deduction.amount, "reference_code": deduction.reference_code}

    deduction.amount = 0.0
    deduction.reference_code = f"DUPLICATE-VOID-{deduction.deduction_id}"

    session.add(deduction)
    session.commit()
    session.refresh(deduction)

    log_audit_event(
        session=session,
        entity_name="Deduction",
        record_id=deduction.deduction_id,
        action="DUPLICATE_VOID",
        actor_role=actor_role,
        actor_name=actor_name,
        old_values=old_values,
        new_values={"amount": 0.0, "reference_code": deduction.reference_code},
        reason="Duplicate leave deduction voided",
        commit=True
    )

    recalculation = recalculate_payroll_record(
        session, deduction.employee_id, deduction.pay_period_id, commit=True, actor_name=actor_name, actor_role=actor_role
    )

    return {
        "success": True,
        "message": f"Duplicate leave deduction {deduction.deduction_id} voided and retained.",
        "payroll_recalculation": recalculation
    }


def reconcile_payroll_record(
    session: Session,
    payroll_input_id: str,
    actor_name: str = "HR Partner",
    actor_role: str = "HR"
) -> Dict[str, Any]:
    """Recalculate and reconcile a payroll record with an arithmetic mismatch."""
    payroll = session.exec(select(PayrollInput).where(PayrollInput.payroll_input_id == payroll_input_id)).first()
    if not payroll:
        return {"success": False, "message": f"Payroll record {payroll_input_id} not found."}

    return recalculate_payroll_record(
        session, payroll.employee_id, payroll.pay_period_id, commit=True, actor_name=actor_name, actor_role=actor_role
    )
