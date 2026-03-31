from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List


def is_repair_prediction_candidate(row: Dict[str, Any]) -> bool:
    """
    harness 재평가용 repaired prediction 후보인지 판정한다.

    기본 조건:
    - repair_success == True
    - repair_patch가 비어 있지 않음
    """
    repair_success = bool(row.get("repair_success", False))
    repair_patch = str(row.get("repair_patch") or "").strip()
    repair_parse_ok = bool(row.get("repair_parse_ok", False))

    if not repair_success:
        return False

    if not repair_parse_ok:
        return False

    if not repair_patch:
        return False

    return True


def build_repair_prediction_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    step2 repair 결과 row를 harness 입력용 prediction row로 변환한다.

    출력 포맷:
    {
        "instance_id": ...,
        "model_name_or_path": ...,
        "model_patch": ...
    }
    """
    instance_id = row.get("instance_id", "")
    model_name = row.get("model", "")
    repair_patch = str(row.get("repair_patch") or "").strip()

    if not instance_id:
        raise ValueError("Missing instance_id in repair result row")

    if not model_name:
        raise ValueError(f"Missing model in repair result row: instance_id={instance_id}")

    if not repair_patch:
        raise ValueError(f"Missing repair_patch in repair result row: instance_id={instance_id}")

    return {
        "instance_id": instance_id,
        "model_name_or_path": model_name,
        "model_patch": repair_patch,
    }


def collect_repair_predictions(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    repair 결과 row들 중 harness 재평가 가능한 prediction row만 수집한다.
    """
    predictions: List[Dict[str, Any]] = []

    for row in rows:
        if not is_repair_prediction_candidate(row):
            continue
        predictions.append(build_repair_prediction_row(row))

    return predictions


def write_predictions_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    if not path.exists():
        raise FileNotFoundError(f"JSONL file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSONL at {path}:{line_no}: {e}") from e

    return rows


def write_repair_predictions_from_results(
    repair_results_path: Path,
    output_predictions_path: Path,
) -> List[Dict[str, Any]]:
    """
    semantic_repair_results.jsonl을 읽어
    harness 재평가용 repair_predictions.jsonl을 생성한다.

    반환값:
    - 실제로 저장된 prediction row 리스트
    """
    result_rows = load_jsonl(repair_results_path)
    prediction_rows = collect_repair_predictions(result_rows)
    write_predictions_jsonl(output_predictions_path, prediction_rows)
    return prediction_rows