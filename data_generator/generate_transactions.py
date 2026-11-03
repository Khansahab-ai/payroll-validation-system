from datetime import date, timedelta
import random
from typing import Dict, List, Optional
from sqlmodel import Session, select

from backend.models.models import (
    Employee,
    PayGroup,
    PayPeriod,
    TimeEntry,
    LeaveRecord,
    Allowance,
    Deduction
)
from data_generator.config import SEED


def generate_time_entries(
    session: Session,
    seed: int = SEED,
    days_per_month_sample: Optional[int] = None
) -> int:
    """
    Generate valid baseline time entries adhering to the naming convention:
    TIME-<employee-id>-<date> (e.g. TIME-EMP-000001-2026-01-05).
    Guarantees valid parent foreign keys and respects pay group hours limits.
    """
    random.seed(seed)
    employees = session.exec(select(Employee).order_by(Employee.id)).all()
    pay_groups = {g.id: g for g in session.exec(select(PayGroup)).all()}
    pay_periods = session.exec(select(PayPeriod).order_by(PayPeriod.start_date)).all()

    existing_time_count = len(session.exec(select(TimeEntry)).all())
    if existing_time_count > 0:
        return existing_time_count

    entries_to_add: List[TimeEntry] = []
    total_generated = 0

    # Determine sampling density to reach ~100k records at full scale (3000 employees)
    # or ~2,500 records at starter scale (50 employees)
    is_large_scale = len(employees) > 500

    for emp in employees:
        pay_group = pay_groups.get(emp.pay_group_id)
        if not pay_group:
            continue

        is_part_time = pay_group.max_period_hours <= 100.0

        for period in pay_periods:
            current_date = period.start_date
            period_hours = 0.0
            workday_index = 0

            # Target monthly hours well within limit for clean baseline
            max_target = 85.0 if is_part_time else 168.0

            while current_date <= period.end_date:
                # Monday to Friday
                if current_date.weekday() < 5:
                    workday_index += 1

                    # At large scale, sample ~10-12 days per month to keep 3000 employees around 100k total
                    # At starter scale, include all weekdays (~22 days)
                    include_day = True
                    if is_large_scale:
                        include_day = (workday_index % 2 == 0) or (random.random() < 0.25)
                    elif is_part_time:
                        include_day = (workday_index % 2 == 1)

                    if include_day and period_hours < max_target:
                        hours = 4.0 if is_part_time else random.choice([8.0, 8.0, 8.0, 8.5])
                        if period_hours + hours <= max_target:
                            period_hours += hours

                            time_id = f"TIME-{emp.employee_id}-{current_date.isoformat()}"
                            sub_ref = f"SUB-{emp.employee_id}-{current_date.isoformat()}"

                            # 96% approved, 4% pending
                            status = "APPROVED" if random.random() < 0.96 else "PENDING"

                            entry = TimeEntry(
                                time_id=time_id,
                                employee_id=emp.id,
                                pay_period_id=period.id,
                                work_date=current_date,
                                hours_worked=hours,
                                approval_status=status,
                                submission_ref=sub_ref
                            )
                            entries_to_add.append(entry)

                current_date += timedelta(days=1)

                if len(entries_to_add) >= 2000:
                    session.add_all(entries_to_add)
                    session.commit()
                    total_generated += len(entries_to_add)
                    entries_to_add.clear()

    if entries_to_add:
        session.add_all(entries_to_add)
        session.commit()
        total_generated += len(entries_to_add)

    return total_generated


def generate_leave_records(
    session: Session,
    seed: int = SEED
) -> int:
    """Generate baseline leave records."""
    random.seed(seed)
    employees = session.exec(select(Employee).order_by(Employee.id)).all()
    pay_periods = session.exec(select(PayPeriod).order_by(PayPeriod.start_date)).all()

    existing_count = len(session.exec(select(LeaveRecord)).all())
    if existing_count > 0:
        return existing_count

    leaves_to_add = []
    total_generated = 0

    for emp in employees:
        # About 1 in 4 employees takes leave per period
        for period in pay_periods:
            if random.random() < 0.22:
                leave_type = random.choice(["ANNUAL", "SICK", "CASUAL", "UNPAID"])
                is_unpaid = (leave_type == "UNPAID")
                days = float(random.choice([1, 2, 3]))

                start_day = random.randint(5, 20)
                start_date = period.start_date.replace(day=start_day)
                end_date = start_date + timedelta(days=int(days) - 1)

                leave_id = f"LEV-{emp.employee_id}-{start_date.isoformat()}"
                status = "APPROVED" if random.random() < 0.92 else "PENDING"

                leave = LeaveRecord(
                    leave_id=leave_id,
                    employee_id=emp.id,
                    pay_period_id=period.id,
                    leave_type=leave_type,
                    start_date=start_date,
                    end_date=end_date,
                    days=days,
                    approval_status=status,
                    is_unpaid=is_unpaid
                )
                leaves_to_add.append(leave)

                if len(leaves_to_add) >= 1000:
                    session.add_all(leaves_to_add)
                    session.commit()
                    total_generated += len(leaves_to_add)
                    leaves_to_add.clear()

    if leaves_to_add:
        session.add_all(leaves_to_add)
        session.commit()
        total_generated += len(leaves_to_add)

    return total_generated


def generate_allowances_and_deductions(
    session: Session,
    seed: int = SEED
) -> Dict[str, int]:
    """Generate deterministic baseline allowances and deductions."""
    random.seed(seed)
    employees = session.exec(select(Employee).order_by(Employee.id)).all()
    pay_periods = session.exec(select(PayPeriod).order_by(PayPeriod.start_date)).all()
    leaves = session.exec(select(LeaveRecord)).all()

    existing_alw = len(session.exec(select(Allowance)).all())
    existing_ded = len(session.exec(select(Deduction)).all())

    if existing_alw > 0 and existing_ded > 0:
        return {"allowances": existing_alw, "deductions": existing_ded}

    alw_to_add = []
    ded_to_add = []

    # Map unpaid approved leaves to their employee and period
    leave_map = {}
    for l in leaves:
        if l.is_unpaid and l.approval_status == "APPROVED":
            leave_map[(l.employee_id, l.pay_period_id)] = l

    for emp in employees:
        for period in pay_periods:
            period_suffix = period.period_code.replace("PP-", "")
            eff_date = period.start_date

            # Allowances
            # Standard meal allowance for everyone
            alw_meal = Allowance(
                allowance_id=f"ALW-{emp.employee_id}-{period_suffix}-01",
                employee_id=emp.id,
                pay_period_id=period.id,
                allowance_type="MEAL",
                amount=1500.0,
                effective_date=eff_date,
                reference_code=f"REF-ALW-{emp.employee_id}-{period_suffix}-MEAL"
            )
            alw_to_add.append(alw_meal)

            # Transport allowance for higher salary bands
            if emp.basic_salary > 40000:
                alw_transport = Allowance(
                    allowance_id=f"ALW-{emp.employee_id}-{period_suffix}-02",
                    employee_id=emp.id,
                    pay_period_id=period.id,
                    allowance_type="TRANSPORT",
                    amount=2500.0,
                    effective_date=eff_date,
                    reference_code=f"REF-ALW-{emp.employee_id}-{period_suffix}-TRANS"
                )
                alw_to_add.append(alw_transport)

            # Deductions
            # Statutory Provident Fund (12% of basic up to standard cap)
            pf_amount = round(min(emp.basic_salary * 0.12, 5000.0), 2)
            ded_pf = Deduction(
                deduction_id=f"DED-{emp.employee_id}-{period_suffix}-01",
                employee_id=emp.id,
                pay_period_id=period.id,
                deduction_type="PF",
                amount=pf_amount,
                effective_date=eff_date,
                reference_code=f"REF-DED-{emp.employee_id}-{period_suffix}-PF"
            )
            ded_to_add.append(ded_pf)

            # Professional Tax
            ded_tax = Deduction(
                deduction_id=f"DED-{emp.employee_id}-{period_suffix}-02",
                employee_id=emp.id,
                pay_period_id=period.id,
                deduction_type="TAX",
                amount=200.0,
                effective_date=eff_date,
                reference_code=f"REF-DED-{emp.employee_id}-{period_suffix}-TAX"
            )
            ded_to_add.append(ded_tax)

            # Unpaid leave deduction if leave taken
            if (emp.id, period.id) in leave_map:
                l_rec = leave_map[(emp.id, period.id)]
                leave_ded_amount = round(l_rec.days * (emp.basic_salary / 30.0), 2)
                ded_leave = Deduction(
                    deduction_id=f"DED-{emp.employee_id}-{period_suffix}-03",
                    employee_id=emp.id,
                    pay_period_id=period.id,
                    deduction_type="UNPAID_LEAVE",
                    amount=leave_ded_amount,
                    effective_date=eff_date,
                    reference_code=f"REF-DED-{emp.employee_id}-{period_suffix}-UNPAID",
                    leave_record_id=l_rec.id
                )
                ded_to_add.append(ded_leave)

            if len(alw_to_add) >= 1000:
                session.add_all(alw_to_add)
                session.commit()
                alw_to_add.clear()

            if len(ded_to_add) >= 1000:
                session.add_all(ded_to_add)
                session.commit()
                ded_to_add.clear()

    if alw_to_add:
        session.add_all(alw_to_add)
        session.commit()
    if ded_to_add:
        session.add_all(ded_to_add)
        session.commit()

    total_alw = len(session.exec(select(Allowance)).all())
    total_ded = len(session.exec(select(Deduction)).all())

    return {"allowances": total_alw, "deductions": total_ded}
