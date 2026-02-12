# 📊 Experiment1-B2-step02-A
- Experiment: B-v2-step2-1 (minimal context)
- Dataset: SWE-bench Lite
- Model: Qwen2.5-7B-Instruct
- Context: Minimal repository context (file-path candidates only, collected from workspace clone)
    - “repo_path에서 *.py 파일의 상대 경로 목록을 수집하여 repo_context로 주입(파일 내용은 포함하지 않음)”
- Tasks: 200
- Notes:
    - context_collector.py : Executor를 분해하지 말고, ContextCollector를 별도 모듈로 추가하여 최소 수정 실험

## Observation (N=200)
    - PATCH_FAIL: 94%
        - corrupt_patch: 181
        - hunk_failed: 5
        - path_missing: 3
    - GEN_FAIL: 9%
        - llm_call_fail : 9
        - invalid_diff_format : 2
    - EXEC: ~0%

## Insite
- Minimal file-list context does not improve EXEC entry rate
- Failure dominated by structural diff corruption
- Stage bottleneck remains PATCH

## 🧠 Interpretation
1. Minimal file-list context does NOT meaningfully increase EXEC entry rate.
2. 대부분의 실패는 unified diff structure 자체가 깨짐 (corrupt_patch)
3. 파일 존재 여부는 일부 개선되었으나 (path_missing 소수), hunk alignment 문제는 여전히 발생
    
> “파일을 모르기 때문”이 아니라 diff formatting 자체의 structural instability

## 🔧 What changed from Step01?
**Step01**:
- 입력 = problem_statement only
- 모델은 repo 구조를 전혀 모름

**Step02-A**:
- problem_statement + Repository file list (lightweight context injection)
- 목적:
    - 존재하지 않는 파일 수정 시도 감소
    - 잘못된 diff header 감소
    - PATCH stage 통과율 증가

>> semantic reasoning을 늘린 것이 아니라
>> structural validity를 돕기 위한 최소한의 context 주입

## 🔍 Structural Insight
Step02-A는 다음 가설을 검증하기 위한 실험:
> “PATCH 실패는 repository ignorance 때문인가?”

결과 : No - structural diff generation 자체가 근본 병목이다.

```
Failure bottleneck = context 부족이 아니라
                     diff formatting instability

```