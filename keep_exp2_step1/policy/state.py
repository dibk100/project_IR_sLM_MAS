from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


STRUCTURAL_FAILURES = {
    "GEN_FAIL",
    "EDIT_PARSE_FAIL",
    "PATCH_FAIL",
    "APPLY_FAIL",
    "REPO_FAIL",
}

SEMANTIC_FAILURES = {
    "TEST_FAIL",
}

INFRA_FAILURES = {
    "EXEC_FAIL",
    "INSTALL_FAIL",
    "TIMEOUT",
    "EXEC_EXCEPTION",
    "OTHER_RUNTIME",
    "HARNESS_MISSING",
}

SUCCESS_TYPES = {
    "PASS",
}


@dataclass
class PolicyState:
    """
    Policy 의사결정을 위한 최소 상태 표현.
    """
    instance_id: str
    stage: str
    failure_type: str
    signature: str
    attempt_idx: int
    repeated_same_failure: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_structural_failure(self) -> bool:
        return self.failure_type in STRUCTURAL_FAILURES

    @property
    def is_semantic_failure(self) -> bool:
        return self.failure_type in SEMANTIC_FAILURES

    @property
    def is_infra_failure(self) -> bool:
        return self.failure_type in INFRA_FAILURES

    @property
    def is_terminal_success(self) -> bool:
        return self.failure_type in SUCCESS_TYPES