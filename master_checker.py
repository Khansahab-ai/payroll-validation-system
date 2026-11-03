import sys
from sqlmodel import Session, select, func

# Ensure project root in sys.path
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from backend.database import engine
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
    AuditLog,
    EmployeeAllowanceEligibility
)
from backend.services.validation_service import evaluate_ground_truth_metrics


def run_master_check():
    with Session(engine) as session:
        employees = session.exec(select(Employee)).all()
        groups = session.exec(select(PayGroup)).all()
        periods = session.exec(select(PayPeriod)).all()
        time_entries = session.exec(select(TimeEntry)).all()
        leave_records = session.exec(select(LeaveRecord)).all()
        allowances = session.exec(select(Allowance)).all()
        deductions = session.exec(select(Deduction)).all()
        payroll_inputs = session.exec(select(PayrollInput)).all()
        rules = session.exec(select(ValidationRule)).all()
        exceptions = session.exec(select(ExceptionRecord)).all()
        approvals = session.exec(select(Approval)).all()
        exports = session.exec(select(PayrollExport)).all()
        audit_logs = session.exec(select(AuditLog)).all()
        eligibilities = session.exec(select(EmployeeAllowanceEligibility)).all()

        print("\n=======================================================")
        print("          MASTER SYSTEM DATABASE AUDIT REPORT")
        print("=======================================================\n")

        print(f"{'Entity':<35} | {'Count':<10}")
        print("-" * 50)
        print(f"{'1. PayGroups':<35} | {len(groups):<10}")
        print(f"{'2. Employees':<35} | {len(employees):<10}")
        print(f"{'3. PayPeriods':<35} | {len(periods):<10}")
        print(f"{'4. TimeEntries':<35} | {len(time_entries):<10}")
        print(f"{'5. LeaveRecords':<35} | {len(leave_records):<10}")
        print(f"{'6. Allowances':<35} | {len(allowances):<10}")
        print(f"{'7. Deductions':<35} | {len(deductions):<10}")
        print(f"{'8. PayrollInputs':<35} | {len(payroll_inputs):<10}")
        print(f"{'9. ValidationRules':<35} | {len(rules):<10}")
        print(f"{'10. Exceptions':<35} | {len(exceptions):<10}")
        print(f"{'11. Approvals':<35} | {len(approvals):<10}")
        print(f"{'12. PayrollExports':<35} | {len(exports):<10}")
        print(f"{'13. AuditLogs':<35} | {len(audit_logs):<10}")
        print(f"{'14. Bridge Table (Eligibilities)':<35} | {len(eligibilities):<10}")

        print("\n-------------------------------------------------------")
        print("          ID NOMENCLATURE CONVENTIONS VERIFICATION")
        print("-------------------------------------------------------")
        if employees:
            print(f"Employee ID sample:       {employees[0].employee_id} (Expected: EMP-000001)")
        if periods:
            print(f"PayPeriod code sample:    {periods[0].period_code} (Expected: PP-2026-01)")
        if time_entries:
            print(f"TimeEntry ID sample:      {time_entries[0].time_id} (Expected: TIME-<emp>-<date>)")
        if payroll_inputs:
            print(f"PayrollInput ID sample:   {payroll_inputs[0].payroll_input_id} (Expected: PIN-<emp>-<period>)")
        if exports:
            print(f"PayrollExport ID sample:  {exports[0].export_id} (Expected: PEX-2026-000001)")

        print("\n-------------------------------------------------------")
        print("          PLANTED EDGE CASES / ANOMALY AUDIT")
        print("-------------------------------------------------------")
        open_excs = [e for e in exceptions if e.status == "OPEN"]
        resolved_excs = [e for e in exceptions if e.status == "RESOLVED"]

        print(f"Total Exceptions:    {len(exceptions)}")
        print(f"Open Exceptions:     {len(open_excs)}")
        print(f"Resolved Exceptions: {len(resolved_excs)}")

        from collections import Counter
        counts = Counter(e.issue_type for e in open_excs)
        for issue_type, count in sorted(counts.items()):
            print(f"  • {issue_type:<32}: {count}")

        print("\n-------------------------------------------------------")
        print("          GROUND TRUTH EVALUATION METRICS")
        print("-------------------------------------------------------")
        metrics = evaluate_ground_truth_metrics(session)
        if metrics.get("ground_truth_available"):
            print(f"Ground Truth Planted Anomalies: {metrics.get('ground_truth_count')}")
            print(f"True Positives Detected (TP):   {metrics.get('true_positives')}")
            print(f"False Positives (FP):           {metrics.get('false_positives')}")
            print(f"False Negatives (FN):           {metrics.get('false_negatives')}")
            print(f"Precision:                      {metrics.get('precision'):.1%}")
            print(f"Recall:                         {metrics.get('recall'):.1%}")
            print(f"F1-Score:                       {metrics.get('f1_score'):.3f}")
        else:
            print("Ground truth file not found.")

        print("\n=======================================================")
        print("          AUDIT REPORT COMPLETED SUCCESSFULLY")
        print("=======================================================\n")


if __name__ == "__main__":
    run_master_check()
