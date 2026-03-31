from __future__ import annotations

from enum import Enum
from typing import Dict

from .state import (
    PolicyState,
    STRUCTURAL_FAILURES,
    SEMANTIC_FAILURES,
    INFRA_FAILURES,
    SUCCESS_TYPES,
)


class Action(str, Enum):
    RETRY = "retry"
    REPAIR = "repair"
    ABORT = "abort"
    ACCEPT = "accept"


DEFAULT_CONFIG: Dict[str, int] = {
    # semantic(TEST_FAIL)에 대해 1회 retry 허용
    "max_semantic_retries": 1,
}


def select_action(state: PolicyState, config: Dict[str, int] | None = None) -> Action:
    """
    Step 1 policy:
    - structural -> repair
    - semantic(TEST_FAIL) -> retry 1회 후 abort
    - infra/runtime -> abort
    - success(PASS) -> accept
    - repeated same failure -> abort
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}

    if state.failure_type in SUCCESS_TYPES:
        return Action.ACCEPT

    # 현재 merged_results 한 줄만으로 repeated_same_failure를 정확히 알기 어렵지만,
    # future trace-level extension을 위해 규칙은 유지한다.
    if state.repeated_same_failure:
        return Action.ABORT

    if state.failure_type in INFRA_FAILURES:
        return Action.ABORT

    if state.failure_type in STRUCTURAL_FAILURES:
        return Action.REPAIR

    if state.failure_type in SEMANTIC_FAILURES:
        if state.attempt_idx < cfg["max_semantic_retries"]:
            return Action.RETRY
        return Action.ABORT

    # intermediate / unknown / pred_ready-only 등은 우선 abort
    return Action.ABORT