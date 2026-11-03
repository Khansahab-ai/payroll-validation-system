"""
Configuration settings for deterministic synthetic data generation.
"""

# Deterministic Seed (explicitly specified in Problem Statement Step 4)
SEED = 20261022

# Scale Profiles
PROFILES = {
    "starter": {
        "employee_count": 50,
        "description": "Starter profile for rapid testing and interactive dashboard demonstration (~3,000 records)"
    },
    "full": {
        "employee_count": 3000,
        "description": "Full benchmark volume profile (3,000 employees, 3 months, ~100,000 records)"
    }
}

# Pay Periods (Q1 2026)
PAY_PERIODS_DEF = [
    {
        "period_code": "PP-2026-01",
        "start_date": "2026-01-01",
        "end_date": "2026-01-31",
        "payment_date": "2026-02-05",
        "status": "OPEN"
    },
    {
        "period_code": "PP-2026-02",
        "start_date": "2026-02-01",
        "end_date": "2026-02-28",
        "payment_date": "2026-03-05",
        "status": "OPEN"
    },
    {
        "period_code": "PP-2026-03",
        "start_date": "2026-03-01",
        "end_date": "2026-03-31",
        "payment_date": "2026-04-05",
        "status": "OPEN"
    }
]

# Pay Groups
PAY_GROUPS_DEF = [
    {
        "group_code": "PG-001",
        "group_name": "Monthly Employees",
        "pay_frequency": "MONTHLY",
        "max_period_hours": 200.0,
        "standard_hours": 160.0
    },
    {
        "group_code": "PG-002",
        "group_name": "Contract Employees",
        "pay_frequency": "MONTHLY",
        "max_period_hours": 220.0,
        "standard_hours": 160.0
    },
    {
        "group_code": "PG-003",
        "group_name": "Part-time Employees",
        "pay_frequency": "MONTHLY",
        "max_period_hours": 100.0,
        "standard_hours": 80.0
    }
]

