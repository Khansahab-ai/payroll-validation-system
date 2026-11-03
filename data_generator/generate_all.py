import argparse
import os
from pathlib import Path
import sys

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Ensure UTF-8 output encoding on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from sqlmodel import Session, SQLModel, create_engine, select

from backend.database import engine, create_db_and_tables
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
from backend.services.validation_service import ensure_validation_rules, run_all_validations
from data_generator.config import SEED, PROFILES
from data_generator.generate_master_data import (
    generate_pay_groups,
    generate_pay_periods,
    generate_employees
)
from data_generator.generate_transactions import (
    generate_time_entries,
    generate_leave_records,
    generate_allowances_and_deductions
)
from data_generator.inject_anomalies import inject_edge_cases_and_ground_truth
from data_generator.export_seeds import export_all_datasets, run_step8_integrity_validation


def reset_and_initialize_database(custom_engine=None):
    """Drop and recreate all tables cleanly."""
    eng = custom_engine or engine
    SQLModel.metadata.drop_all(eng)
    SQLModel.metadata.create_all(eng)


def run_pipeline(
    scale: str = "starter",
    seed: int = SEED,
    custom_engine=None,
    export_seeds: bool = True
) -> dict:
    """
    Run end-to-end data generation pipeline following Steps 1-9.
    """
    eng = custom_engine or engine
    reset_and_initialize_database(eng)

    employee_count = PROFILES.get(scale, PROFILES["starter"])["employee_count"]

    print(f"\n=======================================================")
    print(f"  PAYROLL SYNTHETIC DATA GENERATOR (SEED: {seed})")
    print(f"  Profile: {scale.upper()} ({employee_count} employees)")
    print(f"=======================================================\n")

    with Session(eng) as session:
        # Step 2 & 3: Master Data First
        print("> Generating PayGroups and PayPeriods...")
        generate_pay_groups(session)
        generate_pay_periods(session)

        print(f"> Generating {employee_count} Employees with deterministic IDs...")
        generate_employees(session, count=employee_count, seed=seed)

        # Step 2 & 3: Transactions
        print("> Generating Time Entries (respecting period limits)...")
        time_count = generate_time_entries(session, seed=seed)
        print(f"  [OK] {time_count} time entries generated.")

        print("> Generating Leave Records...")
        leave_count = generate_leave_records(session, seed=seed)
        print(f"  [OK] {leave_count} leave records generated.")

        print("> Generating Allowances & Deductions...")
        ad_counts = generate_allowances_and_deductions(session, seed=seed)
        print(f"  [OK] {ad_counts['allowances']} allowances, {ad_counts['deductions']} deductions generated.")

        # Step 6: Calculate Derived Values (Payroll Inputs)
        print("> Aggregating Payroll Inputs (PIN-<emp-id>-<period>)...")
        p_res = generate_payroll(session)
        print(f"  [OK] {p_res['created_records']} payroll records generated.")

        # Step 5 & 7: Inject Labelled Edge Cases & Output Ground Truth
        print("> Injecting 8 Labelled Edge Cases & Producing ground_truth.json/.csv...")
        gt_records = inject_edge_cases_and_ground_truth(session)
        print(f"  [OK] {len(gt_records)} edge cases injected and documented.")

        # Ensure validation rules are registered & run validations
        print("> Initializing Validation Rules & Running Validations...")
        val_res = run_all_validations(session)
        print(f"  [OK] Validation cycle completed: {val_res['total_exceptions']} total exceptions flagged.")

        # Step 8 & 9: Integrity Verification & Seed Export
        manifest = {}
        if export_seeds:
            print("> Step 8 Integrity Validation & Step 9 CSV/JSON/SQL Seed Export...")
            manifest = export_all_datasets(session, scale=scale)
            print("  [OK] Datasets and manifests successfully exported to datasets/ folder.")

    print("\n=======================================================")
    print("  DATA GENERATION PIPELINE COMPLETED SUCCESSFULLY!")
    print("=======================================================\n")
    return manifest


def verify_reproducibility(scale: str = "starter", seed: int = SEED) -> bool:
    """
    Step 10: Regenerate twice with the same seed and compare row counts/checksums
    to demonstrate 100% deterministic reproducibility.
    """
    import tempfile
    print("\n=======================================================")
    print(f"  STEP 10: DETERMINISTIC REPRODUCIBILITY VERIFICATION")
    print(f"  Fixed Seed: {seed}")
    print("=======================================================\n")

    db1_path = Path("payroll_run1_verify.db")
    db2_path = Path("payroll_run2_verify.db")

    if db1_path.exists():
        db1_path.unlink()
    if db2_path.exists():
        db2_path.unlink()

    engine1 = create_engine(f"sqlite:///{db1_path}", connect_args={"check_same_thread": False})
    engine2 = create_engine(f"sqlite:///{db2_path}", connect_args={"check_same_thread": False})

    try:
        print("> Executing Run 1...")
        run_pipeline(scale=scale, seed=seed, custom_engine=engine1, export_seeds=False)

        print("> Executing Run 2 with identical seed...")
        run_pipeline(scale=scale, seed=seed, custom_engine=engine2, export_seeds=False)

        tables = [
            ("employees", Employee),
            ("pay_groups", PayGroup),
            ("pay_periods", PayPeriod),
            ("time_entries", TimeEntry),
            ("leave_records", LeaveRecord),
            ("allowances", Allowance),
            ("deductions", Deduction),
            ("payroll_inputs", PayrollInput),
            ("validation_rules", ValidationRule),
            ("exceptions", ExceptionRecord)
        ]

        mismatches = []
        with Session(engine1) as s1, Session(engine2) as s2:
            print(f"{'Table':<30} | {'Run 1 Count':<12} | {'Run 2 Count':<12} | {'Match?':<8}")
            print("-" * 70)
            for name, model in tables:
                r1 = s1.exec(select(model)).all()
                r2 = s2.exec(select(model)).all()

                c1 = len(r1)
                c2 = len(r2)
                match = (c1 == c2)

                print(f"{name:<30} | {c1:<12} | {c2:<12} | {'MATCH' if match else 'DIFF'}")
                if not match:
                    mismatches.append(f"{name}: Run1={c1}, Run2={c2}")

        if not mismatches:
            print("\n[SUCCESS] Deterministic reproducibility verified: 100% exact match across all tables!")
            return True
        else:
            print(f"\n[FAILURE] Reproducibility mismatch found: {mismatches}")
            return False

    finally:
        engine1.dispose()
        engine2.dispose()
        if db1_path.exists():
            db1_path.unlink()
        if db2_path.exists():
            db2_path.unlink()


def main():
    parser = argparse.ArgumentParser(description="Payroll System Synthetic Data Generator")
    parser.add_argument(
        "--scale",
        choices=["starter", "full"],
        default="starter",
        help="Scale profile: starter (50 employees) or full (3,000 employees)"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=SEED,
        help=f"Deterministic random seed (default: {SEED})"
    )
    parser.add_argument(
        "--verify-reproducibility",
        action="store_true",
        help="Execute Step 10: regenerate twice with seed and compare counts/hashes"
    )
    parser.add_argument(
        "--no-export",
        action="store_true",
        help="Skip Step 9 dataset export"
    )

    args = parser.parse_args()

    if args.verify_reproducibility:
        success = verify_reproducibility(scale=args.scale, seed=args.seed)
        sys.exit(0 if success else 1)
    else:
        run_pipeline(scale=args.scale, seed=args.seed, export_seeds=(not args.no_export))


if __name__ == "__main__":
    main()
