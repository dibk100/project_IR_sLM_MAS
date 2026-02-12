# src/taxonomy.py
from enum import Enum
import re
from typing import Tuple, Dict, Any

class ErrorType(str, Enum):
    PASS = "PASS"
    GEN_FAIL = "GEN_FAIL"
    REPO_FAIL = "REPO_FAIL"
    PATCH_FAIL = "PATCH_FAIL"
    TEST_FAIL = "TEST_FAIL"
    TIMEOUT = "TIMEOUT"
    EXEC_FAIL = "EXEC_FAIL"
    OTHER_RUNTIME = "OTHER_RUNTIME"  # 마지막 fallback

class Stage(str, Enum):
    GEN = "GEN"
    REPO = "REPO"
    PATCH = "PATCH"
    EXEC = "EXEC"
    TEST = "TEST"
    DONE = "DONE"
    UNKNOWN = "UNKNOWN"

def error_type_to_stage(error_type: str) -> str:
    mapping = {
        ErrorType.PASS.value: Stage.DONE.value,
        ErrorType.GEN_FAIL.value: Stage.GEN.value,
        ErrorType.REPO_FAIL.value: Stage.REPO.value,
        ErrorType.PATCH_FAIL.value: Stage.PATCH.value,
        ErrorType.TIMEOUT.value: Stage.EXEC.value,
        ErrorType.EXEC_FAIL.value: Stage.EXEC.value,
        ErrorType.TEST_FAIL.value: Stage.TEST.value,
        ErrorType.OTHER_RUNTIME.value: Stage.UNKNOWN.value,
    }
    return mapping.get(error_type, Stage.UNKNOWN.value)

def classify_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    B-v2 classifier:
    - Prefer executor-provided error_type/signature if present.
    - Otherwise infer from stdout/stderr/returncode/timeout.
    - Always attach `stage` as policy-friendly abstraction.
    """
    stderr = (result.get("stderr") or "")
    stdout = (result.get("stdout") or "")
    returncode = result.get("returncode", 1)
    timeout = bool(result.get("timeout", False))

    # 1) If executor already set error_type/signature, trust it.
    et = result.get("error_type")
    sig = result.get("signature")

    if et:
        stage = error_type_to_stage(et)
        if not sig:
            sig = _infer_signature(stderr, stdout, et, returncode, timeout)
        return {
            "success": et == ErrorType.PASS.value,
            "error_type": et,
            "signature": sig,
            "stage": stage,
        }

    # 2) Otherwise infer (fallback path)
    et2, sig2 = classify_error(stderr, stdout, returncode, timeout)
    stage2 = error_type_to_stage(et2)
    return {
        "success": et2 == ErrorType.PASS.value,
        "error_type": et2,
        "signature": sig2,
        "stage": stage2,
    }

def classify_error(stderr: str, stdout: str, returncode: int, timeout: bool = False) -> Tuple[str, str]:
    """
    Fallback classifier when executor didn't provide error_type.
    Keep it stage-oriented (B-v2).
    """
    if timeout:
        return ErrorType.TIMEOUT.value, "timeout"
    if returncode == 0:
        return ErrorType.PASS.value, "success"

    full_log = (stderr or "") + "\n" + (stdout or "")

    # Patch-level signals
    if "Git Apply Failed:" in full_log or "error: corrupt patch" in full_log:
        return ErrorType.PATCH_FAIL.value, _extract_patch_signature(full_log)

    # Repo/setup signals (if you log those)
    if "Repo setup failed" in full_log or "git_clone_failed" in full_log or "git_fetch_failed" in full_log or "git_reset_failed" in full_log:
        return ErrorType.REPO_FAIL.value, _extract_repo_signature(full_log)

    # Test-level signals (very rough)
    if re.search(r"\bFAIL\b|\bFAILED\b|AssertionError", full_log):
        return ErrorType.TEST_FAIL.value, _extract_test_signature(full_log)

    return ErrorType.OTHER_RUNTIME.value, "unknown_runtime_error"

def _infer_signature(stderr: str, stdout: str, error_type: str, returncode: int, timeout: bool) -> str:
    full_log = (stderr or "") + "\n" + (stdout or "")
    if error_type == ErrorType.PATCH_FAIL.value:
        return _extract_patch_signature(full_log)
    if error_type == ErrorType.REPO_FAIL.value:
        return _extract_repo_signature(full_log)
    if error_type == ErrorType.TEST_FAIL.value:
        return _extract_test_signature(full_log)
    if error_type == ErrorType.TIMEOUT.value:
        return "timeout"
    if error_type == ErrorType.EXEC_FAIL.value:
        return "exec_fail"
    return "unknown"

def _extract_patch_signature(log: str) -> str:
    # keep minimal, stable
    if "corrupt patch" in log:
        return "git_apply_corrupt_patch"
    if "No such file or directory" in log:
        return "git_apply_path_missing"
    if "patch failed" in log or "hunk" in log.lower():
        return "git_apply_hunk_failed"
    return "git_apply_failed"

def _extract_repo_signature(log: str) -> str:
    # stable repo setup buckets
    if "git_clone_failed" in log:
        return "git_clone_failed"
    if "git_fetch_failed" in log:
        return "git_fetch_failed"
    if "git_reset_failed" in log or "fatal" in log.lower():
        return "git_reset_failed"
    return "repo_setup_failed"

def _extract_test_signature(log: str) -> str:
    # stable and minimal: do not overfit to framework
    if "pytest" in log.lower():
        return "pytest_fail"
    if "unittest" in log.lower():
        return "unittest_fail"
    return "test_fail"
