from enum import Enum
from typing import Tuple, Dict, Any, Optional

class ErrorType(str, Enum):
    PASS = "PASS"              # (harness resolved)
    GEN_FAIL = "GEN_FAIL"
    REPO_FAIL = "REPO_FAIL"
    PATCH_FAIL = "PATCH_FAIL"
    APPLY_FAIL = "APPLY_FAIL"
    TEST_FAIL = "TEST_FAIL"    # semantic failure (tests ran but did not pass)
    TIMEOUT = "TIMEOUT"
    EXEC_FAIL = "EXEC_FAIL"    # infra / execution-layer failure (docker, daemon, etc.)
    OTHER_RUNTIME = "OTHER_RUNTIME"
    
class Stage(str, Enum):
    GEN = "GEN"
    EDIT_PARSE = "EDIT_PARSE"
    REPO = "REPO"
    PATCH = "PATCH"
    EDIT_APPLY = "EDIT_APPLY"
    DIFF_EXPORT = "DIFF_EXPORT"
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
        # runtime errors (non-infra) are most likely observed during execution;
        # but keep as EXEC to avoid over-claiming "TEST" without a signal.
        ErrorType.OTHER_RUNTIME.value: Stage.EXEC.value,
    }
    return mapping.get(error_type, Stage.UNKNOWN.value)

# ----------------------------
# Infra / execution detectors
# ----------------------------
def _detect_infra_failure(full_log: str, sig: Optional[str] = None) -> bool:
    s = (full_log or "").lower()
    sig_l = (sig or "").lower()

    # If executor already gave a docker_* signature (except the generic nonzero),
    # we treat it as infra.
    if sig_l.startswith("docker_") and sig_l != "docker_nonzero_returncode":
        return True

    infra_patterns = [
        "unable to find image",
        "pull access denied",
        "repository does not exist",
        "docker login",
        "cannot connect to the docker daemon",
        "permission denied",          # often docker.sock
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
    Taxonomy classifier (Exp1 step2-4+):
    - Prefer executor-provided error_type/signature if present.
    - BUT: if executor reports EXEC_FAIL, distinguish infra vs semantic test failure:
        * infra patterns -> EXEC_FAIL
        * otherwise (docker ran, cmd exited non-zero) -> TEST_FAIL
    - Always output a canonical stage derived from error_type (policy-friendly).
    """
    stderr = (result.get("stderr") or "")
    stdout = (result.get("stdout") or "")
    returncode = result.get("returncode", 1)
    timeout = bool(result.get("timeout", False))

    et = result.get("error_type")
    sig = result.get("signature")

    full_log = (stderr or "") + "\n" + (stdout or "")

    if et:
        # Normalize timeout first
        if timeout:
            et = ErrorType.TIMEOUT.value
            if not sig:
                sig = "timeout"

        # Critical relabel: EXEC_FAIL (non-infra) -> TEST_FAIL
        if et == ErrorType.EXEC_FAIL.value and not timeout:
            infra_hit = _detect_infra_failure(full_log, sig)

            if infra_hit:
                et = ErrorType.EXEC_FAIL.value
                if not sig or sig in ("exec_fail", "docker_nonzero_returncode"):
                    sig = _extract_exec_signature(full_log)
            else:
                # Treat as semantic test failure (command ran and exited non-zero)
                et = ErrorType.TEST_FAIL.value
                if not sig or sig in ("docker_nonzero_returncode", "exec_fail"):
                    sig = _extract_test_signature(full_log)

        # Canonical stage: do NOT trust executor stage after relabeling.
        stage = error_type_to_stage(et)

        if not sig:
            sig = _infer_signature(stderr, stdout, et, returncode, timeout)

        return {
            "success": et == ErrorType.PASS.value,
            "error_type": et,
            "signature": sig,
            "stage": stage,
        }

    # Fallback path (executor didn't provide error_type)
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
    Keep it stage-oriented (policy-friendly).
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

    # Repo/setup signals
    if (
        "Repo setup failed" in full_log
        or "git_clone_failed" in full_log
        or "git_fetch_failed" in full_log
        or "git_reset_failed" in full_log
    ):
        return ErrorType.REPO_FAIL.value, _extract_repo_signature(full_log)

    # Distinguish infra exec vs semantic test fail (best-effort)
    if _detect_infra_failure(full_log):
        return ErrorType.EXEC_FAIL.value, _extract_exec_signature(full_log)

    # Otherwise, treat as semantic test failure (most useful bucket for Exp2)
    return ErrorType.TEST_FAIL.value, _extract_test_signature(full_log)

# ----------------------------
# Signature inference helpers
# ----------------------------
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
        return _extract_exec_signature(full_log)
    return "unknown"

def _extract_patch_signature(log: str) -> str:
    s = (log or "")
    if "corrupt patch" in s:
        return "git_apply_corrupt_patch"
    if "No such file or directory" in s:
        return "git_apply_path_missing"
    if "patch failed" in s or "hunk" in s.lower():
        return "git_apply_hunk_failed"
    return "git_apply_failed"


def _extract_repo_signature(log: str) -> str:
    s = (log or "")
    if "git_clone_failed" in s:
        return "git_clone_failed"
    if "git_fetch_failed" in s:
        return "git_fetch_failed"
    if "git_reset_failed" in s or "fatal" in s.lower():
        return "git_reset_failed"
    return "repo_setup_failed"


def _extract_test_signature(log: str) -> str:
    """
    Policy-friendly buckets for semantic failures.
    Keep it stable, but a bit more informative than just pytest/unittest.
    """
    s = (log or "").lower()

    # environment-ish but observed during test execution (still actionable for repair policy)
    if "modulenotfounderror" in s or "importerror" in s:
        return "dependency_missing"
    if "syntaxerror" in s:
        return "syntax_error"
    if "typeerror" in s:
        return "type_error"
    if "assertionerror" in s or "\nassert " in s:
        return "assertion_fail"

    # framework hints
    if "pytest" in s:
        return "pytest_fail"
    if "unittest" in s:
        return "unittest_fail"

    return "test_fail"


def _extract_gen_signature(log: str) -> str:
    if "invalid_edit_script" in log or "missing_or_empty_edits" in log:
        return "invalid_edit_script"
    return "gen_fail"


def _extract_apply_signature(log: str) -> str:
    if "edit_apply_path_missing" in log:
        return "edit_apply_path_missing"
    if "edit_apply_range_oob" in log or "range_oob" in log or "insert_oob" in log:
        return "edit_apply_range_oob"
    if "edit_apply_unknown_op" in log or "unknown_op" in log:
        return "edit_apply_unknown_op"
    return "edit_apply_failed"