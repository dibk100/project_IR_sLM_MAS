from exp2_step1_src.policy.action_types import PolicyAction

def choose_action(state: dict) -> PolicyAction:
    stage = state.get("stage", "")
    error_type = state.get("error_type", "")
    signature = state.get("signature", "")

    if error_type == "GEN_FAIL" and signature == "context_length_exceeded":
        return PolicyAction.RETRY_TRIM_CONTEXT

    if error_type == "EDIT_PARSE_FAIL":
        return PolicyAction.RETRY_SCHEMA_CONSTRAINED

    if error_type == "APPLY_FAIL":
        return PolicyAction.RETRY_EXPAND_FILES

    if error_type == "PRED_READY":
        return PolicyAction.ACCEPT

    if error_type == "TEST_FAIL":
        return PolicyAction.RETRY_SEMANTIC_REPAIR

    return PolicyAction.ABORT