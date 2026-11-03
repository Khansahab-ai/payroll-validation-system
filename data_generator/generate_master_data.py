from datetime import date, datetime, timezone
import random
from typing import Dict, List, Optional
from faker import Faker
from sqlmodel import Session, select

from backend.models.models import (
    PayGroup,
    PayPeriod,
    Employee,
    EmployeeAllowanceEligibility
)
from data_generator.config import SEED, PAY_GROUPS_DEF, PAY_PERIODS_DEF


def generate_pay_groups(session: Session) -> Dict[str, PayGroup]:
    """Generate or retrieve standard pay groups."""
    existing = session.exec(select(PayGroup)).all()
    group_map = {g.group_code: g for g in existing}

    for pg_data in PAY_GROUPS_DEF:
        if pg_data["group_code"] not in group_map:
            group = PayGroup(**pg_data)
            session.add(group)
            session.flush()
            group_map[group.group_code] = group

    session.commit()
    return group_map


def generate_pay_periods(session: Session) -> Dict[str, PayPeriod]:
    """Generate or retrieve pay periods for Q1 2026."""
    existing = session.exec(select(PayPeriod)).all()
    period_map = {p.period_code: p for p in existing}

    for pp_data in PAY_PERIODS_DEF:
        if pp_data["period_code"] not in period_map:
            period = PayPeriod(
                period_code=pp_data["period_code"],
                start_date=date.fromisoformat(pp_data["start_date"]),
                end_date=date.fromisoformat(pp_data["end_date"]),
                payment_date=date.fromisoformat(pp_data["payment_date"]),
                status=pp_data["status"]
            )
            session.add(period)
            session.flush()
            period_map[period.period_code] = period

    session.commit()
    return period_map


def generate_employees(
    session: Session,
    count: int = 50,
    seed: int = SEED
) -> List[Employee]:
    """
    Generate synthetic employees with deterministic IDs (EMP-000001, etc.),
    synthetic bank details, and valid foreign keys to pay groups.
    """
    random.seed(seed)
    fake = Faker()
    Faker.seed(seed)

    group_map = generate_pay_groups(session)
    pg_monthly = group_map["PG-001"].id
    pg_contract = group_map["PG-002"].id
    pg_parttime = group_map["PG-003"].id

    existing_count = len(session.exec(select(Employee)).all())
    if existing_count >= count:
        return session.exec(select(Employee).order_by(Employee.id)).all()

    departments = ["Engineering", "Operations", "Finance", "HR", "Product", "Support"]
    designations = ["Associate", "Analyst", "Engineer", "Senior Specialist", "Team Lead", "Manager"]

    employees_to_add = []
    eligibilities_to_add = []

    for i in range(existing_count + 1, count + 1):
        emp_id = f"EMP-{i:06d}"

        # Assign pay group deterministically
        if i % 10 in [8, 9]:
            pay_group_id = pg_parttime
        elif i % 10 in [6, 7]:
            pay_group_id = pg_contract
        else:
            pay_group_id = pg_monthly

        dept = departments[i % len(departments)]
        desig = designations[i % len(designations)]

        # Synthetic salaries
        if pay_group_id == pg_parttime:
            salary = float(random.choice([28000, 32000, 35000, 38000]))
        elif pay_group_id == pg_contract:
            salary = float(random.choice([45000, 52000, 60000, 72000]))
        else:
            salary = float(random.choice([55000, 68000, 75000, 92000, 110000, 125000]))

        emp = Employee(
            employee_id=emp_id,
            name=fake.name(),
            email=f"employee.{i:06d}@enterprise.com",
            department=dept,
            designation=desig,
            bank_account=f"ACC-{i:06d}-{random.randint(1000, 9999)}",
            tax_id=f"TAX-{i:06d}-{random.randint(10, 99)}",
            basic_salary=salary,
            employment_status="ACTIVE",
            pay_group_id=pay_group_id,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        employees_to_add.append(emp)

        # Batch add employees in chunks
        if len(employees_to_add) >= 500:
            session.add_all(employees_to_add)
            session.commit()
            employees_to_add.clear()

    if employees_to_add:
        session.add_all(employees_to_add)
        session.commit()

    # Create allowance eligibilities (bridge table)
    all_employees = session.exec(select(Employee).order_by(Employee.id)).all()
    existing_elig_count = len(session.exec(select(EmployeeAllowanceEligibility)).all())

    if existing_elig_count < len(all_employees):
        for emp in all_employees:
            for alw_type in ["MEAL", "TRANSPORT", "HOUSING"]:
                elig = EmployeeAllowanceEligibility(
                    employee_id=emp.id,
                    allowance_type=alw_type,
                    is_eligible=True,
                    effective_start=date(2026, 1, 1)
                )
                eligibilities_to_add.append(elig)
                if len(eligibilities_to_add) >= 1000:
                    session.add_all(eligibilities_to_add)
                    session.commit()
                    eligibilities_to_add.clear()

        if eligibilities_to_add:
            session.add_all(eligibilities_to_add)
            session.commit()

    return session.exec(select(Employee).order_by(Employee.id)).all()
