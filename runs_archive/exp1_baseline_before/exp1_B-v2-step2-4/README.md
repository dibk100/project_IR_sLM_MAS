# 📊 Experiment1-B2-step02-4
- Experiment: B-v2-step2-4
- Dataset: SWE-bench Lite
- Model: Qwen2.5-7B-Instruct
- Tasks: 200
- Notes:
    - generate_agent.py, executor.py, taxonomy.py, main_exp1.py 수정

## Observation (N=200) : Stage & Signature 분포
    - EXEC 147: 
        - docker_image_not_found
    - EDIT_APPLY 34: 
        - path_missing 32
        - range_oob 2
    - EDIT_PARSE 7 :
        - invalid_edit_script 7
    - GEN 12 : 
        - llm_call_fail 12

→ docker_image_not_found(환경 실패)  
```  
executor → docker run 단계에서 image pull 실패
```

## Insite
#### sLM 포맷 안정성
- 200 중 7 invalid_edit_script → 3.5%   
- 12 llm_call_fail → API/메모리/timeout 문제

→ edit JSON 포맷은 생각보다 안정적임    

#### Edit 적용 품질
- 34 APPLY 실패
    - 32 path_missing → 파일 경로 hallucination
    - 2 range_oob → 라인 오프셋 문제

→ 여기서 이미 sLM 구조적 한계가 보이기 시작함   
(context는 주었지만 정확한 파일/라인 grounding은 아직 불안정)
   

# 📊 Experiment1-B2-step02-4 : docker_image_not_found
- Experiment: B-v2-step2-4
- Dataset: SWE-bench Lite
- Model: Qwen2.5-7B-Instruct
- Tasks: 147
- Notes:
    - docker_image_not_found가 정확히 무슨 실패인지 확인하는 작업.
    - minimal prompting
    - edit-script 방식
    - 제한된 context (80 files)

### 1) harness 설치/검증
```
git clone https://github.com/SWE-bench/SWE-bench
cd SWE-bench
pip install -e .
```

변환 스크립트(06_conversion script.ipynb) : runs 폴더 → predictions.jsonl

```
(amla) dibaeck@diserver:~/workspace/project_IR_sLM_MAS$ python -m swebench.harness.run_evaluation \
  --dataset_name princeton-nlp/SWE-bench_Lite \
  --predictions_path runs/exp1_init_qwen2p5_baseline_20260223_121522/predictions.jsonl \
  --max_workers 1 \
  --run_id exp1-step2-4-qwen-200
```
→ 200개 평가(147개 docker_image_not_found)

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
