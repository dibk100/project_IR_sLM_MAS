# 📊 Experiment1-B2-step02-2
- Experiment: B-v2-step2-2 (p0)
- Dataset: SWE-bench Lite
- Model: Qwen2.5-7B-Instruct
- Context: Minimal repository context (file-path candidates only, collected from workspace clone)
    - “repo_path에서 *.py 파일의 상대 경로 목록을 수집하여 repo_context로 주입(파일 내용은 포함하지 않음)”
- Tasks: 200
- Notes:
    - (step2-1 이슈) PATCH에서 구조적으로 막혀서(stage bottleneck) failure landscape가 “PATCH 중심으로 붕괴(collapse)”한 상태
    - Patch Formatter를 추가하여 **PATCH로 넘어가서 죽는 확률을 줄여서 EXEC/TEST로 “넘어가는 전이(transition)”를 만들어내려는 것**이 해당 실험 목적

## Observation (N=200)
    - PATCH_FAIL: 
        - corrupt_patch: 181 -> 172
        - hunk_failed: 5
        - path_missing: 3
    - GEN_FAIL: 9%
        - llm_call_fail : 9
        - invalid_diff_format : 2 -> 11
    - EXEC: ~0%

## 🧠 Interpretation
```
format_reason 최상위:
git_apply_check_exception:name 'subprocess' is not defined 178건
```
→ git apply --check를 “트리거”로 넣었는데, 그 체크 코드에서 subprocess import가 안 돼서 예외가 나고, 그 예외를 “invalid reason”으로 간주해서 formatter를 거의 모든 task에서 호출됨   

> To-Do.
> - P0-핵심 버그 수정 : import subprocess, “exception”은 invalid로 취급하지 말고, 체크를 스킵하거나 별도 시그니처로 기록
> - P0-트리거 위치(로직) 정리 : validate_unified_diff → 통과한 경우에만 → git apply --check