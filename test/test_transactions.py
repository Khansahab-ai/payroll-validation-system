import pytest
from sqlmodel import Session, select

from backend.database import engine
from backend.models.models import (
    TimeEntry,
    LeaveRecord,
    Allowance,
    Deduction,
    Employee,
    PayPeriod
)


def test_time_entry_nomenclature_and_fks():
    with Session(engine) as session:
        entries = session.exec(select(TimeEntry)).all()
        assert len(entries) > 1000
        emp_ids = {e.id for e in session.exec(select(Employee)).all()}
        period_ids = {p.id for p in session.exec(select(PayPeriod)).all()}

        for entry in entries[:100]:
            # TIME-<employee-id>-<date>
            assert entry.time_id.startswith("TIME-EMP-")
            assert entry.employee_id in emp_ids
            assert entry.pay_period_id in period_ids
            assert entry.hours_worked >= 0
            assert entry.approval_status in ["APPROVED", "PENDING", "REJECTED"]


def test_leave_records():
    with Session(engine) as session:
        leaves = session.exec(select(LeaveRecord)).all()
        assert len(leaves) > 0
        for l in leaves:
            assert l.leave_id.startswith("LEV-EMP-")
            assert l.days > 0
            assert l.leave_type in ["ANNUAL", "SICK", "CASUAL", "UNPAID"]


def test_allowance_and_deduction_fks():
    with Session(engine) as session:
        allowances = session.exec(select(Allowance)).all()
        deductions = session.exec(select(Deduction)).all()
        assert len(allowances) > 100
        assert len(deductions) > 100

        for a in allowances[:50]:
            assert a.allowance_id.startswith("ALW-EMP-")
            assert a.amount >= 0

        for d in deductions[:50]:
            assert d.deduction_id.startswith("DED-EMP-")
            assert d.amount >= 0

