# exp2_step2
- exp2_step2 : policy가 아니라 post-harness repair를 중심으로 한 얇은 확장(**semantic repair**)
      - exp2_step1에서 post-harness로 넘어간 것에 대한 작업
      - 이 단계에서 action은 semantic repair만 있다고 생각하면 됨.
      - step1 결과를 입력으로 받아 semantic repair 1회를 수행하는 post-harness recovery 모듈 설계!
```
(exp2_step1 result)
      ↓
semantic failure만 선택
      ↓
repair 1회 
      ↓
harness 재실행
      ↓
result
```

## 현재 구현된 retry 축.
1. repair patch 생성
python3 -m exp2_step2_src.main_exp2_step2 --config configs/exp2/exp2_step2_base.yaml

2. repair predictions 생성
python3 -m exp2_step2_src.main_exp2_step2_eval --config configs/exp2/exp2_step2_base.yaml

3. repaired patch harness 실행
python3 -m exp2_step2_src.main_exp2_step2_eval_harness --config configs/exp2/exp2_step2_base.yaml

4. repair eval 결과 merge + 요약
python3 -m exp2_step2_src.main_exp2_step2_eval_merge --config configs/exp2/exp2_step2_base.yaml

runs/<step2_run_id>/
├── semantic_repair_results.jsonl
├── repair_predictions.jsonl
├── repair_eval_merged_results.jsonl
├── repair_eval_summary.json
├── eval_harness.log
└── eval_merge.log



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
├── exp2_step2_src/             # exp2_step2 : post-harness semantic repair가 실제로 recovery를 만드는지 검증
│   │
│   ├── main_exp2_step2.py                # repair patch 생성
│   ├── main_exp2_step2_eval.py           # repair patch 재평가(초안필요)
│   │
│   ├── agent/
│   │   ├── repair_agent.py               ### exp2_step1의 generate_agent을 복사해둔 상태
│   │   └── context_collector.py
│   │
│   ├── pipeline/
│   │   ├── diff_materializer.py
│   │   ├── harness_result_merger.py
│   │   └── semantic_repair_executor.py     ## repair 1회 실행하고 재평가까지 orchestration
│   │   └── repaired_prediction_writer.py     ## 초안 필요
│   │
│   ├── repair/                             ## 
│   │   ├── repair_trigger.py               # 어떤 step1 실패가 repair 대상인지 판정
│   │   ├── prompt_builder.py               # failing test, patch, 문제 설명을 묶어 repair prompt 생성
│   │   └── patch_parser.py
│   │
│   ├── data/
│   │   ├── step1_result_loader.py          
│   │   └── recorder.py
│   │
│   ├── taxonomy/
│   │   └── taxonomy.py
│   │

runs/
exp2_qwen2p5_policy_v0_smoke_20260331_120344/
├── logs/
│   └── run_evaluation/

exp2_step2_semantic_repair_v0_smoke100/
├── semantic_repair_results.jsonl
└── semantic_repair_summary.json
```

## 방향
exp1: baseline generation-only
exp2_step1: pre-harness hard-coded policy
exp2_step2: post-harness semantic repair
      - exp2_step2-A: post-harness semantic repair generation 
      - exp2_step2-B: repaired patch harness evaluation ← 지금 여기

exp2_step3: learned policy / adaptive routing