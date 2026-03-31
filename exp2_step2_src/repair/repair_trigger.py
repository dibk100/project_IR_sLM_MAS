"""
patch 존재
apply 성공
test 실행됨
resolved 아님
--- 이 조건이면 True.

판정만하는 역할~
"""

from __future__ import annotations

from typing import Dict

try:
    from exp2_step2_src.taxonomy.taxonomy import ErrorType, Stage
except ImportError:
    # 실행 위치에 따라 import 경로가 달라질 수 있으므로 fallback
    from taxonomy.taxonomy import ErrorType, Stage


NON_REPAIRABLE_TEST_SIGNATURES = {
    # semantic repair로 보기 애매한 경우들
    "dependency_missing",
    "syntax_error",
}


def analyze_repair_target(row: Dict[str, object]) -> Dict[str, object]:
    """
    exp2_step2 semantic repair target selector.

    Selection rule:
    - patch가 있어야 함
    - had_prediction == True
    - merged_from_harness == True
    - final_success == False
    - final_stage == TEST
    - final_error_type == TEST_FAIL

    즉, step2는 taxonomy 기준으로
    'post-harness semantic test failure'만 repair 대상으로 삼는다.
    """
    model_patch = str(row.get("model_patch") or "").strip()
    had_prediction = bool(row.get("had_prediction", False))
    merged_from_harness = bool(row.get("merged_from_harness", False))
    final_success = bool(row.get("final_success", False))

    final_stage = str(row.get("final_stage") or "")
    final_error_type = str(row.get("final_error_type") or "")
    final_signature = str(row.get("final_signature") or "")

    if not model_patch:
        return {
            "eligible": False,
            "reason": "empty_patch",
        }

    if not had_prediction:
        return {
            "eligible": False,
            "reason": "no_prediction",
        }

    if final_success:
        return {
            "eligible": False,
            "reason": "already_resolved",
        }

    if not merged_from_harness:
        return {
            "eligible": False,
            "reason": "no_harness_merged",
        }

    if final_stage != Stage.TEST.value:
        return {
            "eligible": False,
            "reason": f"not_test_stage:{final_stage}",
        }

    if final_error_type != ErrorType.TEST_FAIL.value:
        return {
            "eligible": False,
            "reason": f"not_test_fail:{final_error_type}",
        }

    if final_signature in NON_REPAIRABLE_TEST_SIGNATURES:
        return {
            "eligible": False,
            "reason": f"non_repairable_test_signature:{final_signature}",
        }

    return {
        "eligible": True,
        "reason": "semantic_test_failure",
    }


def is_semantic_repair_target(row: Dict[str, object]) -> bool:
    return bool(analyze_repair_target(row)["eligible"])