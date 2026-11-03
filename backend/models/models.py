from datetime import date, datetime, timezone
from typing import Optional

from sqlmodel import SQLModel, Field, Relationship


# =====================================================
# 1. PAY GROUP
# =====================================================

class PayGroup(SQLModel, table=True):
    __tablename__ = "pay_groups"

    id: Optional[int] = Field(default=None, primary_key=True)
    group_code: str = Field(unique=True, index=True)
    group_name: str
    pay_frequency: str = "MONTHLY"
    max_period_hours: float = 200.0
    standard_hours: float = 160.0

    employees: list["Employee"] = Relationship(back_populates="pay_group")


# =====================================================
# 2. EMPLOYEE
# =====================================================

class Employee(SQLModel, table=True):
    __tablename__ = "employees"

    id: Optional[int] = Field(default=None, primary_key=True)
    employee_id: str = Field(unique=True, index=True)  # EMP-000001
    name: str
    email: str = Field(unique=True)

    department: Optional[str] = None
    designation: Optional[str] = None

    bank_account: Optional[str] = None
    tax_id: Optional[str] = None

    basic_salary: float = Field(gt=0)
    employment_status: str = "ACTIVE"

    pay_group_id: int = Field(foreign_key="pay_groups.id")

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    pay_group: Optional[PayGroup] = Relationship(back_populates="employees")
    time_entries: list["TimeEntry"] = Relationship(back_populates="employee")
    leave_records: list["LeaveRecord"] = Relationship(back_populates="employee")
    allowances: list["Allowance"] = Relationship(back_populates="employee")
    deductions: list["Deduction"] = Relationship(back_populates="employee")
    payroll_inputs: list["PayrollInput"] = Relationship(back_populates="employee")
    exceptions: list["ExceptionRecord"] = Relationship(back_populates="employee")
    eligibilities: list["EmployeeAllowanceEligibility"] = Relationship(back_populates="employee")


# =====================================================
# 3. PAY PERIOD
# =====================================================

class PayPeriod(SQLModel, table=True):
    __tablename__ = "pay_periods"

    id: Optional[int] = Field(default=None, primary_key=True)
    period_code: str = Field(unique=True, index=True)  # PP-2026-01

    start_date: date
    end_date: date
    payment_date: Optional[date] = None

    status: str = "OPEN"

    time_entries: list["TimeEntry"] = Relationship(back_populates="pay_period")
    leave_records: list["LeaveRecord"] = Relationship(back_populates="pay_period")
    allowances: list["Allowance"] = Relationship(back_populates="pay_period")
    deductions: list["Deduction"] = Relationship(back_populates="pay_period")
    payroll_inputs: list["PayrollInput"] = Relationship(back_populates="pay_period")
    payroll_exports: list["PayrollExport"] = Relationship(back_populates="pay_period")


# =====================================================
# 4. TIME ENTRY
# =====================================================

class TimeEntry(SQLModel, table=True):
    __tablename__ = "time_entries"

    id: Optional[int] = Field(default=None, primary_key=True)
    time_id: str = Field(unique=True, index=True)  # TIME-<employee-id>-<date>

    employee_id: int = Field(foreign_key="employees.id")
    pay_period_id: int = Field(foreign_key="pay_periods.id")

    work_date: date
    hours_worked: float = Field(ge=0)

    approval_status: str = "PENDING"  # PENDING, APPROVED, REJECTED
    submission_ref: str

    corrects_time_entry_id: Optional[int] = Field(
        default=None,
        foreign_key="time_entries.id"
    )

    employee: Optional[Employee] = Relationship(back_populates="time_entries")
    pay_period: Optional[PayPeriod] = Relationship(back_populates="time_entries")


# =====================================================
# 5. LEAVE RECORD
# =====================================================

class LeaveRecord(SQLModel, table=True):
    __tablename__ = "leave_records"

    id: Optional[int] = Field(default=None, primary_key=True)
    leave_id: str = Field(unique=True, index=True)  # LEV-<employee-id>-<date>

    employee_id: int = Field(foreign_key="employees.id")
    pay_period_id: int = Field(foreign_key="pay_periods.id")

    leave_type: str  # SICK, ANNUAL, UNPAID, CASUAL

    start_date: date
    end_date: date
    days: float = Field(gt=0)

    approval_status: str = "PENDING"  # PENDING, APPROVED, REJECTED
    is_unpaid: bool = False

    employee: Optional[Employee] = Relationship(back_populates="leave_records")
    pay_period: Optional[PayPeriod] = Relationship(back_populates="leave_records")
    deductions: list["Deduction"] = Relationship(back_populates="leave_record")


# =====================================================
# 6. ALLOWANCE
# =====================================================

class Allowance(SQLModel, table=True):
    __tablename__ = "allowances"

    id: Optional[int] = Field(default=None, primary_key=True)
    allowance_id: str = Field(unique=True, index=True)  # ALW-<employee-id>-<period>-<seq>

    employee_id: int = Field(foreign_key="employees.id")
    pay_period_id: int = Field(foreign_key="pay_periods.id")

    allowance_type: str  # HOUSING, TRANSPORT, MEAL, MEDICAL
    amount: float = Field(ge=0)
    effective_date: date
    reference_code: str

    employee: Optional[Employee] = Relationship(back_populates="allowances")
    pay_period: Optional[PayPeriod] = Relationship(back_populates="allowances")


# =====================================================
# 7. DEDUCTION
# =====================================================

class Deduction(SQLModel, table=True):
    __tablename__ = "deductions"

    id: Optional[int] = Field(default=None, primary_key=True)
    deduction_id: str = Field(unique=True, index=True)  # DED-<employee-id>-<period>-<seq>

    employee_id: int = Field(foreign_key="employees.id")
    pay_period_id: int = Field(foreign_key="pay_periods.id")

    deduction_type: str  # TAX, PF, INSURANCE, UNPAID_LEAVE
    amount: float = Field(ge=0)
    effective_date: date
    reference_code: str

    leave_record_id: Optional[int] = Field(
        default=None,
        foreign_key="leave_records.id"
    )

    employee: Optional[Employee] = Relationship(back_populates="deductions")
    pay_period: Optional[PayPeriod] = Relationship(back_populates="deductions")
    leave_record: Optional[LeaveRecord] = Relationship(back_populates="deductions")


# =====================================================
# 8. PAYROLL INPUT
# =====================================================

class PayrollInput(SQLModel, table=True):
    __tablename__ = "payroll_inputs"

    id: Optional[int] = Field(default=None, primary_key=True)
    payroll_input_id: str = Field(unique=True, index=True)  # PIN-<employee-id>-2026-01

    employee_id: int = Field(foreign_key="employees.id")
    pay_period_id: int = Field(foreign_key="pay_periods.id")

    basic_salary: float
    overtime_amount: float = 0.0

    allowance_total: float = 0.0
    deduction_total: float = 0.0
    unpaid_leave_deduction: float = 0.0

    net_pay: float
    status: str = "DRAFT"  # DRAFT, PENDING, APPROVED, REJECTED, EXPORTED

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    employee: Optional[Employee] = Relationship(back_populates="payroll_inputs")
    pay_period: Optional[PayPeriod] = Relationship(back_populates="payroll_inputs")
    exceptions: list["ExceptionRecord"] = Relationship(back_populates="payroll_input")
    approvals: list["Approval"] = Relationship(back_populates="payroll_input")


# =====================================================
# 9. VALIDATION RULE
# =====================================================

class ValidationRule(SQLModel, table=True):
    __tablename__ = "validation_rules"

    id: Optional[int] = Field(default=None, primary_key=True)
    rule_code: str = Field(unique=True, index=True)  # RULE-BANK-001
    rule_name: str
    description: Optional[str] = None
    severity: str = "HIGH"  # HIGH, MEDIUM, LOW
    is_active: bool = True

    exceptions: list["ExceptionRecord"] = Relationship(back_populates="validation_rule")


# =====================================================
# 10. EXCEPTION
# =====================================================

class ExceptionRecord(SQLModel, table=True):
    __tablename__ = "exceptions"

    id: Optional[int] = Field(default=None, primary_key=True)
    exception_id: str = Field(unique=True, index=True)  # EXC-...

    payroll_input_id: Optional[int] = Field(
        default=None,
        foreign_key="payroll_inputs.id"
    )

    validation_rule_id: Optional[int] = Field(
        default=None,
        foreign_key="validation_rules.id"
    )

    employee_id: int = Field(foreign_key="employees.id")

    issue_type: str
    description: Optional[str] = None

    status: str = "OPEN"  # OPEN, RESOLVED
    severity: str = "HIGH"  # HIGH, MEDIUM, LOW

    source_entity: Optional[str] = None
    source_record_id: Optional[str] = None

    resolution_notes: Optional[str] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[datetime] = None

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    payroll_input: Optional[PayrollInput] = Relationship(back_populates="exceptions")
    validation_rule: Optional[ValidationRule] = Relationship(back_populates="exceptions")
    employee: Optional[Employee] = Relationship(back_populates="exceptions")


# =====================================================
# 11. APPROVAL
# =====================================================

class Approval(SQLModel, table=True):
    __tablename__ = "approvals"

    id: Optional[int] = Field(default=None, primary_key=True)
    approval_id: str = Field(unique=True, index=True)  # APR-...

    payroll_input_id: int = Field(foreign_key="payroll_inputs.id")

    approver_name: str
    approver_role: str  # HR, MANAGER, ADMIN, IT_OPS
    decision: str  # APPROVED, REJECTED
    comments: Optional[str] = None

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    payroll_input: Optional[PayrollInput] = Relationship(back_populates="approvals")


# =====================================================
# 12. PAYROLL EXPORT
# =====================================================

class PayrollExport(SQLModel, table=True):
    __tablename__ = "payroll_exports"

    id: Optional[int] = Field(default=None, primary_key=True)
    export_id: str = Field(unique=True, index=True)  # PEX-2026-000001

    pay_period_id: int = Field(foreign_key="pay_periods.id")

    file_name: str
    file_format: str = "CSV"
    record_count: int = 0
    total_amount: float = 0.0

    export_status: str = "COMPLETED"  # COMPLETED, FAILED
    exported_by: str = "SYSTEM"

    exported_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    pay_period: Optional[PayPeriod] = Relationship(back_populates="payroll_exports")


# =====================================================
# 13. AUDIT LOG (Event History for State Changes)
# =====================================================

class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    log_id: str = Field(unique=True, index=True)  # AUD-2026-000001

    entity_name: str
    record_id: str
    action: str  # CREATE, UPDATE, APPROVE, REJECT, RESOLVE, EXPORT, RECALCULATE, DUPLICATE_VOID
    actor_role: str  # EMPLOYEE, MANAGER, HR, IT_OPS, ADMIN, SYSTEM
    actor_name: str

    old_values: Optional[str] = None
    new_values: Optional[str] = None
    reason: Optional[str] = None

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# =====================================================
# 14. EMPLOYEE ALLOWANCE ELIGIBILITY (Bridge Table)
# =====================================================

class EmployeeAllowanceEligibility(SQLModel, table=True):
    __tablename__ = "employee_allowance_eligibilities"

    id: Optional[int] = Field(default=None, primary_key=True)
    employee_id: int = Field(foreign_key="employees.id")
    allowance_type: str
    is_eligible: bool = True
    effective_start: date
    effective_end: Optional[date] = None

    employee: Optional[Employee] = Relationship(back_populates="eligibilities")
