"""
입력:
problem statement
original patch
failing tests
traceback / error summary

출력:
repair prompt 문자열

ver1.
1.“기존 patch를 고쳐라”를 강하게 줌
2. 출력 형식을 unified diff로 고정
3. failure_text를 그대로 넣음

첫째: problem statement 보강
둘째: failure detail 보강

ISSUE : 
- sLM인데, 프롬프트 엔지니어링이 의미 있을까?

"""
from __future__ import annotations

from typing import Dict


DEFAULT_SYSTEM_PROMPT = """You are an expert software repair assistant.

You are given:
1. a bug-fixing task,
2. a previously generated patch,
3. the observed post-harness test failure.

Your job is to REPAIR the existing patch, not to start over from scratch.

Requirements:
- Preserve the original intent of the previous patch when possible.
- Make the minimal necessary change to fix the failing behavior.
- Do not modify unrelated files.
- Return ONLY a valid unified diff patch.
- Do not include markdown fences.
- Do not include explanations.
"""


def _safe_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def build_semantic_repair_user_prompt(row: Dict[str, object]) -> str:
    """
    Build the user prompt for exp2_step2 semantic repair.

    Expected row fields (from step1_result_loader):
    - instance_id
    - repo
    - problem_statement
    - model_patch
    - final_error_type
    - final_signature
    - failure_text
    """
    instance_id = _safe_text(row.get("instance_id"))
    repo = _safe_text(row.get("repo"))
    problem_statement = _safe_text(row.get("problem_statement"))
    model_patch = _safe_text(row.get("model_patch"))
    final_error_type = _safe_text(row.get("final_error_type"))
    final_signature = _safe_text(row.get("final_signature"))
    failure_text = _safe_text(row.get("failure_text"))

    if not model_patch:
        raise ValueError("build_semantic_repair_user_prompt: empty model_patch")

    prompt = f"""You are repairing a previously generated patch for a software engineering task.

[Instance ID]
{instance_id}

[Repository]
{repo}

[Task]
{problem_statement if problem_statement else "(problem statement unavailable)"}

[Previous Patch]
{model_patch}

[Observed Post-Harness Failure]
final_error_type={final_error_type}
final_signature={final_signature}

[Failure Details]
{failure_text if failure_text else "(no additional failure text available)"}

Task:
Repair the previous patch so that it addresses the observed failing behavior.

Instructions:
- Treat this as a semantic repair of the existing patch.
- Reuse the previous patch where possible instead of rewriting everything.
- Make the smallest effective change.
- Keep the patch syntactically valid and applicable.
- Return ONLY a unified diff patch.
"""
    return prompt


def build_semantic_repair_prompt(row: Dict[str, object]) -> Dict[str, str]:
    """
    Returns a chat-style prompt package for repair_agent.

    Output:
    {
        "system_prompt": ...,
        "user_prompt": ...,
    }
    """
    return {
        "system_prompt": DEFAULT_SYSTEM_PROMPT,
        "user_prompt": build_semantic_repair_user_prompt(row),
    }