"""
역할:
- trials.jsonl의 pre-harness 결과 읽기
- harness 결과를 읽어 post-harness taxonomy로 정규화
- 둘을 합쳐 merged_results.jsonl 생성

harness 결과 파일 포맷이 조금 달라도 최대한 안전하게 fallback함.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from exp1_src.taxonomy.taxonomy import ErrorType, Stage, classify_result


PRE_HARNESS_TERMINAL_TYPES = {
    ErrorType.GEN_FAIL.value,
    ErrorType.EDIT_PARSE_FAIL.value,
    ErrorType.REPO_FAIL.value,
    ErrorType.PATCH_FAIL.value,
    ErrorType.APPLY_FAIL.value,
    ErrorType.EXEC_EXCEPTION.value,
    ErrorType.TIMEOUT.value,
}

PRE_HARNESS_READY_TYPE = ErrorType.PRED_READY.value


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows

    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                rows.append(
                    {
                        "_malformed": True,
                        "_source_file": str(path),
                        "_line_no": line_no,
                        "_raw": line,
                        "_error": repr(e),
                    }
                )
    return rows


def _write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _index_latest_trial_per_instance(trial_rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Keep the latest row per instance_id.
    If trial_id exists, prefer max(trial_id). Otherwise last occurrence wins.
    """
    out: Dict[str, Dict[str, Any]] = {}

    for row in trial_rows:
        instance_id = row.get("task_id") or row.get("instance_id")
        if not instance_id:
            continue

        prev = out.get(instance_id)
        if prev is None:
            out[instance_id] = row
            continue

        prev_trial = prev.get("trial_id")
        cur_trial = row.get("trial_id")

        if isinstance(prev_trial, int) and isinstance(cur_trial, int):
            if cur_trial >= prev_trial:
                out[instance_id] = row
        else:
            out[instance_id] = row

    return out


def _index_predictions_by_instance(pred_rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for row in pred_rows:
        instance_id = row.get("instance_id")
        if instance_id:
            out[instance_id] = row
    return out


def _load_harness_reports_by_instance(log_root: Path) -> Dict[str, Dict[str, Any]]:
    """
    Read instance-level SWE-bench report.json files from:

        logs/run_evaluation/<run_id>/<model_name>/<instance_id>/report.json

    Each report.json usually has shape:
        {
          "<instance_id>": {
              "patch_is_None": bool,
              "patch_exists": bool,
              "patch_successfully_applied": bool,
              "resolved": bool,
              "tests_status": {...}
          }
        }
    """
    out: Dict[str, Dict[str, Any]] = {}

    if not log_root.exists():
        return out

    for instance_dir in log_root.iterdir():
        if not instance_dir.is_dir():
            continue

        report_path = instance_dir / "report.json"
        if not report_path.exists():
            continue

        try:
            with report_path.open("r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as e:
            out[instance_dir.name] = {
                "instance_id": instance_dir.name,
                "_malformed": True,
                "_source_file": str(report_path),
                "_error": repr(e),
            }
            continue

        if isinstance(raw, dict):
            for instance_id, payload in raw.items():
                if isinstance(payload, dict):
                    row = dict(payload)
                    row["instance_id"] = instance_id
                    row["_report_path"] = str(report_path)
                    out[instance_id] = row

    return out


def _classify_harness_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert an instance-level SWE-bench report row into canonical taxonomy.

    Current heuristic for SWE-bench report.json:
    - resolved=True -> PASS
    - missing patch / patch None -> OTHER_RUNTIME
    - patch exists but failed to apply -> PATCH_FAIL
    - patch applied but unresolved -> TEST_FAIL
    """
    resolved = bool(row.get("resolved", False))
    patch_is_none = bool(row.get("patch_is_None", False))
    patch_exists = bool(row.get("patch_exists", False))
    patch_applied = bool(row.get("patch_successfully_applied", False))
    tests_status = row.get("tests_status", {})

    if resolved:
        return {
            "success": True,
            "error_type": ErrorType.PASS.value,
            "signature": "resolved",
            "stage": Stage.DONE.value,
            "post_source": "harness",
        }

    if patch_is_none or not patch_exists:
        return {
            "success": False,
            "error_type": ErrorType.OTHER_RUNTIME.value,
            "signature": "missing_patch",
            "stage": Stage.EXEC.value,
            "post_source": "harness",
        }

    if not patch_applied:
        return {
            "success": False,
            "error_type": ErrorType.PATCH_FAIL.value,
            "signature": "apply_patch_fail",
            "stage": Stage.DIFF_EXPORT.value,
            "post_source": "harness",
        }

    # Patch applied successfully but unresolved => semantic failure at TEST stage
    signature = "unresolved_after_apply"

    if isinstance(tests_status, dict):
        fail_to_pass = tests_status.get("FAIL_TO_PASS", {})
        pass_to_pass = tests_status.get("PASS_TO_PASS", {})

        ftp_failures = fail_to_pass.get("failure", []) if isinstance(fail_to_pass, dict) else []
        ptp_failures = pass_to_pass.get("failure", []) if isinstance(pass_to_pass, dict) else []

        if ftp_failures:
            signature = "fail_to_pass_not_fixed"
        elif ptp_failures:
            signature = "pass_to_pass_regression"

    return {
        "success": False,
        "error_type": ErrorType.TEST_FAIL.value,
        "signature": signature,
        "stage": Stage.TEST.value,
        "post_source": "harness",
    }


def merge_harness_results(
    run_dir: Path,
    run_id: str,
    model_name: str,
    trials_filename: str = "trials.jsonl",
    predictions_filename: str = "predictions.jsonl",
    merged_filename: str = "merged_results.jsonl",
) -> Path:
    """
    Merge pre-harness trials with instance-level SWE-bench harness reports.

    Inputs:
    - run_dir/trials.jsonl
    - run_dir/predictions.jsonl
    - logs/run_evaluation/<run_id>/<model_name_slashed_replaced>/<instance_id>/report.json

    Output:
    - run_dir/merged_results.jsonl
    """
    run_dir = Path(run_dir)

    trials_path = run_dir / trials_filename
    predictions_path = run_dir / predictions_filename

    trial_rows = _read_jsonl(trials_path)
    pred_rows = _read_jsonl(predictions_path)

    pre_by_instance = _index_latest_trial_per_instance(trial_rows)
    pred_by_instance = _index_predictions_by_instance(pred_rows)

    log_root = run_dir / "logs" / "run_evaluation" / run_id / model_name.replace("/", "__")
    harness_by_instance = _load_harness_reports_by_instance(log_root)

    all_instance_ids = sorted(set(pre_by_instance) | set(pred_by_instance) | set(harness_by_instance))

    merged_rows: List[Dict[str, Any]] = []

    for instance_id in all_instance_ids:
        pre = dict(pre_by_instance.get(instance_id, {}))
        pred = pred_by_instance.get(instance_id)
        raw_harness = harness_by_instance.get(instance_id)

        base_row: Dict[str, Any] = {}
        if pre:
            base_row.update(pre)
        else:
            base_row["task_id"] = instance_id

        base_row["instance_id"] = instance_id
        base_row["had_prediction"] = pred is not None
        base_row["merged_from_pre"] = bool(pre)
        base_row["merged_from_harness"] = raw_harness is not None

        pre_error_type = pre.get("error_type")
        is_pre_terminal = pre_error_type in PRE_HARNESS_TERMINAL_TYPES
        is_pre_ready = pre_error_type == PRE_HARNESS_READY_TYPE

        # Case 1: pre-harness terminal failure
        if is_pre_terminal:
            normalized_pre = classify_result(pre)
            base_row["final_error_type"] = normalized_pre["error_type"]
            base_row["final_signature"] = normalized_pre["signature"]
            base_row["final_stage"] = normalized_pre["stage"]
            base_row["final_success"] = normalized_pre["success"]
            base_row["final_source"] = "pre_harness"
            merged_rows.append(base_row)
            continue

        # Case 2: prediction ready, so harness decides final outcome
        if is_pre_ready:
            if raw_harness is None:
                base_row["final_error_type"] = ErrorType.OTHER_RUNTIME.value
                base_row["final_signature"] = "missing_harness_result"
                base_row["final_stage"] = Stage.EXEC.value
                base_row["final_success"] = False
                base_row["final_source"] = "merge_guard"
                merged_rows.append(base_row)
                continue

            post = _classify_harness_row(raw_harness)
            base_row["harness_raw"] = raw_harness
            base_row["final_error_type"] = post["error_type"]
            base_row["final_signature"] = post["signature"]
            base_row["final_stage"] = post["stage"]
            base_row["final_success"] = post["success"]
            base_row["final_source"] = "harness"
            merged_rows.append(base_row)
            continue

        # Case 3: pre row exists but is neither terminal nor PRED_READY
        if pre:
            normalized_pre = classify_result(pre)
            base_row["final_error_type"] = normalized_pre["error_type"]
            base_row["final_signature"] = normalized_pre["signature"]
            base_row["final_stage"] = normalized_pre["stage"]
            base_row["final_success"] = normalized_pre["success"]
            base_row["final_source"] = "pre_harness_fallback"
            merged_rows.append(base_row)
            continue

        # Case 4: no pre row, only harness row
        if raw_harness is not None:
            post = _classify_harness_row(raw_harness)
            base_row["harness_raw"] = raw_harness
            base_row["final_error_type"] = post["error_type"]
            base_row["final_signature"] = post["signature"]
            base_row["final_stage"] = post["stage"]
            base_row["final_success"] = post["success"]
            base_row["final_source"] = "harness_only"
            merged_rows.append(base_row)
            continue

        # Case 5: nothing usable found
        base_row["final_error_type"] = ErrorType.OTHER_RUNTIME.value
        base_row["final_signature"] = "missing_pre_and_harness_result"
        base_row["final_stage"] = Stage.EXEC.value
        base_row["final_success"] = False
        base_row["final_source"] = "merge_guard"
        merged_rows.append(base_row)

    merged_path = run_dir / merged_filename
    _write_jsonl(merged_path, merged_rows)
    return merged_path