"""
stage (where) / error_type (what) / signature (why/how exactly)
"""
from enum import Enum
from typing import Tuple, Dict, Any, Optional

class ErrorType(str, Enum):
    """
    error_type은 의미 정보(semantic axis)
    즉, failure의 성격 → "이 failure는 어떤 종류의 문제인가?"
    
    ex.
    GEN_FAIL → LLM 자체 문제
    EDIT_PARSE_FAIL → 출력 형식 문제
    APPLY_FAIL → patch application 문제
    TEST_FAIL → semantic bug
    EXEC_FAIL → infra 문제
    
    # ErrorType = 무엇이 (failure class)
    failure의 의미적 타입
    중간 granularity
    policy routing 기준
    """
    # ----------------------------
    # Pre-harness
    # ----------------------------
    PRED_READY = "PRED_READY"   # diff ready for harness input
    GEN_FAIL = "GEN_FAIL"       # API timeout / context length 초과 --> prompt/context/call policy 문제
    EDIT_PARSE_FAIL = "EDIT_PARSE_FAIL"   # JSON 형식 깨짐 / edits 비어 있음 --> output schema enforcement 필요
    REPO_FAIL = "REPO_FAIL"
    PATCH_FAIL = "PATCH_FAIL"   # pre-harness patch materialization / diff export failure
    APPLY_FAIL = "APPLY_FAIL"
    EXEC_EXCEPTION = "EXEC_EXCEPTION"

    # ----------------------------
    # Shared / generic
    # ----------------------------
    TIMEOUT = "TIMEOUT"

    # ----------------------------
    # Post-harness
    # ----------------------------
    PASS = "PASS"               # harness resolved
    INSTALL_FAIL = "INSTALL_FAIL"
    TEST_FAIL = "TEST_FAIL"
    EXEC_FAIL = "EXEC_FAIL"     # docker / harness infra failure
    OTHER_RUNTIME = "OTHER_RUNTIME"


class Stage(str, Enum):
    """
    Stage = 어디서 (structural location)
    pipeline 위치, coarse-grained, policy state로 사용
    
    """
    # Pre-harness
    GEN = "GEN"
    REPO = "REPO"
    EDIT_PARSE = "EDIT_PARSE"
    EDIT_APPLY = "EDIT_APPLY"
    DIFF_EXPORT = "DIFF_EXPORT"

    # Post-harness
    INSTALL = "INSTALL"
    TEST = "TEST"
    EXEC = "EXEC"

    DONE = "DONE"
    UNKNOWN = "UNKNOWN"


def error_type_to_stage(error_type: str) -> str:
    mapping = {
        ErrorType.PRED_READY.value: Stage.DIFF_EXPORT.value,
        ErrorType.GEN_FAIL.value: Stage.GEN.value,
        ErrorType.EDIT_PARSE_FAIL.value: Stage.EDIT_PARSE.value,
        ErrorType.REPO_FAIL.value: Stage.REPO.value,
        ErrorType.PATCH_FAIL.value: Stage.DIFF_EXPORT.value,
        ErrorType.APPLY_FAIL.value: Stage.EDIT_APPLY.value,
        ErrorType.EXEC_EXCEPTION.value: Stage.EXEC.value,
        ErrorType.TIMEOUT.value: Stage.EXEC.value,

        ErrorType.PASS.value: Stage.DONE.value,
        ErrorType.INSTALL_FAIL.value: Stage.INSTALL.value,
        ErrorType.TEST_FAIL.value: Stage.TEST.value,
        ErrorType.EXEC_FAIL.value: Stage.EXEC.value,
        ErrorType.OTHER_RUNTIME.value: Stage.EXEC.value,
    }
    return mapping.get(error_type, Stage.UNKNOWN.value)


# ----------------------------
# Infra / execution detectors
# ----------------------------
def _detect_infra_failure(full_log: str, sig: Optional[str] = None) -> bool:
    s = (full_log or "").lower()
    sig_l = (sig or "").lower()

    if sig_l.startswith("docker_") and sig_l != "docker_nonzero_returncode":
        return True

    infra_patterns = [
        "unable to find image",
        "pull access denied",
        "repository does not exist",
        "docker login",
        "cannot connect to the docker daemon",
        "permission denied: /var/run/docker.sock",
        "tls handshake timeout",
        "connection refused",
        "i/o timeout",
    ]
    return any(p in s for p in infra_patterns)


def _extract_exec_signature(log: str) -> str:
    s = (log or "").lower()
    if "unable to find image" in s or "pull access denied" in s or "repository does not exist" in s:
        return "docker_image_not_found"
    if "docker login" in s:
        return "docker_login_required"
    if "cannot connect to the docker daemon" in s:
        return "docker_daemon_unreachable"
    if "permission denied" in s and "docker.sock" in s:
        return "docker_permission_denied"
    if "tls handshake timeout" in s or "i/o timeout" in s or "connection refused" in s:
        return "docker_network_error"
    return "exec_fail"


# ----------------------------
# Main classifier
# ----------------------------
def classify_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Canonical taxonomy classifier.

    Important:
    - Do NOT relabel EXEC_FAIL -> TEST_FAIL anymore.
    - Pre-harness and post-harness are now separated by pipeline design.
    - This function mainly normalizes stage/signature.
    """
    stderr = result.get("stderr") or ""
    stdout = result.get("stdout") or ""
    returncode = result.get("returncode", 1)
    timeout = bool(result.get("timeout", False))

    et = result.get("error_type")
    sig = result.get("signature")

    if et:
        if timeout:
            et = ErrorType.TIMEOUT.value
            if not sig:
                sig = "timeout"

        stage = error_type_to_stage(et)

        if not sig:
            sig = _infer_signature(stderr, stdout, et, returncode, timeout)

        return {
            "success": et == ErrorType.PASS.value or et == ErrorType.PRED_READY.value,
            "error_type": et,
            "signature": sig,
            "stage": stage,
        }

    et2, sig2 = classify_error(stderr, stdout, returncode, timeout)
    stage2 = error_type_to_stage(et2)
    return {
        "success": et2 == ErrorType.PASS.value or et2 == ErrorType.PRED_READY.value,
        "error_type": et2,
        "signature": sig2,
        "stage": stage2,
    }


def classify_error(stderr: str, stdout: str, returncode: int, timeout: bool = False) -> Tuple[str, str]:
    """
    Conservative fallback classifier.

    This is now mostly for post-harness parsing or defensive fallback.
    Avoid aggressive semantic relabeling.
    """
    if timeout:
        return ErrorType.TIMEOUT.value, "timeout"
    if returncode == 0:
        return ErrorType.PASS.value, "success"

    full_log = ((stderr or "") + "\n" + (stdout or "")).lower()

    # Pre-harness generation-layer failures
    if "maximum context length" in full_log or "reduce the length of the input messages" in full_log:
        return ErrorType.GEN_FAIL.value, "context_length_exceeded"

    if (
        "request timed out" in full_log
        or "apitimeouterror" in full_log
        or "readtimeout" in full_log
    ):
        return ErrorType.GEN_FAIL.value, "llm_timeout"

    if "invalid_edit_script" in full_log or "missing_or_empty_edits" in full_log:
        return ErrorType.EDIT_PARSE_FAIL.value, "invalid_edit_script"

    if "edit_apply_path_missing" in full_log:
        return ErrorType.APPLY_FAIL.value, "edit_apply_path_missing"
    if "edit_apply_range_oob" in full_log or "range_oob" in full_log or "insert_oob" in full_log:
        return ErrorType.APPLY_FAIL.value, "edit_apply_range_oob"
    if "edit_apply_unknown_op" in full_log or "unknown_op" in full_log:
        return ErrorType.APPLY_FAIL.value, "edit_apply_unknown_op"

    if "empty_generated_diff" in full_log or "git_diff_failed" in full_log:
        return ErrorType.PATCH_FAIL.value, _extract_patch_signature(full_log)

    if (
        "repo setup failed" in full_log
        or "git_clone_failed" in full_log
        or "git_fetch_failed" in full_log
        or "git_reset_failed" in full_log
    ):
        return ErrorType.REPO_FAIL.value, _extract_repo_signature(full_log)

    # Post-harness install/runtime failures
    if "editable_install_failed" in full_log:
        return ErrorType.INSTALL_FAIL.value, "editable_install_failed"

    if _detect_infra_failure(full_log):
        return ErrorType.EXEC_FAIL.value, _extract_exec_signature(full_log)

    # Conservative fallback: if it's not clearly infra or install, treat as test/runtime
    return ErrorType.TEST_FAIL.value, _extract_test_signature(full_log)


# ----------------------------
# Signature inference helpers
# ----------------------------
def _infer_signature(stderr: str, stdout: str, error_type: str, returncode: int, timeout: bool) -> str:
    full_log = (stderr or "") + "\n" + (stdout or "")

    if error_type == ErrorType.PRED_READY.value:
        return "ready_for_harness"
    if error_type == ErrorType.GEN_FAIL.value:
        return _extract_gen_signature(full_log)
    if error_type == ErrorType.EDIT_PARSE_FAIL.value:
        return "invalid_edit_script"
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
        return _extract_exec_signature(full_log)
    if error_type == ErrorType.INSTALL_FAIL.value:
        return _extract_install_signature(full_log)
    if error_type == ErrorType.EXEC_EXCEPTION.value:
        return "unhandled_exception"
    if error_type == ErrorType.OTHER_RUNTIME.value:
        return "other_runtime"
    return "unknown"


def _extract_install_signature(log: str) -> str:
    s = (log or "").lower()
    if "editable_install_failed" in s:
        return "editable_install_failed"
    if "modulenotfounderror" in s or "importerror" in s:
        return "install_import_error"
    if "syntaxerror" in s:
        return "install_syntax_error"
    return "install_fail"


def _extract_patch_signature(log: str) -> str:
    s = (log or "").lower()
    if "empty_generated_diff" in s:
        return "empty_generated_diff"
    if "git_diff_failed" in s:
        return "git_diff_failed"
    if "corrupt patch" in s:
        return "git_apply_corrupt_patch"
    if "no such file or directory" in s:
        return "git_apply_path_missing"
    if "patch failed" in s or "hunk" in s:
        return "git_apply_hunk_failed"
    return "patch_fail"


def _extract_repo_signature(log: str) -> str:
    s = (log or "").lower()
    if "git_clone_failed" in s:
        return "git_clone_failed"
    if "git_fetch_failed" in s:
        return "git_fetch_failed"
    if "git_reset_failed" in s or "fatal" in s:
        return "git_reset_failed"
    return "repo_setup_failed"


def _extract_test_signature(log: str) -> str:
    s = (log or "").lower()

    if "modulenotfounderror" in s or "importerror" in s:
        return "dependency_missing"
    if "syntaxerror" in s:
        return "syntax_error"
    if "typeerror" in s:
        return "type_error"
    if "assertionerror" in s or "\nassert " in s:
        return "assertion_fail"
    if "pytest" in s:
        return "pytest_fail"
    if "unittest" in s:
        return "unittest_fail"

    return "test_fail"


def _extract_gen_signature(log: str) -> str:
    s = (log or "").lower()

    if "maximum context length" in s or "reduce the length of the input messages" in s:
        return "context_length_exceeded"
    if "request timed out" in s or "apitimeouterror" in s or "readtimeout" in s:
        return "llm_timeout"
    return "gen_fail"


def _extract_apply_signature(log: str) -> str:
    s = (log or "").lower()
    if "edit_apply_path_missing" in s:
        return "edit_apply_path_missing"
    if "edit_apply_range_oob" in s or "range_oob" in s or "insert_oob" in s:
        return "edit_apply_range_oob"
    if "edit_apply_unknown_op" in s or "unknown_op" in s:
        return "edit_apply_unknown_op"
    return "edit_apply_failed"