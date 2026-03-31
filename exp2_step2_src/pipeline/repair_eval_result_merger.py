from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from exp2_step2_src.taxonomy.taxonomy import ErrorType, Stage


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


def _index_repair_results_by_instance(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    instance_id별 repair result row를 인덱싱한다.
    동일 instance가 여러 번 나오면 마지막 row를 유지한다.
    """
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        instance_id = row.get("instance_id") or row.get("task_id")
        if instance_id:
            out[instance_id] = row
    return out


def _normalize_run_id_for_matching(run_id: str) -> str:
    s = str(run_id).strip()
    s = s.replace("-", "_")
    s = s.replace("__", "_")
    return s


def _run_id_prefix_candidates(run_id: str) -> List[str]:
    raw = _normalize_run_id_for_matching(run_id)
    candidates = [raw]

    stripped = raw.rstrip("0123456789")
    stripped = stripped.rstrip("_")
    if stripped and stripped not in candidates:
        candidates.append(stripped)

    return candidates


def _resolve_all_log_roots(run_dir: Path, eval_run_prefix: str, model_name: str) -> List[Path]:
    """
    step2 repair eval harness 결과 디렉토리들을 모두 찾는다.

    기대 경로 예:
      run_dir/logs/run_evaluation/<eval_run_prefix>_part0/<model_dir>/
      run_dir/logs/run_evaluation/<eval_run_prefix>_part1/<model_dir>/
    """
    model_dir_name = model_name.replace("/", "__")
    base = run_dir / "logs" / "run_evaluation"

    if not base.exists():
        return []

    exact = base / eval_run_prefix / model_dir_name
    if exact.exists():
        return [exact]

    prefixes = _run_id_prefix_candidates(eval_run_prefix)

    def _valid_model_dir(p: Path) -> bool:
        return p.is_dir() and (p / model_dir_name).exists()

    startswith_matches: List[Path] = []
    for p in sorted(base.iterdir()):
        if not p.is_dir():
            continue
        if any(p.name.startswith(prefix) for prefix in prefixes) and _valid_model_dir(p):
            startswith_matches.append(p / model_dir_name)

    if startswith_matches:
        return startswith_matches

    contains_matches: List[Path] = []
    for p in sorted(base.iterdir()):
        if not p.is_dir():
            continue
        if any(prefix in p.name for prefix in prefixes) and _valid_model_dir(p):
            contains_matches.append(p / model_dir_name)

    if contains_matches:
        return contains_matches

    return []


def _load_harness_reports_from_single_root(log_root: Path) -> Dict[str, Dict[str, Any]]:
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
                    row["_log_root"] = str(log_root)
                    out[instance_id] = row

    return out


def _load_harness_reports_by_instance(log_roots: List[Path]) -> Dict[str, Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}

    for log_root in log_roots:
        one = _load_harness_reports_from_single_root(log_root)
        merged.update(one)

    return merged


def _classify_harness_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    SWE-bench report.json row를 step2 eval taxonomy 결과로 변환한다.

    heuristic:
    - resolved=True -> PASS
    - patch missing -> OTHER_RUNTIME
    - patch not applied -> PATCH_FAIL
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


def merge_repair_eval_results(
    run_dir: Path,
    eval_run_prefix: str,
    model_name: str,
    repair_results_filename: str = "semantic_repair_results.jsonl",
    merged_filename: str = "repair_eval_merged_results.jsonl",
) -> Path:
    """
    step2 repair 결과와 repair harness 결과를 merge한다.

    입력:
    - run_dir/semantic_repair_results.jsonl
    - run_dir/logs/run_evaluation/<eval_run_prefix>_part*/<model_name>/<instance_id>/report.json

    출력:
    - run_dir/repair_eval_merged_results.jsonl
    """
    run_dir = Path(run_dir)

    repair_results_path = run_dir / repair_results_filename
    repair_rows = _read_jsonl(repair_results_path)
    repair_by_instance = _index_repair_results_by_instance(repair_rows)

    log_roots = _resolve_all_log_roots(run_dir, eval_run_prefix, model_name)
    harness_by_instance = _load_harness_reports_by_instance(log_roots)

    all_instance_ids = sorted(set(repair_by_instance) | set(harness_by_instance))
    merged_rows: List[Dict[str, Any]] = []

    for instance_id in all_instance_ids:
        repair = dict(repair_by_instance.get(instance_id, {}))
        raw_harness = harness_by_instance.get(instance_id)

        base_row: Dict[str, Any] = {}
        if repair:
            base_row.update(repair)
        else:
            base_row["instance_id"] = instance_id
            base_row["task_id"] = instance_id

        base_row["instance_id"] = instance_id
        base_row["repair_eval_merged_from_repair"] = bool(repair)
        base_row["repair_eval_merged_from_harness"] = raw_harness is not None
        base_row["repair_eval_log_roots"] = [str(p) for p in log_roots]

        if raw_harness is None:
            base_row["repair_eval_final_error_type"] = ErrorType.OTHER_RUNTIME.value
            base_row["repair_eval_final_signature"] = "missing_harness_result"
            base_row["repair_eval_final_stage"] = Stage.EXEC.value
            base_row["repair_eval_final_success"] = False
            base_row["repair_eval_final_source"] = "merge_guard"
            merged_rows.append(base_row)
            continue

        post = _classify_harness_row(raw_harness)
        base_row["repair_eval_harness_raw"] = raw_harness
        base_row["repair_eval_final_error_type"] = post["error_type"]
        base_row["repair_eval_final_signature"] = post["signature"]
        base_row["repair_eval_final_stage"] = post["stage"]
        base_row["repair_eval_final_success"] = post["success"]
        base_row["repair_eval_final_source"] = "harness"

        # before/after 비교를 쉽게 하기 위한 보조 필드
        base_row["before_error_type"] = repair.get("final_error_type", "")
        base_row["before_signature"] = repair.get("final_signature", "")
        base_row["before_stage"] = repair.get("final_stage", "")
        base_row["before_success"] = repair.get("final_success", False)

        merged_rows.append(base_row)

    merged_path = run_dir / merged_filename
    _write_jsonl(merged_path, merged_rows)
    return merged_path