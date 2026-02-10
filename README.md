# project_IR_sLM_MAS 🚀
- **Type**: 개인 연구 프로젝트 (Independent Research)
- **Subject**: OpenSourec sLM 기반 자율 에이전트 시스템 제어 구조 연구
- **Focus**: open-source 기반 sLM 환경에서, 코드 편집/수정 task를 대상으로 Multi-Agent 구조의 orchestration 및 policy 설계

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
    swebench_subset.jsonl
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