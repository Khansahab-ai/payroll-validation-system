import os
from pathlib import Path
import sys
import pytest

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(scope="session", autouse=True)
def init_test_suite_database():
    """Ensure the database is freshly initialized with baseline data & planted anomalies."""
    from data_generator.generate_all import run_pipeline
    run_pipeline(scale="starter", seed=20261022, export_seeds=False)
