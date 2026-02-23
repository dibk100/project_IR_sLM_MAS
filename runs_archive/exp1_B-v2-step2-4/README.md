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

# 🧠 Insite
#### ✅ sLM 포맷 안정성
- 200 중 7 invalid_edit_script → 3.5%   
- 12 llm_call_fail → API/메모리/timeout 문제

→ edit JSON 포맷은 생각보다 안정적임    

#### ⚠️ Edit 적용 품질
- 34 APPLY 실패
    - 32 path_missing → 파일 경로 hallucination
    - 2 range_oob → 라인 오프셋 문제

→ 여기서 이미 sLM 구조적 한계가 보이기 시작함   
(context는 주었지만 정확한 파일/라인 grounding은 아직 불안정)


> To-Do.    
> Docker 문제 해결