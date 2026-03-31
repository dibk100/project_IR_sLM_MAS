# exp1_Baseline
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

## 🚀 Exp1 : Setting UP
0. conda activate (name)

1. vllm setting
    ```  
    (name)~/workspace/project_IR_sLM_MAS$./scripts/start_vllm.sh <model_name>
    ```
2. experiment setting
    ```  
    (name)~/workspace/project_IR_sLM_MAS$python3 -m src.main_exp1 --config configs/exp1/exp1_<model_name>.yaml
    ```


## 📊 Observation (N=300)

| model                                       | submitted | resolved | unresolved | error |
| ------------------------------------------- | --------- | -------- | ---------- | ----- |
| Qwen/Qwen2.5-Coder-7B-Instruct              | 217       | 2        | 212        | 3     |
| codellama/CodeLlama-7b-Instruct-hf          | 187       | 0        | 187        | 0     |
| deepseek-ai/deepseek-coder-6.7b-instruct    | 204       | 2        | 198        | 4     |
| deepseek-ai/deepseek-coder-7b-instruct-v1.5 | 185       | 1        | 182        | 2     |
| microsoft/Phi-3.5-mini-instruct             | 203       | 1        | 200        | 2     |
| meta-llama/Llama-3.1-8B-Instruct                        | 230       | 1        | 220        | 9     |
| mistralai/Mistral-7B-Instruct-v0.3          | 175       | 1        | 171        | 3     |

<details>
<summary><strong>Qwen/Qwen2.5-Coder-7B-Instruct</strong></summary>

### 1) Pre-Harness Filtering (Generation / Edit 단계)

| stage        | error_type       | signature                   | count | ratio (%) |
|--------------|-----------------|-----------------------------|-------|-----------|
| DIFF_EXPORT  | PRED_READY      | ready_for_harness           | 217   | 72.33     |
| EDIT_APPLY   | APPLY_FAIL      | edit_apply_path_missing     | 57    | 19.00     |
| EDIT_PARSE   | EDIT_PARSE_FAIL | invalid_edit_script         | 11    | 3.67      |
| EDIT_APPLY   | APPLY_FAIL      | edit_apply_range_oob        | 10    | 3.33      |
| GEN          | GEN_FAIL        | context_length_exceeded     | 5     | 1.67      |

---

### 2) Harness Evaluation Results

| metric                  | value |
|------------------------|-------|
| total_instances        | 300   |
| submitted_instances    | 217   |
| completed_instances    | 214   |
| resolved_instances     | 2     |
| unresolved_instances   | 212   |
| empty_patch_instances  | 0     |
| error_instances        | 3     |

</details>
<details>
<summary><strong>codellama/CodeLlama-7b-Instruct-hf</strong></summary>

### 1) Pre-Harness Filtering (Generation / Edit 단계)

| stage        | error_type       | signature                   | count | ratio (%) |
|--------------|-----------------|-----------------------------|-------|-----------|
| DIFF_EXPORT  | PRED_READY      | ready_for_harness           | 187   | 62.33     |
| EDIT_PARSE   | EDIT_PARSE_FAIL | invalid_edit_script         | 46    | 15.33     |
| EDIT_APPLY   | APPLY_FAIL      | edit_apply_path_missing     | 44    | 14.67     |
| GEN          | GEN_FAIL        | context_length_exceeded     | 13    | 4.33      |
| EDIT_APPLY   | APPLY_FAIL      | edit_apply_range_oob        | 9     | 3.00      |
| DIFF_EXPORT  | PATCH_FAIL      | empty_generated_diff        | 1     | 0.33      |

---

### 2) Harness Evaluation Results

| metric                  | value |
|------------------------|-------|
| total_instances        | 300   |
| submitted_instances    | 187   |
| completed_instances    | 187   |
| resolved_instances     | 0     |
| unresolved_instances   | 187   |
| empty_patch_instances  | 0     |
| error_instances        | 0     |

</details>
<details>
<summary><strong>deepseek-ai/deepseek-coder-6.7b-instruct</strong></summary>

### 1) Pre-Harness Filtering (Generation / Edit 단계)

| stage        | error_type       | signature                   | count | ratio (%) |
|--------------|-----------------|-----------------------------|-------|-----------|
| DIFF_EXPORT  | PRED_READY      | ready_for_harness           | 204   | 68.00     |
| EDIT_PARSE   | EDIT_PARSE_FAIL | invalid_edit_script         | 36    | 12.00     |
| EDIT_APPLY   | APPLY_FAIL      | edit_apply_path_missing     | 31    | 10.33     |
| GEN          | GEN_FAIL        | context_length_exceeded     | 15    | 5.00      |
| EDIT_APPLY   | APPLY_FAIL      | edit_apply_range_oob        | 14    | 4.67      |

---

### 2) Harness Evaluation Results

| metric                  | value |
|------------------------|-------|
| total_instances        | 300   |
| submitted_instances    | 204   |
| completed_instances    | 200   |
| resolved_instances     | 2     |
| unresolved_instances   | 198   |
| empty_patch_instances  | 0     |
| error_instances        | 4     |

</details>
<details> 
<summary><strong>deepseek-ai/deepseek-coder-7b-instruct-v1.5</strong></summary>

### 1) Pre-Harness Filtering (Generation / Edit 단계)
| stage        | error_type       | signature                   | count | ratio (%) |
|--------------|-----------------|-----------------------------|-------|-----------|
| DIFF_EXPORT  | PRED_READY      | ready_for_harness           | 185   | 61.67     |
| EDIT_APPLY   | APPLY_FAIL      | edit_apply_path_missing     | 49    | 16.33     |
| EDIT_PARSE   | EDIT_PARSE_FAIL | invalid_edit_script         | 47    | 15.67     |
| GEN          | GEN_FAIL        | context_length_exceeded     | 11    | 3.67      |
| EDIT_APPLY   | APPLY_FAIL      | edit_apply_range_oob        | 8     | 2.67      |

---

### 2) Harness Evaluation Results
| metric                  | value |
|------------------------|-------|
| total_instances        | 300   |
| submitted_instances    | 185   |
| completed_instances    | 183   |
| resolved_instances     | 1     |
| unresolved_instances   | 182   |
| empty_patch_instances  | 0     |
| error_instances        | 2     |
</details>
<details>
<summary><strong>microsoft/Phi-3.5-mini-instruct</strong></summary>

### 1) Pre-Harness Filtering (Generation / Edit 단계)

| Stage | Error Type | Signature | Count | Ratio (%) |
|-------|------------|-----------|-------|-----------|
| DIFF_EXPORT | PRED_READY | ready_for_harness | 203 | 67.67 |
| EDIT_APPLY | APPLY_FAIL | edit_apply_range_oob | 45 | 15.00 |
| EDIT_APPLY | APPLY_FAIL | edit_apply_path_missing | 31 | 10.33 |
| GEN | GEN_FAIL | context_length_exceeded | 12 | 4.00 |
| EDIT_PARSE | EDIT_PARSE_FAIL | invalid_edit_script | 9 | 3.00 |

---

### 2) Harness Evaluation Results

| Metric | Value |
|--------|-------|
| total_instances | 300 |
| submitted_instances | 203 |
| completed_instances | 201 |
| resolved_instances | 1 |
| unresolved_instances | 200 |
| empty_patch_instances | 0 |
| error_instances | 2 |

</details>
<details>
<summary><strong>meta-llama/Llama-3.1-8B-Instruct</strong></summary>

### 1) Pre-Harness Filtering (Generation / Edit 단계)

| Stage | Error Type | Signature | Count | Ratio (%) |
|-------|------------|-----------|-------|-----------|
| DIFF_EXPORT | PRED_READY | ready_for_harness | 230 | 76.67 |
| EDIT_PARSE | EDIT_PARSE_FAIL | invalid_edit_script | 35 | 11.67 |
| EDIT_APPLY | APPLY_FAIL | edit_apply_path_missing | 24 | 8.00 |
| EDIT_APPLY | APPLY_FAIL | edit_apply_range_oob | 7 | 2.33 |
| GEN | GEN_FAIL | context_length_exceeded | 4 | 1.33 |

---

### 2) Harness Evaluation Results

| Metric | Value |
|--------|-------|
| total_instances | 300 |
| submitted_instances | 230 |
| completed_instances | 221 |
| resolved_instances | 1 |
| unresolved_instances | 220 |
| empty_patch_instances | 0 |
| error_instances | 9 |

</details>
<details>
<summary><strong>mistralai/Mistral-7B-Instruct-v0.3</strong></summary>

### 1) Pre-Harness Filtering (Generation / Edit 단계)

| stage       | error_type      | signature               | count | ratio (%) |
| ----------- | --------------- | ----------------------- | ----- | --------- |
| DIFF_EXPORT | PRED_READY      | ready_for_harness       | 175   | 58.33     |
| EDIT_APPLY  | APPLY_FAIL      | edit_apply_path_missing | 48    | 16.00     |
| EDIT_APPLY  | APPLY_FAIL      | edit_apply_range_oob    | 41    | 13.67     |
| EDIT_PARSE  | EDIT_PARSE_FAIL | invalid_edit_script     | 23    | 7.67      |
| GEN         | GEN_FAIL        | context_length_exceeded | 13    | 4.33      |

---

### 2) Harness Evaluation Results

| metric                | value |
| --------------------- | ----- |
| total_instances       | 300   |
| submitted_instances   | 175   |
| completed_instances   | 172   |
| resolved_instances    | 1     |
| unresolved_instances  | 171   |
| empty_patch_instances | 0     |
| error_instances       | 3     |


</details>


## 📁 Folder Structure
```
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

```
