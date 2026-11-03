from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import inspect
from sqlmodel import Session, select

from backend.database import (
    engine,
    create_db_and_tables,
    get_session
)
from backend.models.models import (
    Employee,
    PayGroup,
    PayPeriod,
    TimeEntry,
    LeaveRecord,
    Allowance,
    Deduction,
    PayrollInput,
    ValidationRule,
    ExceptionRecord,
    Approval,
    PayrollExport,
    AuditLog
)
from backend.services.payroll_service import generate_payroll
from backend.services.validation_service import run_all_validations, evaluate_ground_truth_metrics
from backend.services.exception_service import (
    get_open_exceptions,
    resolve_exception
)
from backend.services.approval_service import (
    process_payroll_approval
)
from backend.services.payroll_export_service import (
    export_approved_payroll
)
from backend.services.employee_service import (
    update_employee_payroll_details
)
from backend.services.transaction_service import (
    update_time_entry,
    mark_duplicate_time_entry,
    bulk_approve_pending_time_entries,
    update_allowance,
    mark_duplicate_allowance,
    mark_duplicate_leave_deduction,
    reconcile_payroll_record,
    recalculate_payroll_record
)

app = FastAPI(
    title="Payroll Validation System",
    description="End-to-end payroll validation, reconciliation, approvals, and export engine.",
    version="2.0.0"
)


# ==========================================
# REQUEST SCHEMAS
# ==========================================

class ExceptionResolutionRequest(BaseModel):
    resolution_comments: str
    actor_name: str = "HR Partner"
    actor_role: str = "HR"


class ApprovalRequest(BaseModel):
    approver_name: str
    approver_role: str
    decision: str
    comments: str = ""


class EmployeePayrollDetailsRequest(BaseModel):
    bank_account: Optional[str] = None
    tax_id: Optional[str] = None
    actor_name: str = "HR Partner"
    actor_role: str = "HR"


class TimeEntryCorrectionRequest(BaseModel):
    hours_worked: Optional[float] = None
    approval_status: Optional[str] = None
    submission_ref: Optional[str] = None
    actor_name: str = "Manager"
    actor_role: str = "MANAGER"
    reason: str = "Manager time correction"


class AllowanceCorrectionRequest(BaseModel):
    amount: Optional[float] = None
    reference_code: Optional[str] = None
    allowance_type: Optional[str] = None
    actor_name: str = "HR Partner"
    actor_role: str = "HR"
    reason: str = "Allowance correction"


class BulkApproveRequest(BaseModel):
    employee_id: Optional[int] = None
    pay_period_id: Optional[int] = None
    actor_name: str = "Manager"
    actor_role: str = "MANAGER"


class ExportRequest(BaseModel):
    actor_name: str = "System Administrator"
    actor_role: str = "SYSTEM"


# ==========================================
# DATABASE INITIALIZATION
# ==========================================

@app.on_event("startup")
def on_startup():
    create_db_and_tables()


# ==========================================
# BASIC & HEALTH CHECK ENDPOINTS
# ==========================================

@app.get("/")
def home():
    return {
        "message": "Payroll Validation System API is running!",
        "version": "2.0.0",
        "status": "success"
    }


@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.get("/database-check")
def database_check():
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    return {
        "database": "connected",
        "total_tables": len(tables),
        "tables": tables
    }


# ==========================================
# MASTER DATA ENDPOINTS
# ==========================================

@app.get("/employees")
def get_employees(
    limit: int = 100,
    offset: int = 0,
    session: Session = Depends(get_session)
):
    employees = session.exec(select(Employee).offset(offset).limit(limit)).all()
    total = session.exec(select(Employee)).all()
    return {
        "total": len(total),
        "count": len(employees),
        "offset": offset,
        "limit": limit,
        "employees": employees
    }


@app.get("/employees/{employee_id}/details")
def get_employee_details(
    employee_id: str,
    session: Session = Depends(get_session)
):
    employee = session.exec(select(Employee).where(Employee.employee_id == employee_id)).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    pay_group = session.get(PayGroup, employee.pay_group_id)
    time_entries = session.exec(select(TimeEntry).where(TimeEntry.employee_id == employee.id)).all()
    leave_records = session.exec(select(LeaveRecord).where(LeaveRecord.employee_id == employee.id)).all()
    allowances = session.exec(select(Allowance).where(Allowance.employee_id == employee.id)).all()
    deductions = session.exec(select(Deduction).where(Deduction.employee_id == employee.id)).all()
    payroll_inputs = session.exec(select(PayrollInput).where(PayrollInput.employee_id == employee.id)).all()
    exceptions = session.exec(select(ExceptionRecord).where(ExceptionRecord.employee_id == employee.id)).all()

    return {
        "employee": employee,
        "pay_group": pay_group,
        "time_entries_count": len(time_entries),
        "leave_records_count": len(leave_records),
        "allowances_count": len(allowances),
        "deductions_count": len(deductions),
        "payroll_inputs": payroll_inputs,
        "exceptions": exceptions,
        "recent_time_entries": time_entries[:15]
    }


@app.get("/pay-periods")
def get_pay_periods(session: Session = Depends(get_session)):
    return session.exec(select(PayPeriod)).all()


@app.get("/pay-groups")
def get_pay_groups(session: Session = Depends(get_session)):
    return session.exec(select(PayGroup)).all()


@app.get("/validation-rules")
def get_validation_rules(session: Session = Depends(get_session)):
    return session.exec(select(ValidationRule)).all()


# ==========================================
# PAYROLL GENERATION & CALCULATION
# ==========================================

@app.post("/payroll/generate")
def generate_payroll_api(session: Session = Depends(get_session)):
    result = generate_payroll(session)
    total_records = session.exec(select(PayrollInput)).all()
    return {
        "success": True,
        "message": "Payroll aggregation completed successfully.",
        "service_result": result,
        "total_payroll_records": len(total_records)
    }


@app.get("/payroll")
def get_payroll_records(
    period_id: Optional[int] = None,
    status: Optional[str] = None,
    session: Session = Depends(get_session)
):
    query = select(PayrollInput)
    if period_id is not None:
        query = query.where(PayrollInput.pay_period_id == period_id)
    if status is not None:
        query = query.where(PayrollInput.status == status.upper())
    return session.exec(query).all()


@app.post("/payroll/{payroll_input_id}/reconcile")
def reconcile_payroll_api(
    payroll_input_id: str,
    session: Session = Depends(get_session)
):
    return reconcile_payroll_record(session, payroll_input_id)


# ==========================================
# PAYROLL VALIDATION & EVALUATION METRICS
# ==========================================

@app.post("/payroll/validate")
def validate_payroll_api(session: Session = Depends(get_session)):
    return run_all_validations(session)


@app.get("/validation/metrics")
def get_validation_metrics_api(session: Session = Depends(get_session)):
    return evaluate_ground_truth_metrics(session)


# ==========================================
# EXCEPTION WORKBENCH & RESOLUTION
# ==========================================

@app.get("/exceptions")
def get_exceptions_api(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    issue_type: Optional[str] = None,
    session: Session = Depends(get_session)
):
    query = select(ExceptionRecord)
    if status:
        query = query.where(ExceptionRecord.status == status.upper())
    if severity:
        query = query.where(ExceptionRecord.severity == severity.upper())
    if issue_type:
        query = query.where(ExceptionRecord.issue_type == issue_type)
    query = query.order_by(ExceptionRecord.employee_id.asc(), ExceptionRecord.id.asc())
    return session.exec(query).all()


@app.post("/exceptions/{exception_id}/resolve")
def resolve_exception_api(
    exception_id: str,
    request: ExceptionResolutionRequest,
    session: Session = Depends(get_session)
):
    return resolve_exception(
        session=session,
        exception_id=exception_id,
        resolution_comments=request.resolution_comments,
        actor_name=request.actor_name,
        actor_role=request.actor_role
    )


# ==========================================
# IN-LINE TRANSACTION & MASTER DATA CORRECTIONS
# ==========================================

@app.patch("/employees/{employee_db_id}/payroll-details")
def update_employee_details_api(
    employee_db_id: int,
    request: EmployeePayrollDetailsRequest,
    session: Session = Depends(get_session)
):
    return update_employee_payroll_details(
        session=session,
        employee_db_id=employee_db_id,
        bank_account=request.bank_account,
        tax_id=request.tax_id,
        actor_name=request.actor_name,
        actor_role=request.actor_role
    )


@app.patch("/time-entries/{time_id}")
def correct_time_entry_api(
    time_id: str,
    request: TimeEntryCorrectionRequest,
    session: Session = Depends(get_session)
):
    return update_time_entry(
        session=session,
        time_id=time_id,
        hours_worked=request.hours_worked,
        approval_status=request.approval_status,
        submission_ref=request.submission_ref,
        actor_name=request.actor_name,
        actor_role=request.actor_role,
        reason=request.reason
    )


@app.post("/time-entries/{time_id}/mark-duplicate")
def mark_duplicate_time_api(
    time_id: str,
    session: Session = Depends(get_session)
):
    return mark_duplicate_time_entry(session, time_id)


@app.post("/time-entries/{time_id}/approve")
def approve_time_entry_api(
    time_id: str,
    actor_name: str = "Manager",
    session: Session = Depends(get_session)
):
    return update_time_entry(
        session=session,
        time_id=time_id,
        approval_status="APPROVED",
        actor_name=actor_name,
        actor_role="MANAGER",
        reason="Manager approved individual time entry"
    )


@app.post("/time-entries/{time_id}/reject")
def reject_time_entry_api(
    time_id: str,
    actor_name: str = "Manager",
    session: Session = Depends(get_session)
):
    return update_time_entry(
        session=session,
        time_id=time_id,
        approval_status="REJECTED",
        actor_name=actor_name,
        actor_role="MANAGER",
        reason="Manager rejected time entry"
    )


@app.post("/time-entries/bulk-approve")
def bulk_approve_time_entries_api(
    request: BulkApproveRequest,
    session: Session = Depends(get_session)
):
    return bulk_approve_pending_time_entries(
        session=session,
        employee_id=request.employee_id,
        pay_period_id=request.pay_period_id,
        actor_name=request.actor_name,
        actor_role=request.actor_role
    )


@app.patch("/allowances/{allowance_id}")
def correct_allowance_api(
    allowance_id: str,
    request: AllowanceCorrectionRequest,
    session: Session = Depends(get_session)
):
    return update_allowance(
        session=session,
        allowance_id=allowance_id,
        amount=request.amount,
        reference_code=request.reference_code,
        allowance_type=request.allowance_type,
        actor_name=request.actor_name,
        actor_role=request.actor_role,
        reason=request.reason
    )


@app.post("/allowances/{allowance_id}/mark-duplicate")
def mark_duplicate_allowance_api(
    allowance_id: str,
    session: Session = Depends(get_session)
):
    return mark_duplicate_allowance(session, allowance_id)


@app.post("/deductions/{deduction_id}/mark-duplicate")
def mark_duplicate_leave_deduction_api(
    deduction_id: str,
    session: Session = Depends(get_session)
):
    return mark_duplicate_leave_deduction(session, deduction_id)


# ==========================================
# PAYROLL APPROVAL WORKFLOW
# ==========================================

@app.post("/approvals/{payroll_id}")
def approve_payroll_api(
    payroll_id: int,
    request: ApprovalRequest,
    session: Session = Depends(get_session)
):
    return process_payroll_approval(
        session=session,
        payroll_record_id=payroll_id,
        approver_name=request.approver_name,
        approver_role=request.approver_role,
        decision=request.decision,
        comments=request.comments
    )


# ==========================================
# SECURE CSV EXPORT & DOWNLOAD
# ==========================================

@app.post("/payroll/export/{period_id}")
def export_payroll_api(
    period_id: int,
    request: Optional[ExportRequest] = None,
    session: Session = Depends(get_session)
):
    actor_name = request.actor_name if request else "System Administrator"
    actor_role = request.actor_role if request else "SYSTEM"
    return export_approved_payroll(
        session=session,
        pay_period_id=period_id,
        actor_name=actor_name,
        actor_role=actor_role
    )


@app.get("/payroll/exports")
def get_payroll_exports(session: Session = Depends(get_session)):
    return session.exec(select(PayrollExport).order_by(PayrollExport.exported_at.desc())).all()


@app.get("/payroll/exports/download/{file_name}")
def download_export_file(file_name: str):
    for d in [Path("export"), Path("exports")]:
        p = d / file_name
        if p.exists():
            return FileResponse(
                path=str(p),
                filename=file_name,
                media_type="text/csv"
            )
    raise HTTPException(status_code=404, detail="Export file not found.")


# ==========================================
# AUDIT LOGS & EVENT TRACEABILITY
# ==========================================

@app.get("/audit-logs")
def get_audit_logs(
    limit: int = 100,
    entity: Optional[str] = None,
    session: Session = Depends(get_session)
):
    query = select(AuditLog).order_by(AuditLog.timestamp.desc())
    if entity:
        query = query.where(AuditLog.entity_name == entity)
    return session.exec(query.limit(limit)).all()
