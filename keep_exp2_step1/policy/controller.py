from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .rules import Action, select_action
from .state import PolicyState


@dataclass
class AttemptRecord:
    attempt_idx: int
    stage: str
    failure_type: str
    signature: str
    action: str
    raw_result: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EpisodeResult:
    instance_id: str
    final_status: str
    total_attempts: int
    attempts: List[AttemptRecord] = field(default_factory=list)
    final_result: Dict[str, Any] = field(default_factory=dict)


class Step1Controller:
    """
    exp2 step1 정책 실행기.

    이 컨트롤러는 'runner' 객체를 주입받는다.
    runner는 각 task/instance에 대해 1회 실행을 수행하고,
    taxonomy 형태의 결과 dict를 반환한다고 가정한다.

    runner 인터페이스 예시:
        runner.run_once(instance, attempt_idx=0, mode="generate") -> dict
        runner.repair_once(instance, prev_result, attempt_idx=1) -> dict

    result dict 최소 필요 필드:
        {
            "instance_id": "...",
            "stage": "EDIT_PARSE",
            "failure_type": "EDIT_PARSE_FAIL",
            "signature": "invalid_edit_script",
            ...
        }
    """

    def __init__(self, runner: Any, policy_config: Optional[Dict[str, int]] = None, max_attempts: int = 3):
        self.runner = runner
        self.policy_config = policy_config or {}
        self.max_attempts = max_attempts

    def _build_state(
        self,
        instance_id: str,
        result: Dict[str, Any],
        attempt_idx: int,
        prev_result: Optional[Dict[str, Any]] = None,
    ) -> PolicyState:
        stage = result.get("stage", "UNKNOWN")
        failure_type = result.get("failure_type", "UNKNOWN")
        signature = result.get("signature", "unknown_signature")

        repeated_same_failure = False
        if prev_result is not None:
            repeated_same_failure = (
                prev_result.get("stage") == stage
                and prev_result.get("failure_type") == failure_type
                and prev_result.get("signature") == signature
            )

        return PolicyState(
            instance_id=instance_id,
            stage=stage,
            failure_type=failure_type,
            signature=signature,
            attempt_idx=attempt_idx,
            repeated_same_failure=repeated_same_failure,
            metadata={"raw_result": result},
        )

    def run_instance(self, instance: Dict[str, Any]) -> EpisodeResult:
        instance_id = str(instance.get("instance_id", instance.get("task_id", "unknown_instance")))

        attempts: List[AttemptRecord] = []
        prev_result: Optional[Dict[str, Any]] = None
        current_result: Optional[Dict[str, Any]] = None

        for attempt_idx in range(self.max_attempts):
            if attempt_idx == 0:
                current_result = self.runner.run_once(instance=instance, attempt_idx=attempt_idx, mode="generate")
            else:
                # 직전 policy action을 보고 적절한 경로로 실행
                # current_result는 직전 루프에서 업데이트되어야 하므로 여기서는 prev_result 기준으로 분기
                raise RuntimeError("Internal control flow error: follow-up action should execute inside loop tail.")

            state = self._build_state(
                instance_id=instance_id,
                result=current_result,
                attempt_idx=attempt_idx,
                prev_result=prev_result,
            )
            action = select_action(state, self.policy_config)

            attempts.append(
                AttemptRecord(
                    attempt_idx=attempt_idx,
                    stage=state.stage,
                    failure_type=state.failure_type,
                    signature=state.signature,
                    action=action.value,
                    raw_result=current_result,
                )
            )

            if action == Action.ACCEPT:
                return EpisodeResult(
                    instance_id=instance_id,
                    final_status="RESOLVED",
                    total_attempts=attempt_idx + 1,
                    attempts=attempts,
                    final_result=current_result,
                )

            if action == Action.ABORT:
                return EpisodeResult(
                    instance_id=instance_id,
                    final_status="ABORTED",
                    total_attempts=attempt_idx + 1,
                    attempts=attempts,
                    final_result=current_result,
                )

            prev_result = current_result

            if attempt_idx + 1 >= self.max_attempts:
                break

            if action == Action.RETRY:
                current_result = self.runner.run_once(
                    instance=instance,
                    attempt_idx=attempt_idx + 1,
                    mode="retry",
                    prev_result=prev_result,
                )
            elif action == Action.REPAIR:
                current_result = self.runner.repair_once(
                    instance=instance,
                    prev_result=prev_result,
                    attempt_idx=attempt_idx + 1,
                )
            else:
                return EpisodeResult(
                    instance_id=instance_id,
                    final_status="ABORTED",
                    total_attempts=attempt_idx + 1,
                    attempts=attempts,
                    final_result=current_result,
                )

            state = self._build_state(
                instance_id=instance_id,
                result=current_result,
                attempt_idx=attempt_idx + 1,
                prev_result=prev_result,
            )
            action = select_action(state, self.policy_config)

            attempts.append(
                AttemptRecord(
                    attempt_idx=attempt_idx + 1,
                    stage=state.stage,
                    failure_type=state.failure_type,
                    signature=state.signature,
                    action=action.value,
                    raw_result=current_result,
                )
            )

            if action == Action.ACCEPT:
                return EpisodeResult(
                    instance_id=instance_id,
                    final_status="RESOLVED",
                    total_attempts=attempt_idx + 2,
                    attempts=attempts,
                    final_result=current_result,
                )

            if action == Action.ABORT:
                return EpisodeResult(
                    instance_id=instance_id,
                    final_status="ABORTED",
                    total_attempts=attempt_idx + 2,
                    attempts=attempts,
                    final_result=current_result,
                )

            prev_result = current_result

        return EpisodeResult(
            instance_id=instance_id,
            final_status="MAX_ATTEMPTS_REACHED",
            total_attempts=len(attempts),
            attempts=attempts,
            final_result=current_result or {},
        )