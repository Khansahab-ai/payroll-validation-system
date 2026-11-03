import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from sqlmodel import Session, select

from backend.models.models import (
    PayrollInput,
    ExceptionRecord,
    PayrollExport,
    PayPeriod
)
from backend.services.approval_service import exception_belongs_to_payroll
from backend.services.audit_service import log_audit_event


def export_approved_payroll(
    session: Session,
    pay_period_id: int,
    actor_name: str = "System Administrator",
    actor_role: str = "SYSTEM"
) -> Dict[str, Any]:
    """
    Export only approved payroll records for the given pay period where no
    open HIGH-severity exceptions exist.
    Outputs to CSV with deterministic PEX-YYYY-XXXXXX identifiers and
    updates status to EXPORTED.
    """
    period = session.get(PayPeriod, pay_period_id)
    if not period:
        return {
            "success": False,
            "message": f"Pay period ID {pay_period_id} not found."
        }

    # 1. Fetch approved payroll records
    payroll_records = session.exec(
        select(PayrollInput).where(
            PayrollInput.pay_period_id == pay_period_id,
            PayrollInput.status == "APPROVED"
        )
    ).all()

    if not payroll_records:
        return {
            "success": False,
            "message": f"No approved payroll records found for pay period {period.period_code}. Approve records first."
        }

    # 2. Strict governance: verify no blocking exceptions for this period
    eligible_records: List[PayrollInput] = []
    blocked_count = 0

    for payroll in payroll_records:
        employee_exceptions = session.exec(
            select(ExceptionRecord).where(
                ExceptionRecord.employee_id == payroll.employee_id,
                ExceptionRecord.status == "OPEN",
                ExceptionRecord.severity == "HIGH"
            )
        ).all()

        blocking = [
            exc for exc in employee_exceptions
            if exception_belongs_to_payroll(session, exc, payroll, period)
        ]

        if not blocking:
            eligible_records.append(payroll)
        else:
            blocked_count += 1

    if not eligible_records:
        return {
            "success": False,
            "message": f"All {blocked_count} approved records are blocked by open exceptions in {period.period_code}."
        }

    # 3. Deterministic export ID: PEX-YYYY-XXXXXX
    existing_exports = session.exec(select(PayrollExport)).all()
    year = period.period_code.split("-")[1] if "-" in period.period_code else "2026"
    export_id = f"PEX-{year}-{len(existing_exports) + 1:06d}"

    # 4. Prepare export files in export and exports directories
    export_dirs = [Path("export"), Path("exports")]
    for ed in export_dirs:
        ed.mkdir(exist_ok=True)

    file_name = f"payroll_export_{period.period_code}_{export_id}.csv"

    columns = [
        "payroll_input_id",
        "employee_id",
        "pay_period_code",
        "basic_salary",
        "overtime_amount",
        "allowance_total",
        "deduction_total",
        "unpaid_leave_deduction",
        "net_pay",
        "export_id",
        "export_timestamp"
    ]

    export_timestamp_str = datetime.now(timezone.utc).isoformat()

    for ed in export_dirs:
        file_path = ed / file_name
        with open(file_path, "w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=columns)
            writer.writeheader()
            for payroll in eligible_records:
                writer.writerow({
                    "payroll_input_id": payroll.payroll_input_id,
                    "employee_id": payroll.employee_id,
                    "pay_period_code": period.period_code,
                    "basic_salary": payroll.basic_salary,
                    "overtime_amount": payroll.overtime_amount,
                    "allowance_total": payroll.allowance_total,
                    "deduction_total": payroll.deduction_total,
                    "unpaid_leave_deduction": payroll.unpaid_leave_deduction,
                    "net_pay": payroll.net_pay,
                    "export_id": export_id,
                    "export_timestamp": export_timestamp_str
                })

    # 5. Persist export history
    total_amount = round(sum(p.net_pay for p in eligible_records), 2)

    export_record = PayrollExport(
        export_id=export_id,
        pay_period_id=pay_period_id,
        file_name=file_name,
        file_format="CSV",
        record_count=len(eligible_records),
        total_amount=total_amount,
        export_status="COMPLETED",
        exported_by=actor_name,
        exported_at=datetime.now(timezone.utc)
    )
    session.add(export_record)

    # 6. Update exported payroll status to preserve state transition
    for payroll in eligible_records:
        payroll.status = "EXPORTED"
        session.add(payroll)

    session.commit()

    log_audit_event(
        session=session,
        entity_name="PayrollExport",
        record_id=export_id,
        action="EXPORT",
        actor_role=actor_role,
        actor_name=actor_name,
        new_values={
            "period": period.period_code,
            "record_count": len(eligible_records),
            "total_amount": total_amount,
            "file_name": file_name
        },
        reason="Official payroll CSV exported",
        commit=True
    )

    return {
        "success": True,
        "export_id": export_id,
        "file_name": file_name,
        "record_count": len(eligible_records),
        "total_amount": total_amount,
        "blocked_records": blocked_count,
        "message": f"Successfully exported {len(eligible_records)} records to {file_name} under {export_id}."
    }
