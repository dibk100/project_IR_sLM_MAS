# project_IR_sLM_MAS 🚀
- **Type**: 개인 연구 프로젝트 (Independent Research)
- **Subject**: OpenSourec sLM 기반 자율 에이전트 시스템 제어 구조 연구
- **Focus**: open-source 기반 sLM 환경에서, 코드 편집/수정 task를 대상으로 Multi-Agent 구조의 orchestration-policy 설계
- **Area** : Agentic AI **(Software Analysis, sLM for Software Engineering)**

## 🚀 Notes & Issues
- ISSUE : vllm-version, torch-version 재설정
  - export VLLM_DISABLE_COMPILE=1

- ISSUE : vLLM-setting (Done : 2026-02-12)
    - (상황) vLLM 서버를 안 띄운 상태에서도 GEN_FAIL이 llm_call_fail이 아니라 empty_diff로 찍힘.
    - “요청이 실패해서 예외가 난” 게 아니라, agent.generate()가 예외 없이 돌아왔는데 결과(diff)가 비어 있었다는 의미
        > “서버를 띄우면 PATCH가 나오고, 안 띄우면 GEN 100% empty_diff”
- ISSUE : SWE-bench Evaluation (Done : 2026-03-16)
    - (상황) Local에서 sLM이 Diff생성 및 수정한 생성물을 Local로 Execute 진행하며 오류가 계속 발생했었고, Harness평가(SWE-bench)에서 정확한 결과를 뽑아낼 수 없었음 .
        > exp1_baseline을 새로 구축함. Local에서는 edit_script로 생성시키고, 실제 실행은 Harness로 넘김.
- ISSUE : vLLM-setting (Done : 2026-03-17)
    - (상황) 300task를 실험하며, Harness 평가할 때, 사용하지 않은 Docker Image가 쌓이면서 터지는 상황이 보임(확실하지는 않음).
        > Harness 평가 시, 100task씩 청크로 나눠서 진행함. 100task 끝나면 도커 이미지 지우고 재실행(단점: 시간이 엄청 소요됨.)

## 📊 Experiment Log
- **exp1 - Failure Measurement**
  - B-v1. raw failure landscape (Status: Completed 2026.02.12)
  - B-v2. stage-structured abstraction
      - step1 : structural collapse (Done : 2026.02.13)
      - step2-A : minimal context TEST (Done : 2026.02.13)
      - step2-B : diff structural failure (Done : 2026.02.13) -> PATCH collapse
      - step2-2 : solution : single sLM 2-call (Done : 2026.02.17) -> single sLM X 근거 수집
      - step2-3 : solution : Always-Formatter (Done : 2026.02.18) 
      - step2-4 : Baseline 구축 완료(Done : 2026.02.24)
      - step2-5 : 번외 실험(other sLMs)(Done : 2026.03.04 끝내기)
- **pre_exp2 - Refactoring**
  - rollback_exp1_fin_v1 : 기존 baseline의 이슈 수정 및 재구축(2026.03.16)
      - sLMs-<model_name>-300 : 300task로 sLMs 재실험
- **exp2 - policy design**
  - (exp1: baseline generation-only)
  - exp2_step1: structural/pre-harness hard-coded policy
  - exp2_step2: semantic/post-harness semantic repair (진행중)
  - exp2_step3: learned policy / adaptive routing

## 📁 Folder Structure
```
project_IR_sLM_MAS/
│
├── configs/
│   └── exp1/
│       ├── exp1_base.yaml
│       └── ...
│
├── data/
│   └── swe_bench_lite_test.jsonl
│
├── exp1_src/
│   │
│   ├── main_exp1.py                # orchestration (generate-only)
│   │
│   ├── agent/
│   │   ├── generate_agent.py
│   │   └── context_collector.py
│   │
│   ├── pipeline/
│   │   ├── diff_materializer.py   # (기존 executor.py)
│   │   └── harness_result_merger.py
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
│
├── exp2_step1_src/             # exp2_step1 : pre-harness failure-aware retry가 실제로 작동하는지 검증하는 것
│   │
│   ├── main_exp2_step1.py          
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
│
├── exp2_step2_src/             # exp2_step2 : post-harness semantic repair가 실제로 recovery를 만드는지 검증
│   │
│   ├── main_exp2_step2.py
│   │
│   ├── agent/
│   │   ├── repair_agent.py
│   │   └── context_collector.py
│   │
│   ├── pipeline/
│   │   ├── semantic_repair_executor.py
│   │   ├── harness_result_merger.py
│   │   └── diff_materializer.py
│   │
│   ├── repair/
│   │   ├── repair_trigger.py
│   │   ├── prompt_builder.py
│   │   └── patch_parser.py
│   │
│   ├── data/
│   │   ├── task_loader.py
│   │   ├── step1_result_loader.py
│   │   └── recorder.py
│   │
│   ├── taxonomy/
│   │   └── taxonomy.py
│   │
│   └── utils/
│       └── utils.py
│
├── workspace/                   # ← repo clone되는 곳 (diff 생성용)
│   ├── repo1__name/
│   ├── repo2__name/
│   └── ...
│
├── runs/
│   └── exp1_<run_name>_<timestamp>/
│       ├── experiment.log
│       ├── config_snapshot.yaml
│       ├── trials.jsonl            # ← pre-harness 결과 (recorder)
│       ├── predictions.jsonl       # ← (harness input)
│       │   └── predictions_chunk_0.jsonl   # Docker_image 이슈로 100task로 나눠서 진행하게 코드수정함
│       │
│       ├── logs/                   # ← run_harness 결과 (자동 생성)
│       │   ├── build_images        # instance별 결과
│       │   └── run_evaluation      # ← run_harness 결과
│       │
│       └── merged_results.jsonl    # 
│
├── runs_archive/                   # paper용으로 기록 저장해둔 폴더
│   ├── exp1_baseline_before/       # baseline 구축되는 과정
│   └── ...
│
│
└── README.md

```
<!--

## Research Question
- H1 : sLM 기반 code agent에서는 단순 retry보다 error-aware orchestration이 더 높은 복구 성공률을 보인다.
- H2 : 코드 생성보다 코드 수정(repair)이 sLM 환경에서 비용 대비 효율이 높다.
- H3 : 일정 실패 횟수 이후 abort는 전체 시스템 비용을 줄이면서 성공률 손실을 최소화한다.

## To-Do :
- Experiment 1. sLM Code Agent Failure
- Experiment 2. Orchestration Policy Comparison

## 📚 Research Landscape :
1. LLM Agent System(prompt-based) : 
    - ReAct: Synergizing Reasoning and Acting in Language Models(ICLR 2023)
    - Toolformer: Language Models Can Teach Themselves to Use Tools(NeurIPS 2023)
    - Self-Refine: Iterative Refinement with Self-Feedback(NeurIPS 2023)
2. LLM-based Multi-Agent System (task : Code Generation)
    - MetaGPT: Meta Programming for Multi-Agent Collaborative Framework(ICLR 2024)
3. LLM-based Software Engineering Tasks (Code Repair & Patching)
   - SWE-bench: Can Language Models Resolve Real-World GitHub Issues?(ICLR 2023)

## Project Structure
project/
  configs/
    exp1.yaml
  data/
    swe_bench_lite_test.jsonl
  src/
    main_exp1.py
    task_loader.py
    generate_agent.py
    executor.py
    verifier.py
    recorder.py
    taxonomy.py
    utils.py
  runs/
    exp1_YYYYMMDD_HHMMSS/
      config_snapshot.yaml
      results.csv
      traces/
        <task_id>_trial1.json
        <task_id>_trial1.stdout.txt
        <task_id>_trial1.stderr.txt
        <task_id>_trial1.patch.diff
      artifacts/
        ... (필요시)

작업 순서
(amla) dibaeck@diserver:~/workspace/project_IR_sLM_MAS/scripts$ ./start_vllm.sh
curl http://localhost:8000/v1/models  # 모델 확인
python3 scripts/check_vllm.py



-->