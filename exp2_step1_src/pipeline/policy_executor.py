import hashlib
import time
from pathlib import Path
from typing import Any, Dict, Tuple

from exp2_step1_src.agent.generate_agent import GenerateAgent
from exp2_step1_src.pipeline.diff_materializer import DiffMaterializer
from exp2_step1_src.data.recorder import Recorder
from exp2_step1_src.utils.utils import count_diff_lines
from exp2_step1_src.policy.state_builder import build_state
from exp2_step1_src.policy.rule_policy import choose_action
from exp2_step1_src.policy.action_types import PolicyAction


def _sha256(text: str) -> str:
    """로그 및 재현성 추적용 prompt hash 생성"""
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def _build_task_input(
    task: Dict[str, Any],
    repo_path: Path,
    file_candidates: list[str],
) -> Tuple[Dict[str, Any], bool, int, str]:
    """
    task 정보와 repo context를 합쳐서 실제 sLM 입력(task_in)을 구성

    반환값:
        - task_in: sLM에 들어갈 입력 dict
        - context_used: context 사용 여부
        - context_num_files: context 파일 수
        - repo_context_preview: 로그/기록용 미리보기 문자열
    """
    task_in = dict(task)
    context_used = bool(file_candidates)
    context_num_files = len(file_candidates)
    repo_context_preview = ""

    if context_used:
        injected_context = "Existing files (choose from these):\n" + "\n".join(file_candidates)
        task_in["repo_context"] = injected_context
        task_in["context_num_files"] = context_num_files
        task_in["repo_path"] = str(repo_path)

        preview_lines = ["Existing files (choose from these):"] + file_candidates[:20]
        repo_context_preview = "\n".join(preview_lines)
        if len(file_candidates) > 20:
            repo_context_preview += f"\n... (+{len(file_candidates) - 20} more)"
    else:
        task_in["repo_context"] = ""
        task_in["context_num_files"] = 0
        task_in["repo_path"] = str(repo_path)

    return task_in, context_used, context_num_files, repo_context_preview


def _infer_gen_signature(err_msg: str) -> str:
    """
    generation 예외 메시지를 taxonomy용 signature로 정규화.
    """
    if "maximum context length" in err_msg or "Please reduce the length of the input messages" in err_msg:
        return "context_length_exceeded"
    if "Request timed out" in err_msg or "APITimeoutError" in err_msg:
        return "llm_timeout"
    return "llm_call_fail"


def _make_retry_plan(
    action: str,
    file_candidates: list[str],
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """
    선택된 policy action을 실제 retry 설정으로 변환

    핵심:
        failure state → action → retry plan

    retry plan이 바꾸는 것:
        - retry 시 보여줄 file candidates
        - retry 시 허용할 max_files
        - prompt에 붙일 suffix instruction
        - 어떤 전략이 적용됐는지 나타내는 context_strategy
    """
    policy_cfg = config.get("policy", {}) or {}
    constraints_cfg = config.get("constraints", {}) or {}

    plan = {
        "action": action,
        "retry_max_files": int(constraints_cfg.get("max_files", 2)),
        "retry_file_candidates": list(file_candidates),
        "prompt_suffix": "",
        "context_strategy": "default",
    }

    if action == PolicyAction.RETRY_TRIM_CONTEXT.value:
        trimmed_count = int(policy_cfg.get("trimmed_context_files", 20))
        retry_max_files = int(
            policy_cfg.get("trimmed_max_files", max(1, min(2, trimmed_count)))
        )

        plan["retry_file_candidates"] = list(file_candidates[:trimmed_count])
        plan["retry_max_files"] = retry_max_files
        plan["context_strategy"] = f"trim_top_{trimmed_count}"

    elif action == PolicyAction.RETRY_SCHEMA_CONSTRAINED.value:
        retry_max_files = int(
            policy_cfg.get("schema_retry_max_files", constraints_cfg.get("max_files", 2))
        )
        plan["retry_max_files"] = retry_max_files
        plan["prompt_suffix"] = (
            "\n\n[Retry Instruction]\n"
            "Return ONLY a valid edit script in the exact expected schema.\n"
            "Do not include explanation, markdown fences, or extra text.\n"
            "Every edit must reference an existing file from the provided repository context.\n"
            "Ensure required fields are present and non-empty.\n"
        )
        plan["context_strategy"] = "schema_constrained"

    elif action == PolicyAction.RETRY_EXPAND_FILES.value:
        expanded_count = int(policy_cfg.get("expanded_context_files", 120))
        retry_max_files = int(policy_cfg.get("expanded_max_files", 4))
        expanded = list(file_candidates[:expanded_count])

        plan["retry_file_candidates"] = expanded
        plan["retry_max_files"] = retry_max_files
        plan["prompt_suffix"] = (
            "\n\n[Retry Instruction]\n"
            "Be careful to reference the correct target file path from repository context.\n"
            "Prefer precise file selection before proposing edits.\n"
            "Avoid edits that depend on ambiguous or out-of-range line positions.\n"
        )
        plan["context_strategy"] = f"expand_top_{expanded_count}"

    return plan


def _run_attempt(
    *,
    task: Dict[str, Any],
    repo_path: Path,
    task_id: str,
    trial_id: int,
    attempt_index: int,
    model_name: str,
    seed: int,
    run_ts: str,
    recorder: Recorder,
    logger,
    agent: GenerateAgent,
    materializer: DiffMaterializer,
    config: Dict[str, Any],
    file_candidates: list[str],
    trigger_error_type: str = "",
    trigger_signature: str = "",
    policy_action: str = "INITIAL",
    policy_params: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    단일 attempt 실행 함수.

    흐름:
        1. task + context로 입력 구성
        2. 필요 시 prompt_suffix 적용
        3. generation 수행
        4. materialization 수행
        5. taxonomy-compatible result 생성
        6. recorder에 저장
        7. 결과 반환
    """
    task_in, context_used, context_num_files, repo_context_preview = _build_task_input(
        task=task,
        repo_path=repo_path,
        file_candidates=file_candidates,
    )

    if policy_params and policy_params.get("prompt_suffix"):
        base_problem = task_in.get("problem_statement", "") or ""
        task_in["problem_statement"] = base_problem + policy_params["prompt_suffix"]

    logger.info(
        "Attempt start for %s trial%d attempt%d: action=%s trigger=%s/%s context_num_files=%d",
        task_id,
        trial_id,
        attempt_index,
        policy_action,
        trigger_error_type or "-",
        trigger_signature or "-",
        context_num_files,
    )

    edit_used = True
    edit_parse_ok = False
    edit_parse_reason = ""
    diff_export_ok = False
    diff_export_reason = ""

    t0 = time.time()
    try:
        edit_script = agent.generate_edits(
            task_in,
            max_files=int((policy_params or {}).get("retry_max_files", config.get("constraints", {}).get("max_files", 2))),
        )
    except Exception as e:
        gen_elapsed = time.time() - t0
        err_msg = str(e)
        gen_signature = _infer_gen_signature(err_msg)

        logger.exception(
            "GEN_FAIL for %s trial%d attempt%d: err=%s gen_elapsed=%.2fs context_num_files=%d signature=%s",
            task_id,
            trial_id,
            attempt_index,
            e,
            gen_elapsed,
            context_num_files,
            gen_signature,
        )

        full_result = {
            "task_id": task_id,
            "trial_id": trial_id,
            "attempt_index": attempt_index,
            "model": model_name,
            "prompt_hash": _sha256(
                f"{task.get('repo','')}|{task.get('base_commit','')}|{task.get('problem_statement','')}"
            ),
            "diff": "",
            "edit_script": "",
            "patch_lines_added": 0,
            "patch_lines_removed": 0,
            "files_changed": 0,
            "timestamp": run_ts,
            "seed": seed,
            "repo": task.get("repo"),
            "base_commit": task.get("base_commit"),
            "taxonomy_version": config["experiment"].get("taxonomy_version", "B-v2"),
            "gen_elapsed_sec": gen_elapsed,
            "context_used": context_used,
            "context_num_files": context_num_files,
            "repo_context_preview": repo_context_preview,
            "edit_used": edit_used,
            "edit_parse_ok": False,
            "edit_parse_reason": gen_signature,
            "diff_export_ok": False,
            "diff_export_reason": "",
            "success": False,
            "stage": "GEN",
            "error_type": "GEN_FAIL",
            "signature": gen_signature,
            "stdout": "",
            "stderr": err_msg,
            "returncode": None,
            "timeout": False,
            "elapsed_sec": gen_elapsed,
            "test_command": "",
            "generated_diff": "",
            "exception": repr(e),
            "policy_enabled": True,
            "trigger_error_type": trigger_error_type,
            "trigger_signature": trigger_signature,
            "policy_action": policy_action,
            "policy_params": dict(policy_params or {}),
            "final_selected": False,
            "terminated_by_policy": False,
        }
        recorder.log_trial(full_result)
        return full_result

    gen_elapsed = time.time() - t0

    logger.info("Materializing diff locally for %s trial%d attempt%d ...", task_id, trial_id, attempt_index)
    exec_result = materializer.execute_edits(task_in, edit_script)

    if exec_result.get("error_type") == "EDIT_PARSE_FAIL":
        edit_parse_ok = False
        edit_parse_reason = exec_result.get("signature", "invalid_edit_script")
    elif exec_result.get("stage") == "REPO":
        edit_parse_ok = False
        edit_parse_reason = "not_reached"
    else:
        edit_parse_ok = True
        edit_parse_reason = "ok"

    diff = exec_result.get("generated_diff", "") or ""
    diff_export_ok = bool(diff.strip())

    if diff_export_ok:
        diff_export_reason = "ok"
    else:
        st = exec_result.get("stage", "")
        sig = exec_result.get("signature", "")
        diff_export_reason = f"empty_generated_diff:{st}:{sig}"

    patch_added, patch_removed, files_changed = (
        count_diff_lines(diff) if diff_export_ok else (0, 0, 0)
    )

    logger.info(
        "Pre-harness result for %s trial%d attempt%d: %s (%s), diff_ok=%s, +%d -%d in %d files",
        task_id,
        trial_id,
        attempt_index,
        exec_result.get("error_type"),
        exec_result.get("signature"),
        diff_export_ok,
        patch_added,
        patch_removed,
        files_changed,
    )

    full_result = {
        "task_id": task_id,
        "trial_id": trial_id,
        "attempt_index": attempt_index,
        "model": model_name,
        "prompt_hash": _sha256(
            f"{task.get('repo','')}|{task.get('base_commit','')}|{task.get('problem_statement','')}"
        ),
        "diff": diff,
        "edit_script": edit_script,
        "patch_lines_added": patch_added,
        "patch_lines_removed": patch_removed,
        "files_changed": files_changed,
        "timestamp": run_ts,
        "seed": seed,
        "repo": task.get("repo"),
        "base_commit": task.get("base_commit"),
        "taxonomy_version": config["experiment"].get("taxonomy_version", "B-v2"),
        "gen_elapsed_sec": gen_elapsed,
        "context_used": context_used,
        "context_num_files": context_num_files,
        "repo_context_preview": repo_context_preview,
        "edit_used": edit_used,
        "edit_parse_ok": edit_parse_ok,
        "edit_parse_reason": edit_parse_reason,
        "diff_export_ok": diff_export_ok,
        "diff_export_reason": diff_export_reason,
        "policy_enabled": True,
        "trigger_error_type": trigger_error_type,
        "trigger_signature": trigger_signature,
        "policy_action": policy_action,
        "policy_params": dict(policy_params or {}),
        "final_selected": False,
        "terminated_by_policy": False,
        **exec_result,
    }
    recorder.log_trial(full_result)
    return full_result


def run_policy_attempts(
    *,
    task: Dict[str, Any],
    repo_path: Path,
    task_id: str,
    trial_id: int,
    model_name: str,
    seed: int,
    run_ts: str,
    recorder: Recorder,
    logger,
    agent: GenerateAgent,
    materializer: DiffMaterializer,
    config: Dict[str, Any],
    base_file_candidates: list[str],
) -> Dict[str, Any]:
    """
    exp2_step1의 policy execution 전체를 담당하는 함수.

    흐름:
        1. attempt0 실행 (baseline-style)
        2. result -> state 변환
        3. state 기반 action 선택
        4. retry 필요 시 retry plan 생성 후 attempt1 실행
        5. 최종 결과 반환
    """
    first_result = _run_attempt(
        task=task,
        repo_path=repo_path,
        task_id=task_id,
        trial_id=trial_id,
        attempt_index=0,
        model_name=model_name,
        seed=seed,
        run_ts=run_ts,
        recorder=recorder,
        logger=logger,
        agent=agent,
        materializer=materializer,
        config=config,
        file_candidates=base_file_candidates,
        trigger_error_type="",
        trigger_signature="",
        policy_action="INITIAL",
        policy_params={
            "retry_max_files": int(config.get("constraints", {}).get("max_files", 2)),
            "context_strategy": "default",
            "prompt_suffix": "",
        },
    )

    state = build_state(first_result)
    action = choose_action(state)

    logger.info(
        "Policy decision for %s trial%d after attempt0: error=%s signature=%s action=%s",
        task_id,
        trial_id,
        first_result.get("error_type"),
        first_result.get("signature"),
        action,
    )

    final_result = first_result

    if action.value.startswith("RETRY_"):
        retry_plan = _make_retry_plan(
            action=action.value,
            file_candidates=base_file_candidates,
            config=config,
        )

        retry_candidates = retry_plan["retry_file_candidates"]

        final_result = _run_attempt(
            task=task,
            repo_path=repo_path,
            task_id=task_id,
            trial_id=trial_id,
            attempt_index=1,
            model_name=model_name,
            seed=seed,
            run_ts=run_ts,
            recorder=recorder,
            logger=logger,
            agent=agent,
            materializer=materializer,
            config=config,
            file_candidates=retry_candidates,
            trigger_error_type=first_result.get("error_type", ""),
            trigger_signature=first_result.get("signature", ""),
            policy_action=action.value,
            policy_params=retry_plan,
        )
    else:
        logger.info(
            "No retry for %s trial%d: terminal action=%s",
            task_id,
            trial_id,
            action.value,
        )

    return final_result