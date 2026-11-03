import json
from pathlib import Path
import pytest
from sqlmodel import Session

from backend.database import engine
from backend.services.validation_service import evaluate_ground_truth_metrics
from data_generator.generate_all import verify_reproducibility


def test_ground_truth_files_exist():
    gt_json = Path("datasets/ground_truth.json")
    gt_csv = Path("datasets/ground_truth.csv")
    assert gt_json.exists()
    assert gt_csv.exists()

    with open(gt_json, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert len(data) >= 8  # Covers all 8 edge cases


def test_ground_truth_recall_metric():
    with Session(engine) as session:
        metrics = evaluate_ground_truth_metrics(session)
        assert metrics["ground_truth_available"] is True
        assert metrics["true_positives"] >= 8
        assert metrics["recall"] >= 0.80
        assert metrics["f1_score"] >= 0.80


def test_step10_reproducibility():
    is_reproducible = verify_reproducibility(scale="starter", seed=20261022)
    assert is_reproducible is True

