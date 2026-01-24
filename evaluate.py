from __future__ import annotations

import json
from typing import Dict, List, Optional, TypedDict


# ==================================================
# CONFIG
# ==================================================

PREDICTIONS_PATH: str = "output.json"
GROUND_TRUTH_PATH: str = "ground_truth.json"


# ==================================================
# TYPED STRUCTURES
# ==================================================

class ExtractionRecord(TypedDict, total=False):
    id: str
    product_line: Optional[str]
    origin_port_code: Optional[str]
    origin_port_name: Optional[str]
    destination_port_code: Optional[str]
    destination_port_name: Optional[str]
    incoterm: Optional[str]
    cargo_weight_kg: Optional[float]
    cargo_cbm: Optional[float]
    is_dangerous: Optional[bool]


# ==================================================
# EVALUATED FIELDS (MANDATORY – 9)
# ==================================================

EVALUATED_FIELDS: List[str] = [
    "product_line",
    "origin_port_code",
    "origin_port_name",
    "destination_port_code",
    "destination_port_name",
    "incoterm",
    "cargo_weight_kg",
    "cargo_cbm",
    "is_dangerous",
]


# ==================================================
# LOADERS
# ==================================================

def load_json(path: str) -> List[Dict[str, object]]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ==================================================
# NORMALIZATION / COMPARISON
# ==================================================

def normalize_str(value: Optional[str]) -> Optional[str]:
    return value.strip().lower() if isinstance(value, str) else None


def normalize_float(value: Optional[float]) -> Optional[float]:
    return round(float(value), 2) if value is not None else None


def values_equal(pred: object, truth: object) -> bool:
    # Both missing
    if pred is None and truth is None:
        return True

    # One missing
    if pred is None or truth is None:
        return False

    # Boolean (strict)
    if isinstance(truth, bool):
        return isinstance(pred, bool) and pred == truth

    # Numeric
    if isinstance(truth, (int, float)):
        if not isinstance(pred, (int, float, str)):
            return False
        try:
            return (
                normalize_float(float(pred))
                == normalize_float(float(truth))
            )
        except (TypeError, ValueError):
            return False

    # String
    if isinstance(truth, str):
        return normalize_str(str(pred)) == normalize_str(truth)

    return False


# ==================================================
# EVALUATION
# ==================================================

def evaluate(
    predictions: List[Dict[str, object]],
    ground_truth: List[Dict[str, object]],
) -> None:
    # Index ground truth by ID (type-safe)
    truth_by_id: Dict[str, Dict[str, object]] = {}
    for item in ground_truth:
        record_id = item.get("id")
        if isinstance(record_id, str):
            truth_by_id[record_id] = item

    field_correct: Dict[str, int] = dict.fromkeys(EVALUATED_FIELDS, 0)
    field_total: Dict[str, int] = dict.fromkeys(EVALUATED_FIELDS, 0)

    total_correct = 0
    total_fields = 0

    for pred in predictions:
        record_id = pred.get("id")
        if not isinstance(record_id, str):
            continue

        truth = truth_by_id.get(record_id)
        if truth is None:
            continue

        # Compute field comparisons in one step
        comparisons = {
            field: values_equal(pred.get(field), truth.get(field))
            for field in EVALUATED_FIELDS
        }

        for field, is_correct in comparisons.items():
            field_total[field] += 1
            total_fields += 1

            if is_correct:
                field_correct[field] += 1
                total_correct += 1

    # ==================================================
    # REPORT METRICS
    # ==================================================

    print("\n=== FIELD-LEVEL ACCURACY ===")
    for field in EVALUATED_FIELDS:
        correct = field_correct[field]
        total = field_total[field]
        accuracy = (correct / total * 100) if total else 0.0
        print(f"{field:25s}: {accuracy:6.2f}% ({correct}/{total})")

    overall_accuracy = (total_correct / total_fields * 100) if total_fields else 0.0

    print("\n=== OVERALL ACCURACY ===")
    print(
        f"Overall Accuracy: {overall_accuracy:.2f}% "
        f"({total_correct}/{total_fields})\n"
    )


# ==================================================
# MAIN
# ==================================================

def main() -> None:
    predictions = load_json(PREDICTIONS_PATH)
    ground_truth = load_json(GROUND_TRUTH_PATH)
    evaluate(predictions, ground_truth)


if __name__ == "__main__":
    main()
