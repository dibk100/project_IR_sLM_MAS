"""
raw result를 policy가 읽기 쉬운 state 형태로 바꾸는 파일
executor가 만든 복잡한 result dict에서 policy decision에 필요한 최소 정보만 뽑아내는 역할~~~
"""

def build_state(result: dict) -> dict:
    return {
        "stage": result.get("stage", ""),
        "error_type": result.get("error_type", ""),
        "signature": result.get("signature", ""),
        "success": result.get("success", False),
        "diff_export_ok": result.get("diff_export_ok", False),
    }