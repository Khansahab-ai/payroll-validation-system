import pytest
from sqlmodel import Session, select

from backend.database import engine
from backend.models.models import PayrollInput, Employee, PayPeriod


def test_payroll_input_nomenclature():
    with Session(engine) as session:
        payrolls = session.exec(select(PayrollInput)).all()
        assert len(payrolls) > 0
        for p in payrolls:
            # PIN-<employee-id>-2026-01
            assert p.payroll_input_id.startswith("PIN-EMP-")
            assert "-2026-" in p.payroll_input_id
            assert p.basic_salary > 0
            assert p.status in ["DRAFT", "PENDING", "APPROVED", "REJECTED", "EXPORTED"]


def test_payroll_arithmetic_formula():
    with Session(engine) as session:
        payrolls = session.exec(select(PayrollInput)).all()
        reconciled_count = 0
        mismatch_count = 0

        for p in payrolls:
            expected = round(
                p.basic_salary
                + p.overtime_amount
                + p.allowance_total
                - p.deduction_total
                - p.unpaid_leave_deduction,
                2
            )
            if abs(round(p.net_pay, 2) - expected) <= 0.01:
                reconciled_count += 1
            else:
                mismatch_count += 1

        # The vast majority are reconciled; only planted mismatch anomaly fails
        assert reconciled_count > 100
        assert mismatch_count >= 1

