from typing import Any, Dict, Optional
from sqlmodel import Session

from backend.models.models import Employee
from backend.services.audit_service import log_audit_event


def update_employee_payroll_details(
    session: Session,
    employee_db_id: int,
    bank_account: Optional[str] = None,
    tax_id: Optional[str] = None,
    actor_name: str = "HR Partner",
    actor_role: str = "HR"
) -> Dict[str, Any]:
    """Update employee bank account or tax ID with complete audit logging."""
    employee = session.get(Employee, employee_db_id)
    if not employee:
        return {"success": False, "message": f"Employee ID {employee_db_id} not found."}

    if bank_account is None and tax_id is None:
        return {"success": False, "message": "Provide at least bank account or tax ID to update."}

    old_values = {
        "bank_account": employee.bank_account,
        "tax_id": employee.tax_id
    }

    if bank_account is not None:
        employee.bank_account = bank_account.strip()

    if tax_id is not None:
        employee.tax_id = tax_id.strip()

    session.add(employee)
    session.commit()
    session.refresh(employee)

    log_audit_event(
        session=session,
        entity_name="Employee",
        record_id=employee.employee_id,
        action="UPDATE",
        actor_role=actor_role,
        actor_name=actor_name,
        old_values=old_values,
        new_values={
            "bank_account": employee.bank_account,
            "tax_id": employee.tax_id
        },
        reason="Updated statutory payroll details",
        commit=True
    )

    return {
        "success": True,
        "employee_id": employee.employee_id,
        "bank_account": employee.bank_account,
        "tax_id": employee.tax_id,
        "message": f"Updated payroll details for {employee.employee_id}."
    }
