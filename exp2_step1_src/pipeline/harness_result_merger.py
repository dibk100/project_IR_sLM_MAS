from __future__ import annotations
"""
역할:
- trials.jsonl의 pre-harness 결과 읽기
- harness 결과를 읽어 post-harness taxonomy로 정규화
- 둘을 합쳐 merged_results.jsonl 생성

harness 결과 파일 포맷이 조금 달라도 최대한 안전하게 fallback함.
"""
"""
역할:
- trials.jsonl의 pre-harness 결과 읽기
- harness 결과를 읽어 post-harness taxonomy로 정규화
- 둘을 합쳐 merged_results.jsonl 생성

수정 사항:
- logs/run_evaluation 아래의 multi-part harness 결과를 모두 읽을 수 있도록 개선
- run_id exact match뿐 아니라 prefix / contains / model_dir 존재 여부를 기준으로 후보를 수집
"""
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
    instance_id별 최신 row만 유지한다.
    trial_id가 있으면 max(trial_id)를 우선하고, 없으면 마지막 row가 이긴다.
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


def _normalize_run_id_for_matching(run_id: str) -> str:
    """
    run_id 매칭을 조금 느슨하게 하기 위한 정규화.
    예:
    - exp2_step1_policy_v0_smoke300 -> exp2_step1_policy_v0_smoke
    - exp2_step1_policy_v0_smoke100 -> exp2_step1_policy_v0_smoke
    """
    s = str(run_id).strip()
    s = s.replace("-", "_")
    s = s.replace("__", "_")
    return s


def _run_id_prefix_candidates(run_id: str) -> List[str]:
    """
    run_id로부터 prefix 후보를 만든다.
    뒤에 숫자/part suffix가 붙은 실제 harness 디렉토리명을 잡기 위함.
    """
    raw = _normalize_run_id_for_matching(run_id)
    candidates = [raw]

    # trailing digits 제거 버전 추가
    stripped = raw.rstrip("0123456789")
    stripped = stripped.rstrip("_")
    if stripped and stripped not in candidates:
        candidates.append(stripped)

    return candidates


def _resolve_all_log_roots(run_dir: Path, run_id: str, model_name: str) -> List[Path]:
    """
    logs/run_evaluation 아래에서 model 디렉토리가 존재하는 모든 관련 run 디렉토리를 찾는다.

    우선순위:
    1) exact match
    2) startswith(prefix 후보)
    3) contains(prefix 후보)
    4) fallback: model_dir가 있는 모든 디렉토리 (경고성 fallback)

    반환값:
    - [<run_eval_dir>/<matched_run_dir>/<model_dir>, ...]
    """
    model_dir_name = model_name.replace("/", "__")
    base = run_dir / "logs" / "run_evaluation"

    if not base.exists():
        return []

    # 1) exact match
    exact = base / run_id / model_dir_name
    if exact.exists():
        return [exact]

    prefixes = _run_id_prefix_candidates(run_id)

    # helper
    def _valid_model_dir(p: Path) -> bool:
        return p.is_dir() and (p / model_dir_name).exists()

    # 2) startswith(prefix 후보)
    startswith_matches: List[Path] = []
    for p in sorted(base.iterdir()):
        if not p.is_dir():
            continue
        if any(p.name.startswith(prefix) for prefix in prefixes) and _valid_model_dir(p):
            startswith_matches.append(p / model_dir_name)

    if startswith_matches:
        return startswith_matches

    # 3) contains(prefix 후보)
    contains_matches: List[Path] = []
    for p in sorted(base.iterdir()):
        if not p.is_dir():
            continue
        if any(prefix in p.name for prefix in prefixes) and _valid_model_dir(p):
            contains_matches.append(p / model_dir_name)

    if contains_matches:
        return contains_matches

    # 4) fallback: model_dir가 있는 모든 디렉토리
    fallback = sorted(
        p / model_dir_name
        for p in base.iterdir()
        if p.is_dir() and (p / model_dir_name).exists()
    )
    return fallback


def _load_harness_reports_from_single_root(log_root: Path) -> Dict[str, Dict[str, Any]]:
    """
    단일 log_root에서 instance별 report.json를 읽는다.

    기대 경로:
        logs/run_evaluation/<matched_run_id>/<model_name>/<instance_id>/report.json
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
                    row["_log_root"] = str(log_root)
                    out[instance_id] = row

    return out


def _load_harness_reports_by_instance(log_roots: List[Path]) -> Dict[str, Dict[str, Any]]:
    """
    여러 log_root를 순회하며 instance별 harness report를 합친다.

    정책:
    - 동일 instance_id가 여러 root에 등장하면 나중 root가 덮어쓴다.
    - 일반적으로 part0, part1, part2 등은 instance가 겹치지 않을 것이므로 안전하다.
    """
    merged: Dict[str, Dict[str, Any]] = {}

    for log_root in log_roots:
        one = _load_harness_reports_from_single_root(log_root)
        merged.update(one)

    return merged


def _classify_harness_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    instance-level SWE-bench report row를 canonical taxonomy로 변환한다.

    현재 heuristic:
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

    # patch applied successfully but unresolved => semantic failure at TEST stage
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
    pre-harness trials와 instance-level SWE-bench harness reports를 합친다.

    입력:
    - run_dir/trials.jsonl
    - run_dir/predictions.jsonl
    - run_dir/logs/run_evaluation/<matched_run_dir>/<model_name>/<instance_id>/report.json

    출력:
    - run_dir/merged_results.jsonl
    """
    run_dir = Path(run_dir)

    trials_path = run_dir / trials_filename
    predictions_path = run_dir / predictions_filename

    trial_rows = _read_jsonl(trials_path)
    pred_rows = _read_jsonl(predictions_path)

    pre_by_instance = _index_latest_trial_per_instance(trial_rows)
    pred_by_instance = _index_predictions_by_instance(pred_rows)

    log_roots = _resolve_all_log_roots(run_dir, run_id, model_name)
    harness_by_instance = _load_harness_reports_by_instance(log_roots)

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
        base_row["harness_log_roots"] = [str(p) for p in log_roots]

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