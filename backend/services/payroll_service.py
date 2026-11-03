from datetime import datetime, timezone
from typing import Any, Dict, List
from sqlmodel import Session, select

from backend.models.models import (
    Employee,
    PayGroup,
    PayPeriod,
    TimeEntry,
    LeaveRecord,
    Allowance,
    Deduction,
    PayrollInput,
    ExceptionRecord
)
from backend.services.audit_service import log_audit_event


def generate_payroll(session: Session) -> Dict[str, Any]:
    """
    Calculate and aggregate payroll inputs for each employee and pay period
    from source transactions and master data.
    Produces deterministic IDs adhering to PIN-<employee-id>-<period> convention.
    """
    employees = session.exec(select(Employee)).all()
    pay_groups = {g.id: g for g in session.exec(select(PayGroup)).all()}
    pay_periods = session.exec(select(PayPeriod)).all()

    time_entries = session.exec(select(TimeEntry)).all()
    leave_records = session.exec(select(LeaveRecord)).all()
    allowances = session.exec(select(Allowance)).all()
    deductions = session.exec(select(Deduction)).all()

    existing_payroll_map = {
        (p.employee_id, p.pay_period_id): p
        for p in session.exec(select(PayrollInput)).all()
    }

    created_count = 0
    updated_count = 0

    for employee in employees:
        pay_group = pay_groups.get(employee.pay_group_id)
        if not pay_group:
            continue

        standard_hours = pay_group.standard_hours or 160.0

        for period in pay_periods:
            period_suffix = period.period_code.replace("PP-", "")
            payroll_input_id = f"PIN-{employee.employee_id}-{period_suffix}"

            # 1. Approved Time & Overtime Calculation
            emp_time = [
                e for e in time_entries
                if e.employee_id == employee.id
                and e.pay_period_id == period.id
                and e.approval_status == "APPROVED"
            ]
            total_approved_hours = sum(e.hours_worked for e in emp_time)

            overtime_hours = max(0.0, total_approved_hours - standard_hours)
            hourly_rate = employee.basic_salary / standard_hours
            overtime_amount = round(overtime_hours * hourly_rate * 1.5, 2)

            # 2. Allowances
            emp_allowances = [
                a for a in allowances
                if a.employee_id == employee.id
                and a.pay_period_id == period.id
                and not a.reference_code.startswith("DUPLICATE-VOID")
            ]
            allowance_total = round(sum(a.amount for a in emp_allowances), 2)

            # 3. Deductions (Statutory & Voluntary, excluding leave deductions)
            emp_deductions = [
                d for d in deductions
                if d.employee_id == employee.id
                and d.pay_period_id == period.id
                and d.deduction_type != "UNPAID_LEAVE"
                and not d.reference_code.startswith("DUPLICATE-VOID")
            ]
            deduction_total = round(sum(d.amount for a in emp_deductions for d in [a]), 2)

            # 4. Unpaid Leave Deductions
            emp_leave_deductions = [
                d for d in deductions
                if d.employee_id == employee.id
                and d.pay_period_id == period.id
                and d.deduction_type == "UNPAID_LEAVE"
                and not d.reference_code.startswith("DUPLICATE-VOID")
            ]
            if emp_leave_deductions:
                unpaid_leave_deduction = round(sum(d.amount for d in emp_leave_deductions), 2)
            else:
                emp_unpaid_leaves = [
                    l for l in leave_records
                    if l.employee_id == employee.id
                    and l.pay_period_id == period.id
                    and l.is_unpaid
                    and l.approval_status == "APPROVED"
                ]
                unpaid_days = sum(l.days for l in emp_unpaid_leaves)
                unpaid_leave_deduction = round(unpaid_days * (employee.basic_salary / 30.0), 2)

            # 5. Net Pay
            net_pay = round(
                employee.basic_salary
                + overtime_amount
                + allowance_total
                - deduction_total
                - unpaid_leave_deduction,
                2
            )

            existing = existing_payroll_map.get((employee.id, period.id))

            if existing:
                # Preserve open planted reconciliation exceptions until explicitly resolved
                open_recon_exc = session.exec(
                    select(ExceptionRecord).where(
                        ExceptionRecord.payroll_input_id == existing.id,
                        ExceptionRecord.issue_type == "PAYROLL_RECONCILIATION_MISMATCH",
                        ExceptionRecord.status == "OPEN"
                    )
                ).first()

                existing.basic_salary = employee.basic_salary
                existing.overtime_amount = overtime_amount
                existing.allowance_total = allowance_total
                existing.deduction_total = deduction_total
                existing.unpaid_leave_deduction = unpaid_leave_deduction
                if not open_recon_exc:
                    existing.net_pay = net_pay
                session.add(existing)
                updated_count += 1
            else:
                payroll = PayrollInput(
                    payroll_input_id=payroll_input_id,
                    employee_id=employee.id,
                    pay_period_id=period.id,
                    basic_salary=employee.basic_salary,
                    overtime_amount=overtime_amount,
                    allowance_total=allowance_total,
                    deduction_total=deduction_total,
                    unpaid_leave_deduction=unpaid_leave_deduction,
                    net_pay=net_pay,
                    status="DRAFT"
                )
                session.add(payroll)
                created_count += 1

    session.commit()

    log_audit_event(
        session=session,
        entity_name="PayrollInput",
        record_id="ALL_PERIODS",
        action="CALCULATE",
        actor_role="SYSTEM",
        actor_name="Automated Payroll Calculator",
        new_values={"created": created_count, "updated": updated_count},
        reason="Aggregated approved inputs and source transactions",
        commit=True
    )

    return {
        "success": True,
        "created_records": created_count,
        "updated_records": updated_count,
        "message": f"Generated {created_count} new payroll inputs, updated {updated_count} existing."
    }
