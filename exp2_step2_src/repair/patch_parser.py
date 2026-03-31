"""
모델 출력 후처리.

역할:

raw output에서 patch 추출
빈 출력, malformed diff 처리

"""
from __future__ import annotations

import re
from typing import Dict


DIFF_START_MARKERS = (
    "diff --git ",
    "--- ",
)


def _strip_code_fences(text: str) -> str:
    text = text.strip()

    # ```diff ... ```
    fenced_block = re.search(r"```(?:diff|patch)?\s*\n(.*?)```", text, flags=re.DOTALL)
    if fenced_block:
        return fenced_block.group(1).strip()

    # fence가 있지만 닫힘이 이상한 경우 대비
    text = re.sub(r"^```(?:diff|patch)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text.strip())
    return text.strip()


def _extract_diff_region(text: str) -> str:
    """
    첫 번째 unified diff 블록을 추출한다.
    우선 'diff --git' 시작을 찾고,
    없으면 '--- ' 시작을 fallback으로 사용한다.
    """
    text = text.strip()
    if not text:
        return ""

    start_idx = -1
    for marker in DIFF_START_MARKERS:
        idx = text.find(marker)
        if idx != -1:
            start_idx = idx
            break

    if start_idx == -1:
        return ""

    text = text[start_idx:]

    # 다음 diff 블록이 있으면 첫 블록까지만 사용
    next_diff_idx = text.find("\ndiff --git ", 1)
    if next_diff_idx != -1:
        text = text[:next_diff_idx]

    return text.strip()


def _looks_like_unified_diff(text: str) -> bool:
    """
    Very lightweight validation.
    """
    if not text.strip():
        return False

    has_git_header = "diff --git " in text
    has_file_headers = "--- " in text and "+++ " in text
    has_hunk_header = "@@ " in text or "\n@@ " in text

    if has_git_header and has_file_headers:
        return True

    if has_file_headers and has_hunk_header:
        return True

    return False


def parse_repaired_patch(raw_output: str) -> Dict[str, object]:
    """
    Parse repair-agent output into a unified diff patch.

    Returns:
    {
        "ok": bool,
        "patch": str,
        "reason": str,
        "raw_output": str,
    }
    """
    raw_output = raw_output or ""
    stripped = raw_output.strip()

    if not stripped:
        return {
            "ok": False,
            "patch": "",
            "reason": "empty_output",
            "raw_output": raw_output,
        }

    no_fence = _strip_code_fences(stripped)
    diff_text = _extract_diff_region(no_fence)

    if not diff_text:
        return {
            "ok": False,
            "patch": "",
            "reason": "diff_start_not_found",
            "raw_output": raw_output,
        }

    if not _looks_like_unified_diff(diff_text):
        return {
            "ok": False,
            "patch": diff_text,
            "reason": "invalid_unified_diff",
            "raw_output": raw_output,
        }

    return {
        "ok": True,
        "patch": diff_text.strip() + "\n",
        "reason": "ok",
        "raw_output": raw_output,
    }


def extract_patch_or_raise(raw_output: str) -> str:
    parsed = parse_repaired_patch(raw_output)
    if not parsed["ok"]:
        raise ValueError(f"Failed to parse repaired patch: {parsed['reason']}")
    return str(parsed["patch"])