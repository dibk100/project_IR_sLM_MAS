# 📊 Experiment1-B2-step02-2
- Experiment: B-v2-step2-2 (p0) - 버그 수정본
- Dataset: SWE-bench Lite
- Model: Qwen2.5-7B-Instruct
- Tasks: 200
- Notes:
    - (step2-1 이슈) PATCH에서 구조적으로 막혀서(stage bottleneck) failure landscape가 “PATCH 중심으로 붕괴(collapse)”한 상태
    - Patch Formatter를 추가하여 **PATCH로 넘어가서 죽는 확률을 줄여서 EXEC/TEST로 “넘어가는 전이(transition)”를 만들어내려는 것**이 해당 실험 목적
    - P0-핵심 버그 수정 : import subprocess, “exception”은 invalid로 취급하지 말고, 체크를 스킵하거나 별도 시그니처로 기록
    - P0-트리거 위치(로직) 정리 : validate_unified_diff → 통과한 경우에만 → git apply --check
    - _bucket_git_apply_check 함수 추가하여 git apply --check 오류 유형 쪼갬

## Observation (N=200)
    - PATCH_FAIL 187: 
        - corrupt_patch: 181 -> 172 -> 178
        - hunk_failed: 5 -> -> 6
        - path_missing: 3
    - GEN_FAIL: 
        - llm_call_fail : 9
        - invalid_diff_format : 2 -> 11 -> 4
    - EXEC: ~0%


## 🧠 Insite
```
corrupt_patch: 178 / 187  
corrupt_patch with formatter_used: 178
```
→ formatter는 거의 모든 케이스에 호출됐지만 실질적으로 patch 구조를 고치지 못했다.


이건 정책 문제도 아니고, trigger 문제도 아니고, bucket 문제도 아님

> **같은 sLM으로 생성 → 같은 sLM으로 포맷 정규화**
> = 거의 같은 분포를 재생산


→ 모델이 구조를 이해 못하는데 같은 모델에게 “조금 더 정리해줘”라고 해봤자 근본적 구조 복원은 어렵다.

# Step02-2 End
Next-step...