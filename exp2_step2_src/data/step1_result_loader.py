from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


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
                print(f"[WARN] JSON decode error at {path}:{line_no} -> {e}")

    return rows


def _first_non_empty(row: Dict[str, Any], keys: List[str], default: Any = "") -> Any:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue

        if isinstance(value, str):
            if value.strip():
                return value
        else:
            return value

    return default


def _extract_patch(row: Dict[str, Any]) -> str:
    """
    step2 repair의 입력 patch.
    generated_diff를 우선 사용하고, 없으면 diff, stdout 순으로 fallback.
    """
    return _first_non_empty(
        row,
        ["generated_diff", "diff", "stdout"],
        default="",
    )


def _extract_problem_statement(row: Dict[str, Any]) -> str:
    """
    현재 merged_results.jsonl 샘플에는 problem statement가 직접 없을 수 있음.
    일단 fallback을 두고, 없으면 빈 문자열로 둔다.
    나중에 task_loader와 join 필요 시 확장 가능.
    """
    return _first_non_empty(
        row,
        ["problem_statement", "problem", "issue_text", "prompt"],
        default="",
    )


def _extract_failure_text(row: Dict[str, Any]) -> str:
    """
    prompt_builder에서 바로 참고할 수 있게 failure-related text를 모아둔다.
    현재 merged_results 샘플 기준으로는 stderr / exception / taxonomy fields 위주.
    """
    parts: List[str] = []

    candidate_keys = [
        "stderr",
        "exception",
        "final_signature",
        "final_error_type",
        "signature",
        "error_type",
    ]

    for key in candidate_keys:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(f"[{key}] {value.strip()}")

    return "\n".join(parts)


def normalize_step1_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    exp2_step2가 사용하기 쉬운 schema로 step1 merged row를 정규화한다.
    """
    return {
        # identity
        "instance_id": row.get("instance_id") or row.get("task_id") or "",
        "task_id": row.get("task_id") or row.get("instance_id") or "",
        "trial_id": row.get("trial_id"),
        "attempt_index": row.get("attempt_index"),

        # repo / model
        "repo": row.get("repo", ""),
        "base_commit": row.get("base_commit", ""),
        "model": row.get("model", ""),
        "timestamp": row.get("timestamp", ""),

        # task text
        "problem_statement": _extract_problem_statement(row),

        # patch
        "model_patch": _extract_patch(row),
        "edit_script": row.get("edit_script", ""),
        "had_prediction": bool(row.get("had_prediction", False)),
        "files_changed": row.get("files_changed", 0),
        "patch_lines_added": row.get("patch_lines_added", 0),
        "patch_lines_removed": row.get("patch_lines_removed", 0),

        # pre-harness taxonomy
        "pre_success": bool(row.get("success", False)),
        "pre_stage": row.get("stage", ""),
        "pre_error_type": row.get("error_type", ""),
        "pre_signature": row.get("signature", ""),

        # step1 policy metadata
        "policy_action": row.get("policy_action", ""),
        "trigger_error_type": row.get("trigger_error_type", ""),
        "trigger_signature": row.get("trigger_signature", ""),

        # merged post-harness taxonomy
        "merged_from_pre": bool(row.get("merged_from_pre", False)),
        "merged_from_harness": bool(row.get("merged_from_harness", False)),
        "final_error_type": row.get("final_error_type", ""),
        "final_signature": row.get("final_signature", ""),
        "final_stage": row.get("final_stage", ""),
        "final_success": bool(row.get("final_success", False)),
        "final_source": row.get("final_source", ""),

        # repair/prompt convenience
        "failure_text": _extract_failure_text(row),

        # raw backup
        "raw_row": row,
    }


def find_step1_run_dir(project_root: Path, run_name: str) -> Path:
    """
    runs/<run_name> 를 찾는다.
    exact match가 없으면 startswith 기반으로 후보를 찾는다.
    """
    runs_dir = project_root / "runs"
    if not runs_dir.exists():
        raise FileNotFoundError(f"runs directory not found: {runs_dir}")

    exact = runs_dir / run_name
    if exact.exists() and exact.is_dir():
        return exact

    candidates = sorted(
        p for p in runs_dir.iterdir()
        if p.is_dir() and p.name.startswith(run_name)
    )

    if len(candidates) == 1:
        return candidates[0]

    if len(candidates) > 1:
        raise RuntimeError(
            f"Multiple run directories matched '{run_name}': {[p.name for p in candidates]}"
        )

    raise FileNotFoundError(f"No run directory matched: {run_name}")


def load_step1_results_from_run_dir(run_dir: Path) -> List[Dict[str, Any]]:
    """
    merged_results.jsonl를 우선 사용하고,
    없으면 trials.jsonl을 fallback으로 사용한다.
    """
    merged_path = run_dir / "merged_results.jsonl"
    trials_path = run_dir / "trials.jsonl"

    if merged_path.exists():
        raw_rows = _read_jsonl(merged_path)
        source = merged_path
    elif trials_path.exists():
        raw_rows = _read_jsonl(trials_path)
        source = trials_path
    else:
        raise FileNotFoundError(
            f"Neither merged_results.jsonl nor trials.jsonl found in {run_dir}"
        )

    print(f"[INFO] loaded {len(raw_rows)} rows from {source}")
    return [normalize_step1_row(row) for row in raw_rows]


def load_step1_results(project_root: str | Path, run_name: str) -> List[Dict[str, Any]]:
    project_root = Path(project_root)
    run_dir = find_step1_run_dir(project_root, run_name)
    return load_step1_results_from_run_dir(run_dir)