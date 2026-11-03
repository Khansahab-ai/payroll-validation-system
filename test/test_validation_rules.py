import pytest
from sqlmodel import Session, select

from backend.database import engine
from backend.models.models import ValidationRule, ExceptionRecord
from backend.services.validation_service import run_all_validations


def test_validation_rules_registered():
    with Session(engine) as session:
        rules = session.exec(select(ValidationRule)).all()
        assert len(rules) == 8
        rule_codes = {r.rule_code for r in rules}
        expected_codes = {
            "RULE-BANK-001",
            "RULE-TAX-001",
            "RULE-TIME-DUP-001",
            "RULE-TIME-EXC-001",
            "RULE-ALW-DUP-001",
            "RULE-TIME-UNAPP-001",
            "RULE-LEV-DUP-001",
            "RULE-PAY-RECON-001"
        }
        assert rule_codes == expected_codes


def test_validation_flags_all_edge_cases():
    with Session(engine) as session:
        result = run_all_validations(session)
        assert result["success"] is True

        all_exceptions = session.exec(select(ExceptionRecord)).all()
        issue_types = {e.issue_type for e in all_exceptions}

        # Verify all 8 issue types are detected and categorized
        assert "MISSING_BANK_ACCOUNT" in issue_types
        assert "MISSING_TAX_ID" in issue_types
        assert "DUPLICATE_TIME_ENTRY" in issue_types
        assert "EXCESSIVE_WORKING_HOURS" in issue_types
        assert "DUPLICATE_ALLOWANCE" in issue_types
        assert "UNAPPROVED_TIME_ENTRY" in issue_types
        assert "DUPLICATE_LEAVE_DEDUCTION" in issue_types
        assert "PAYROLL_RECONCILIATION_MISMATCH" in issue_types

