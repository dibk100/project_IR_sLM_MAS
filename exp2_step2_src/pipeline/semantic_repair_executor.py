"""
흐름 : 
step1 결과 1개 받음
semantic repair 대상인지 확인
repair prompt 생성
model 호출
patch 파싱
harness 재실행용 prediction 생성
결과 기록
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from exp2_step2_src.agent.repair_agent import RepairAgent
from exp2_step2_src.repair.patch_parser import parse_repaired_patch
from exp2_step2_src.repair.prompt_builder import build_semantic_repair_prompt
from exp2_step2_src.repair.repair_trigger import analyze_repair_target

logger = logging.getLogger(__name__)


class SemanticRepairExecutor:
    """
    exp2_step2용 post-harness semantic repair 실행기.

    현재 책임 범위:
    - step1 결과 row를 입력으로 받음
    - semantic repair 대상 여부 판정
    - repair prompt 생성
    - repair agent 호출
    - raw output에서 repaired patch 파싱
    - step2용 result dict 반환

    주의:
    - 실제 harness 재실행은 아직 포함하지 않음
    - 이 단계는 "repair patch 생성 성공 여부"까지 담당
    """

    def __init__(self, repair_agent: RepairAgent):
        self.repair_agent = repair_agent

    def run_on_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """
        step1의 normalized row 하나를 받아 semantic repair를 1회 수행한다.

        반환값은 recorder / 후속 harness 단계에서 바로 쓰기 쉽도록
        최대한 구조화해서 돌려준다.
        """
        instance_id = row.get("instance_id", "unknown")

        logger.info("[SemanticRepairExecutor] start instance_id=%s", instance_id)

        # 1) repair 대상 판정
        trigger_result = analyze_repair_target(row)
        eligible = bool(trigger_result["eligible"])
        trigger_reason = str(trigger_result["reason"])

        if not eligible:
            logger.info(
                "[SemanticRepairExecutor] skip instance_id=%s reason=%s",
                instance_id,
                trigger_reason,
            )
            return self._build_skip_result(row=row, trigger_reason=trigger_reason)

        # 2) prompt 생성
        try:
            prompt_bundle = build_semantic_repair_prompt(row)
            system_prompt = prompt_bundle["system_prompt"]
            user_prompt = prompt_bundle["user_prompt"]
        except Exception as e:
            logger.exception(
                "[SemanticRepairExecutor] prompt_build_failed instance_id=%s exc=%s",
                instance_id,
                type(e).__name__,
            )
            return self._build_failure_result(
                row=row,
                trigger_reason=trigger_reason,
                failure_stage="PROMPT_BUILD",
                failure_reason=repr(e),
            )

        # 3) repair agent 호출
        try:
            raw_output = self.repair_agent.generate_repair_patch(
                task=row,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except Exception as e:
            logger.exception(
                "[SemanticRepairExecutor] repair_call_failed instance_id=%s exc=%s",
                instance_id,
                type(e).__name__,
            )
            return self._build_failure_result(
                row=row,
                trigger_reason=trigger_reason,
                failure_stage="REPAIR_CALL",
                failure_reason=repr(e),
                prompt_bundle=prompt_bundle,
            )

        # 4) repaired patch 파싱
        parsed = parse_repaired_patch(raw_output)
        if not parsed["ok"]:
            logger.info(
                "[SemanticRepairExecutor] patch_parse_failed instance_id=%s reason=%s",
                instance_id,
                parsed["reason"],
            )
            return self._build_failure_result(
                row=row,
                trigger_reason=trigger_reason,
                failure_stage="PATCH_PARSE",
                failure_reason=str(parsed["reason"]),
                prompt_bundle=prompt_bundle,
                raw_output=raw_output,
                parsed_patch=str(parsed.get("patch", "")),
            )

        repaired_patch = str(parsed["patch"])

        logger.info(
            "[SemanticRepairExecutor] success instance_id=%s repaired_patch_chars=%d",
            instance_id,
            len(repaired_patch),
        )

        return {
            # identity
            "instance_id": row.get("instance_id", ""),
            "task_id": row.get("task_id", ""),
            "trial_id": row.get("trial_id"),
            "attempt_index": row.get("attempt_index"),

            # step1 summary
            "repo": row.get("repo", ""),
            "base_commit": row.get("base_commit", ""),
            "model": row.get("model", ""),
            "policy_action": row.get("policy_action", ""),
            "pre_error_type": row.get("pre_error_type", ""),
            "pre_signature": row.get("pre_signature", ""),
            "final_error_type": row.get("final_error_type", ""),
            "final_signature": row.get("final_signature", ""),
            "final_stage": row.get("final_stage", ""),
            "final_success": row.get("final_success", False),

            # trigger / repair status
            "repair_eligible": True,
            "repair_trigger_reason": trigger_reason,
            "repair_attempted": True,
            "repair_success": True,
            "repair_failure_stage": "",
            "repair_failure_reason": "",

            # prompt
            "repair_system_prompt": system_prompt,
            "repair_user_prompt": user_prompt,

            # model output
            "repair_raw_output": raw_output,
            "repair_patch": repaired_patch,
            "repair_parse_ok": True,
            "repair_parse_reason": "ok",
        }

    def _build_skip_result(self, row: Dict[str, Any], trigger_reason: str) -> Dict[str, Any]:
        return {
            "instance_id": row.get("instance_id", ""),
            "task_id": row.get("task_id", ""),
            "trial_id": row.get("trial_id"),
            "attempt_index": row.get("attempt_index"),

            "repo": row.get("repo", ""),
            "base_commit": row.get("base_commit", ""),
            "model": row.get("model", ""),

            "pre_error_type": row.get("pre_error_type", ""),
            "pre_signature": row.get("pre_signature", ""),
            "final_error_type": row.get("final_error_type", ""),
            "final_signature": row.get("final_signature", ""),
            "final_stage": row.get("final_stage", ""),
            "final_success": row.get("final_success", False),

            "repair_eligible": False,
            "repair_trigger_reason": trigger_reason,
            "repair_attempted": False,
            "repair_success": False,
            "repair_failure_stage": "TRIGGER",
            "repair_failure_reason": trigger_reason,

            "repair_system_prompt": "",
            "repair_user_prompt": "",
            "repair_raw_output": "",
            "repair_patch": "",
            "repair_parse_ok": False,
            "repair_parse_reason": "not_attempted",
        }

    def _build_failure_result(
        self,
        row: Dict[str, Any],
        trigger_reason: str,
        failure_stage: str,
        failure_reason: str,
        prompt_bundle: Optional[Dict[str, str]] = None,
        raw_output: str = "",
        parsed_patch: str = "",
    ) -> Dict[str, Any]:
        prompt_bundle = prompt_bundle or {}

        return {
            "instance_id": row.get("instance_id", ""),
            "task_id": row.get("task_id", ""),
            "trial_id": row.get("trial_id"),
            "attempt_index": row.get("attempt_index"),

            "repo": row.get("repo", ""),
            "base_commit": row.get("base_commit", ""),
            "model": row.get("model", ""),

            "pre_error_type": row.get("pre_error_type", ""),
            "pre_signature": row.get("pre_signature", ""),
            "final_error_type": row.get("final_error_type", ""),
            "final_signature": row.get("final_signature", ""),
            "final_stage": row.get("final_stage", ""),
            "final_success": row.get("final_success", False),

            "repair_eligible": True,
            "repair_trigger_reason": trigger_reason,
            "repair_attempted": True,
            "repair_success": False,
            "repair_failure_stage": failure_stage,
            "repair_failure_reason": failure_reason,

            "repair_system_prompt": prompt_bundle.get("system_prompt", ""),
            "repair_user_prompt": prompt_bundle.get("user_prompt", ""),
            "repair_raw_output": raw_output,
            "repair_patch": parsed_patch,
            "repair_parse_ok": False,
            "repair_parse_reason": failure_reason if failure_stage == "PATCH_PARSE" else "not_reached",
        }