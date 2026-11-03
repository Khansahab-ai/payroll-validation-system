import pytest
from sqlmodel import Session, select

from backend.database import engine
from backend.models.models import PayrollInput, Employee, ExceptionRecord
from backend.services.approval_service import process_payroll_approval
from backend.services.payroll_export_service import export_approved_payroll


def test_approval_blocked_on_open_exceptions():
    with Session(engine) as session:
        # Find an employee who has an open exception in Period 1
        exc = session.exec(
            select(ExceptionRecord).where(
                ExceptionRecord.status == "OPEN",
                ExceptionRecord.issue_type == "DUPLICATE_TIME_ENTRY"
            )
        ).first()

        assert exc is not None
        payroll = session.exec(
            select(PayrollInput).where(
                PayrollInput.employee_id == exc.employee_id,
                PayrollInput.pay_period_id == 1
            )
        ).first()

        assert payroll is not None
        res = process_payroll_approval(
            session=session,
            payroll_record_id=payroll.id,
            approver_name="HR Manager",
            approver_role="HR",
            decision="APPROVED"
        )

        assert res["success"] is False
        assert res["status"] == "BLOCKED"
        assert res["blocking_exceptions"] > 0
        assert len(res["exception_ids"]) > 0


def test_clean_payroll_approval_and_export():
    with Session(engine) as session:
        # Find an employee without any open exceptions
        all_exc_emp_ids = {
            e.employee_id for e in session.exec(
                select(ExceptionRecord).where(ExceptionRecord.status == "OPEN")
            ).all()
        }

        clean_payroll = session.exec(
            select(PayrollInput).where(
                PayrollInput.pay_period_id == 2,
                ~PayrollInput.employee_id.in_(all_exc_emp_ids)
            )
        ).first()

        assert clean_payroll is not None

        # 1. Approval succeeds
        app_res = process_payroll_approval(
            session=session,
            payroll_record_id=clean_payroll.id,
            approver_name="HR Manager",
            approver_role="HR",
            decision="APPROVED",
            comments="Clean period 2 verified"
        )
        assert app_res["success"] is True
        assert app_res["decision"] == "APPROVED"
        assert app_res["approval_id"].startswith("APR-")

        # 2. Export succeeds for period 2
        exp_res = export_approved_payroll(session=session, pay_period_id=2)
        assert exp_res["success"] is True
        assert exp_res["export_id"].startswith("PEX-")
        assert exp_res["record_count"] >= 1
