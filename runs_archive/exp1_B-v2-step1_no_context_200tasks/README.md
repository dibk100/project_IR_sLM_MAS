# 📊 Experiment1-B2-step01
- Experiment: B-v2-step1
- Dataset: SWE-bench Lite
- Model: Qwen2.5-7B-Instruct
- Context: NONE (problem_statement only)
- Tasks: 200
- Observation:
    - PATCH_FAIL: 91%
    - GEN_FAIL: 9%
    - EXEC: ~0%
- Interpretation:
    > Failure collapses at PATCH stage due to missing repo grounding.

## (analysis) stage_distribution
| Stage | Count | Ratio |
| ----- | ----- | ----- |
| GEN   | 18    | 9%    |
| PATCH | 182   | 91%   |

## (Insite) structural collapse
> sLM + naive context → failure collapses to PATCH stage
>> “Without minimal repository grounding, sLM-based patch generation degenerates into patch-level failure.”