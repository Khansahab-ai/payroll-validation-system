import pytest
from sqlmodel import Session, select

from backend.database import engine
from backend.models.models import (
    Employee,
    PayGroup,
    PayPeriod,
    EmployeeAllowanceEligibility
)


def test_pay_groups_created():
    with Session(engine) as session:
        groups = session.exec(select(PayGroup)).all()
        assert len(groups) == 3
        codes = {g.group_code for g in groups}
        assert codes == {"PG-001", "PG-002", "PG-003"}


def test_pay_periods_created():
    with Session(engine) as session:
        periods = session.exec(select(PayPeriod)).all()
        assert len(periods) == 3
        codes = [p.period_code for p in periods]
        assert "PP-2026-01" in codes
        assert "PP-2026-02" in codes
        assert "PP-2026-03" in codes


def test_employee_id_nomenclature():
    with Session(engine) as session:
        employees = session.exec(select(Employee)).all()
        assert len(employees) >= 50
        for emp in employees:
            assert emp.employee_id.startswith("EMP-")
            assert len(emp.employee_id) == 10  # EMP-000001
            assert emp.pay_group_id is not None
            assert emp.basic_salary > 0


def test_bridge_table_eligibility():
    with Session(engine) as session:
        eligibilities = session.exec(select(EmployeeAllowanceEligibility)).all()
        assert len(eligibilities) > 0
        for elig in eligibilities:
            assert elig.employee_id is not None
            assert elig.allowance_type in ["MEAL", "TRANSPORT", "HOUSING"]

