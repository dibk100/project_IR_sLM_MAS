# exp2_Step1
- Dataset: SWE-bench Lite
- Tasks: 300
- Exp-Model (7개):
    - Qwen/Qwen2.5-Coder-7B-Instruct **(baseline)**
    - codellama/CodeLlama-7b-Instruct-hf
    - deepseek-ai/deepseek-coder-6.7b-instruct
    - deepseek-ai/deepseek-coder-7b-instruct-v1.5
    - microsoft/Phi-3.5-mini-instruct
    - mistralai/Mistral-7B-Instruct-v0.3
    - meta-llama/Llama-3.1-8B-Instruct

## 📁 Folder Structure
```
exp2_step1_src/
├── policy/
│   ├── state.py
│   ├── rules.py
│   └── controller.py
├── pipeline/
│   └── run_step1.py
├── analysis/
│   └── simulate_step1.py
└── README.md

```

# exp2_step1_src

Step 1 prototype for a failure-aware controller.

## Goal

Implement an initial deterministic policy:

- structural -> repair
- semantic -> no retry (or 1 retry)
- repeated same failure -> abort

## Structure

- `policy/state.py`
  - state abstraction for decision-making

- `policy/rules.py`
  - deterministic failure-aware policy

- `policy/controller.py`
  - execution loop that maps state to action

- `pipeline/run_step1.py`
  - online execution entrypoint using exp1 pipeline adapter

- `analysis/simulate_step1.py`
  - offline policy simulation from exp1 results

## Current status

This is a scaffold, not a fully integrated exp1 execution system yet.

### TODO
1. connect `Exp1RunnerAdapter` to actual `exp1_src` pipeline
2. define real repair actions for structural failures
3. align field names with merged taxonomy outputs
4. add evaluation metrics:
   - resolved rate
   - average attempts
   - abort ratio
   - useless retry reduction