# 📊 Experiment1-B2-step02-C
- Experiment: B-v2-step2-Check
- Dataset: SWE-bench Lite
- Model: Qwen2.5-7B-Instruct
- Notes:
    - 목적 : Step2-1이 “진짜 컨텍스트 실험이었는지 추가 확인
    - (A) context_used/context_num_files + (B) preview 추가
        - 상 파일 : src/recorder.py, src/main_exp1.py

## Observation (N=200)
    - PATCH_FAIL:
        - corrupt_patch: 179 
        - hunk_failed: 4
        - path_missing: 3
    - GEN_FAIL: 
        - llm_call_fail : 9
        - invalid_diff_format : 3
        - empty_diff : 2
    - EXEC: ~0%
