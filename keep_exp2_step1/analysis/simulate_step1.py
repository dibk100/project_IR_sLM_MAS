from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List

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
    exp1 merged_results.jsonl 비슷한 row를 받아 PolicyState로 바꾸는 예시.
    실제 필드명에 맞게 수정 필요.
    """
    return PolicyState(
        instance_id=str(row.get("instance_id", "unknown")),
        stage=row.get("stage", "UNKNOWN"),
        failure_type=row.get("error_type", row.get("failure_type", "UNKNOWN")),
        signature=row.get("signature", "unknown_signature"),
        attempt_idx=int(row.get("attempt_idx", 0)),
        repeated_same_failure=bool(row.get("repeated_same_failure", False)),
        metadata=row,
    )


def main() -> None:
    input_path = Path("runs/exp1_qwen2p5_baseline_fin_20260330_184939/merged_results.jsonl")
    rows = read_jsonl(input_path)

    action_counter = Counter()
    failure_counter = Counter()

    for row in rows:
        state = infer_state_from_row(row)
        action = select_action(state)

        action_counter[action.value] += 1
        failure_counter[(state.stage, state.failure_type, state.signature)] += 1

    print("=== Policy Action Distribution ===")
    for action, count in action_counter.most_common():
        print(f"{action}: {count}")

    print("\n=== Top Failure States ===")
    for key, count in failure_counter.most_common(20):
        print(f"{key}: {count}")


if __name__ == "__main__":
    main()