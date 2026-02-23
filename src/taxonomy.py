from enum import Enum
import re
from typing import Tuple, Dict, Any

class ErrorType(str, Enum):
    PASS = "PASS"
    GEN_FAIL = "GEN_FAIL"
    REPO_FAIL = "REPO_FAIL"
    PATCH_FAIL = "PATCH_FAIL"
    APPLY_FAIL = "APPLY_FAIL"  # step2-4 (edit apply failures)
    TEST_FAIL = "TEST_FAIL"
    TIMEOUT = "TIMEOUT"
    EXEC_FAIL = "EXEC_FAIL"
    OTHER_RUNTIME = "OTHER_RUNTIME"  # 마지막 fallback

class Stage(str, Enum):
    GEN = "GEN"
    EDIT_PARSE = "EDIT_PARSE"   # step2-4
    REPO = "REPO"
    PATCH = "PATCH"
    EDIT_APPLY = "EDIT_APPLY"   # step2-4
    DIFF_EXPORT = "DIFF_EXPORT" # step2-4 (git diff export)
    EXEC = "EXEC"
    TEST = "TEST"
    DONE = "DONE"
    UNKNOWN = "UNKNOWN"

def error_type_to_stage(error_type: str) -> str:
    mapping = {
        ErrorType.PASS.value: Stage.DONE.value,
        ErrorType.GEN_FAIL.value: Stage.EDIT_PARSE.value,
        ErrorType.REPO_FAIL.value: Stage.REPO.value,
        ErrorType.PATCH_FAIL.value: Stage.PATCH.value,
        ErrorType.APPLY_FAIL.value: Stage.EDIT_APPLY.value,
        ErrorType.TIMEOUT.value: Stage.EXEC.value,
        ErrorType.EXEC_FAIL.value: Stage.EXEC.value,
        ErrorType.TEST_FAIL.value: Stage.TEST.value,
        ErrorType.OTHER_RUNTIME.value: Stage.EXEC.value,            # fallback runtime errors almost always occur during execution inside docker
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
        # Prefer executor-provided stage if present (most faithful to pipeline)
        stage = result.get("stage") or error_type_to_stage(et)
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

    # Edit-script parse signals (step2-4)
    if "invalid_edit_script" in full_log or "missing_or_empty_edits" in full_log:
        return ErrorType.GEN_FAIL.value, "invalid_edit_script"

    # Edit apply signals (step2-4)
    if "edit_apply_path_missing" in full_log:
        return ErrorType.APPLY_FAIL.value, "edit_apply_path_missing"
    if "edit_apply_range_oob" in full_log or "range_oob" in full_log or "insert_oob" in full_log:
        return ErrorType.APPLY_FAIL.value, "edit_apply_range_oob"
    if "edit_apply_unknown_op" in full_log or "unknown_op" in full_log:
        return ErrorType.APPLY_FAIL.value, "edit_apply_unknown_op"

    # Patch-level signals
    if "Git Apply Failed:" in full_log or "error: corrupt patch" in full_log:
        return ErrorType.PATCH_FAIL.value, _extract_patch_signature(full_log)

    # Repo/setup signals (if you log those)
    if "Repo setup failed" in full_log or "git_clone_failed" in full_log or "git_fetch_failed" in full_log or "git_reset_failed" in full_log:
        return ErrorType.REPO_FAIL.value, _extract_repo_signature(full_log)

    return ErrorType.OTHER_RUNTIME.value, "unknown_runtime_error"

def _infer_signature(stderr: str, stdout: str, error_type: str, returncode: int, timeout: bool) -> str:
    full_log = (stderr or "") + "\n" + (stdout or "")
    if error_type == ErrorType.GEN_FAIL.value:
        return _extract_gen_signature(full_log)
    if error_type == ErrorType.APPLY_FAIL.value:
        return _extract_apply_signature(full_log)
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

def _extract_gen_signature(log: str) -> str:
    # step2-4: JSON parsing / schema mismatch
    if "invalid_edit_script" in log or "missing_or_empty_edits" in log:
        return "invalid_edit_script"
    return "gen_fail"

def _extract_apply_signature(log: str) -> str:
    # step2-4: apply failures (stable buckets)
    if "edit_apply_path_missing" in log:
        return "edit_apply_path_missing"
    if "edit_apply_range_oob" in log or "range_oob" in log or "insert_oob" in log:
        return "edit_apply_range_oob"
    if "edit_apply_unknown_op" in log or "unknown_op" in log:
        return "edit_apply_unknown_op"
    return "edit_apply_failed"
