# 📊 Experiment1-B2-step02-A
- Experiment: B-v2-step2-1 (minimal context)
- Dataset: SWE-bench Lite
- Model: Qwen2.5-7B-Instruct
- Context: Minimal repository context (file-path candidates only, collected from workspace clone)
    - “repo_path에서 *.py 파일의 상대 경로 목록을 수집하여 repo_context로 주입(파일 내용은 포함하지 않음)”
- Tasks: 200
- Notes:
    - src/utils.py에 diff format validator 추가
    - GenerateAgent에서 raw_diff →sanitize_diff(raw_diff)

## Observation (N=200)
    - PATCH_FAIL:
        - corrupt_patch: 178 
        - hunk_failed: 5
        - path_missing: 3
    - GEN_FAIL: 
        - llm_call_fail : 9
        - invalid_diff_format : 3
        - empty_diff : 2
    - EXEC: ~0%

## analysis
- GEN_FAIL이 세분화됨
    - `llm_call_fail` (인프라/서버/클라이언트 계열)
    - `invalid_diff_format` (unified diff 포맷 자체가 깨짐)
    - `empty_diff` (모델이 사실상 아무 것도 못 냄)
- corrupt_patch(178)
    > “파일 후보 리스트 컨텍스트”의 효과가 (1) 경로 미존재(path_missing) 를 조금 줄일 수는 있어도,
    (2) unified diff 자체가 git apply가 못 먹는 형태로 나오는 문제(corrupt)를 거의 못 건드린 상태
    >
