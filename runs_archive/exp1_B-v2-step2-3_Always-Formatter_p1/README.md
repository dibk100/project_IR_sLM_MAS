# 📊 Experiment1-B2-step02-3
- Experiment: B-v2-step2-3 (p1) - Always-Formatter Canonical Diff
- Dataset: SWE-bench Lite
- Model: Qwen2.5-7B-Instruct
- Tasks: 200
- Notes:
    - (step2-1 이슈) PATCH에서 구조적으로 막혀서(stage bottleneck) failure landscape가 “PATCH 중심으로 붕괴(collapse)”한 상태
    - Patch Formatter를 추가하여 **PATCH로 넘어가서 죽는 확률을 줄여서 EXEC/TEST로 “넘어가는 전이(transition)”를 만들어내려는 것**이 해당 실험 목적
    - P1 - 구조 변경 : Always-Formatter Canonical Diff(항상 formatter → apply-check)

## 1️⃣ Observation (N=200) : Stage 분포
    - PATCH_FAIL 0: 

    - GEN_FAIL **200**: 
        - invalid_diff_format: 189
        - llm_call_fail : 9
        - invalid_diff_format : 2
    - EXEC: ~0%
→ PATCH 단계 자체가 사라짐.

→ 모든 patch가 executor까지 가지 못하고 apply-check 또는 formatter 단계에서 걸림.
```
GEN → FORMAT → APPLY_CHECK → (여기서 다 죽음)
```

## 2️⃣ Formatter 성능
```
formatter_used: 191
formatter_success: 186
success_rate_given_used ≈ 97%
```
→ 겉으로 보면 formatter는 매우 잘 작동하는 것처럼 보임

## 3️⃣ apply_check_reason 분석
```
상위 실패 이유 : 
error: corrupt patch at line XX
```
→ formatter가 unified diff “형태”는 맞췄지만 git apply는 여전히 corrupt 판정

# 🧠 Insite
step2-2구조 :
```
generator → (validate 통과) → apply-check → 일부 PATCH_FAIL
```

**step2-3구조 :** 
```
generator → formatter (항상) →validate → apply-check → 실패 → GEN_FAIL로 기록
```
PATCH_FAIL이 GEN_FAIL로 “위치 이동”했을 뿐, 본질적인 corrupt 문제는 그대로

>  Formatter는 "문자열 정규화"만 하고 있음
> > diff가 깨지는 원인은 “표현 형식”이 아니라   
> > “구조적/semantic 정합성” 문제라는 강한 증거

# 결론 :
step2-3은    
✔ unified diff format 문제를 제거하는 통제 실험   
❌ corrupt 문제 해결 실패
