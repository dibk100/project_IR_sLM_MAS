from enum import Enum

"""
역할 : policy가 선택할 수 있는 action의 집합을 정의하는 파일

"""

class PolicyAction(str, Enum):
    ACCEPT = "ACCEPT"
    ABORT = "ABORT"
    RETRY_TRIM_CONTEXT = "RETRY_TRIM_CONTEXT"
    RETRY_SCHEMA_CONSTRAINED = "RETRY_SCHEMA_CONSTRAINED"
    RETRY_EXPAND_FILES = "RETRY_EXPAND_FILES"
    RETRY_SEMANTIC_REPAIR = "RETRY_SEMANTIC_REPAIR"