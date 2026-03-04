# 📊 Experiment1-Step2-5
- Experiment: B-v2-step2-5
- Dataset: SWE-bench Lite
- Model: Qwen2.5-7B-Instruct
- Tasks: 200
- Notes:
    - run_id : Qwen_exp1-sLMs-qwen2p5-200
    - MAX_MODEL_LEN=32,768 / max_token = 2024 (동적 계산 전략 활용함)


########################아래 수정하기
### 2) 결과
- 3시간 소요 (147개 평가)
    - instance 하나당 평균 소요 시간 : 77.26s/it
- 평가 :
   - ✓ = 테스트 통과 solved (PASS)
   - ✖ = 테스트 실패(evaluated but failed)
   - error = evaluation 자체 실패(harness 실행 실패)

#### Observation (N=147)
   - ✓=1, ✖=145, error=1
   - 07_instance_id.ipynb : 확인


✅ 환경 정상 (docker, dataset, harness OK)    
✅ patch는 적용됨    
✅ 테스트는 실행됨    
❌ 하지만 테스트를 통과하지 못함

→ **모델이 만든 patch는 “문법적으로는 적용 가능”하지만
“버그를 실제로 고치지는 못했다”**

```
EXEC_FAIL (docker_image_not_found) → ✖ (test failed)
```
> patch는 apply 되지만, 문제 해결 실패.   
→ "semantic failure"

환경/하네스 파이프라인은 정상   
모델 패치가 문제를 해결하지 못함(semantic failure)

## Insite
### 현재 실험 :
- 7B 모델
- minimal prompting
- edit-script 방식
- 제한된 context (80 files)

→ 7B single-shot + file list contex

> reasoning 없이/single-shot/repair loop 없음으로 실험함.

## Observation (N=200)
| 구간            | Count |
| ------------- | -- |
| GEN 실패        | 12 |
| EDIT_PARSE 실패 | 7 |
| EDIT_APPLY 실패 | 34 |
| HARNESS 실패(✖) | 147 |
| HARNESS 성공(✓) | 0 |
