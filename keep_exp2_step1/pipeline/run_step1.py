from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from exp2_step1_src__keep.policy.rules import select_action
from exp2_step1_src__keep.policy.state import PolicyState


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def infer_state_from_row(row: Dict[str, Any]) -> PolicyState:
    """
    merged_results.jsonl row -> PolicyState

    우선순위:
    1) final_* 필드를 사용해 최종 상태를 해석
    2) structural pre-harness failure면 pre-harness error_type 사용
    3) PRED_READY인데 harness 결과가 없으면 HARNESS_MISSING으로 처리
    """

    instance_id = str(row.get("instance_id", row.get("task_id", "unknown")))

    pre_stage = row.get("stage", "UNKNOWN")
    pre_error_type = row.get("error_type", "UNKNOWN")
    pre_signature = row.get("signature", "unknown_signature")

    final_stage = row.get("final_stage")
    final_error_type = row.get("final_error_type")
    final_signature = row.get("final_signature")
    final_success = bool(row.get("final_success", False))

    merged_from_harness = bool(row.get("merged_from_harness", False))

    # 1) 최종 성공
    if final_success or final_error_type == "PASS":
        stage = "DONE"
        failure_type = "PASS"
        signature = "success"

    # 2) post-harness final taxonomy 결과가 있으면 우선 사용
    elif final_error_type in {
        "TEST_FAIL",
        "INSTALL_FAIL",
        "EXEC_FAIL",
        "OTHER_RUNTIME",
        "TIMEOUT",
        "EXEC_EXCEPTION",
    }:
        stage = final_stage or "UNKNOWN"
        failure_type = final_error_type
        signature = final_signature or "unknown_signature"

    # 3) pre-harness structural failure
    elif pre_error_type in {
        "GEN_FAIL",
        "EDIT_PARSE_FAIL",
        "PATCH_FAIL",
        "APPLY_FAIL",
        "REPO_FAIL",
    }:
        stage = pre_stage
        failure_type = pre_error_type
        signature = pre_signature

    # 4) harness-ready였지만 실제 harness 결과가 병합되지 않은 경우
    elif pre_error_type == "PRED_READY" and not merged_from_harness:
        stage = final_stage or "EXEC"
        failure_type = "HARNESS_MISSING"
        signature = final_signature or "missing_harness_result"

    # 5) harness-ready인데 final taxonomy가 없는 경우
    elif pre_error_type == "PRED_READY":
        stage = pre_stage
        failure_type = "PRED_READY"
        signature = pre_signature

    # 6) fallback
    else:
        stage = final_stage or pre_stage or "UNKNOWN"
        failure_type = final_error_type or pre_error_type or "UNKNOWN"
        signature = final_signature or pre_signature or "unknown_signature"

    attempt_idx = int(row.get("attempt_idx", 0))

    # merged_results 단일 row 기준으론 반복 실패 여부를 알기 어려워서 False
    repeated_same_failure = False

    return PolicyState(
        instance_id=instance_id,
        stage=stage,
        failure_type=failure_type,
        signature=signature,
        attempt_idx=attempt_idx,
        repeated_same_failure=repeated_same_failure,
        metadata=row,
    )


def main() -> None:
    input_path = Path("runs/exp1_qwen2p5_baseline_fin_20260330_184939/merged_results.jsonl")
    rows = read_jsonl(input_path)

    action_counter = Counter()
    failure_counter = Counter()
    signature_counter = Counter()
    stage_counter = Counter()
    model_action_counter = Counter()

    for row in rows:
        state = infer_state_from_row(row)
        action = select_action(state)

        action_counter[action.value] += 1
        failure_counter[state.failure_type] += 1
        signature_counter[(state.failure_type, state.signature)] += 1
        stage_counter[state.stage] += 1

        model_name = row.get("model", "unknown_model")
        model_action_counter[(model_name, action.value)] += 1

    print("=== Policy Action Distribution ===")
    for action, count in action_counter.most_common():
        print(f"{action}: {count}")

    print("\n=== Failure Type Distribution ===")
    for failure_type, count in failure_counter.most_common():
        print(f"{failure_type}: {count}")

    print("\n=== Stage Distribution ===")
    for stage, count in stage_counter.most_common():
        print(f"{stage}: {count}")

    print("\n=== Top Failure Signatures ===")
    for (failure_type, signature), count in signature_counter.most_common(20):
        print(f"{failure_type} | {signature}: {count}")

    print("\n=== Per-Model Action Distribution ===")
    grouped = {}
    for (model_name, action), count in model_action_counter.items():
        grouped.setdefault(model_name, {})
        grouped[model_name][action] = count

    for model_name in sorted(grouped.keys()):
        print(f"\n[{model_name}]")
        for action, count in sorted(grouped[model_name].items()):
            print(f"  {action}: {count}")


if __name__ == "__main__":
    main()