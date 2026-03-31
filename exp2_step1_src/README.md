# exp2_policy_v0
- exp2_step1 : pre-harness failure-aware retry가 실제로 작동하는지 검증하는 것
- task → generate → (policy) → retry/abort → harness → result
- 목적 : 
    - 작동하는 최초의 policy system 구축 및 실험
    - exp2_step1의 범위 : Pre-harness failure-aware policy만 구현
        - 대상 상태 : GEN_FAIL,EDIT_PARSE_FAIL,APPLY_FAIL,PRED_READY
- Policy v0 :
    - GEN_FAIL/context_length_exceeded
        - action: context file 수 줄여서 1회 재시도
    - EDIT_PARSE_FAIL
        - action: 더 강한 output schema prompt로 1회 재생성
    - APPLY_FAIL/edit_apply_path_missing
        - action: 더 많은 file candidate 제공 후 1회 재생성
    - APPLY_FAIL/edit_apply_range_oob
        - action: 동일 파일 수 유지 + “exact line replacement 금지” 류 지침 추가 후 1회 재생성
    - PRED_READY
        - action: harness로 전달
    - 그 외
        - action: abort

## 현재 구현된 retry 축.
main_exp2.py(_make_retry_plan 함수로 구현)
- GEN_FAIL/context_length_exceeded → context 축소(context trimming)
- EDIT_PARSE_FAIL → schema 강화(schema-constrained regeneration)
- APPLY_FAIL → file grounding 확장

## 📊 Observation (N=50)
- Dataset: SWE-bench Lite
- Model : Qwen/Qwen2.5-Coder-7B-Instruct **(baseline)**

| category                                       | count | total | 
| ------------------------------------------- | --------- | -------- |
| initial PRED_READY at attempt0              | 36       | 50       | 
| APPLY_FAIL → PRED_READY          | 2       | 10       | 
| EDIT_PARSE_FAIL → PRED_READY          | 1       | 3       | 

## Summary.
**exp2_step1 takeaway**
- hard-coded pre-harness policy는 실제로 동작했다
- structural failure의 일부는 recovery 가능했다
- 그러나 recovery는 제한적이었다
- 따라서 pre-harness만으로는 부족하고 post-harness 개입이 필요하다

## 📁 Folder Structure
```
├── exp2_step1_src/
│   │
│   ├── main_exp2_step1.py          # 수정중
│   │
│   ├── agent/
│   │   ├── generate_agent.py
│   │   └── context_collector.py
│   │
│   ├── pipeline/
│   │   ├── diff_materializer.py
│   │   ├── harness_result_merger.py
│   │   └── policy_executor.py      # policy 적용 orchestration 계층            # action execution
│   │
│   ├── policy/                     # state → action 결정 계층
│   │   ├── rule_policy.py          # 무슨 action을 고를지 결정(decision rule)
│   │   ├── action_types.py         # 고를 수 있는 action 이름의 표준 목록(action space)
│   │   └── state_builder.py        # raw result를 policy가 읽기 쉬운 state 형태로 바꾸는 파일(state abstraction)
│   │
│   ├── data/
│   │   ├── task_loader.py
│   │   └── recorder.py
│   │
│   ├── taxonomy/
│   │   └── taxonomy.py
│   │
│   └── utils/
│       └── utils.py
```

## 방향
- exp1: baseline generation-only
- exp2_step1: pre-harness hard-coded policy
    - task → generate → (policy) → retry/abort → harness → result
- exp2_step2: post-harness semantic repair
    - → harness까지 간 뒤 드러난 TEST_FAIL을 대상으로, 기존 patch를 수정해 recovery 시도
- exp2_step3: learned policy / adaptive routing
    - → step1, step2에서 관찰된 failure pattern을 바탕으로 policy를 hand-coded가 아니라 learned/adaptive하게 확장 시도