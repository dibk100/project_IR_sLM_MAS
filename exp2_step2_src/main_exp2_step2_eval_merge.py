from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

import yaml

from exp2_step2_src.pipeline.repair_eval_result_merger import merge_repair_eval_results

logger = logging.getLogger(__name__)


def setup_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def load_config(config_path: Path | str) -> Dict[str, Any]:
    config_path = Path(config_path)
    with config_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    if not path.exists():
        raise FileNotFoundError(f"JSONL file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSONL at {path}:{line_no}: {e}") from e

    return rows


def save_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def build_run_output_dir(project_root: Path, config: Dict[str, Any]) -> Path:
    experiment_cfg = config.get("experiment", {})
    run_id = experiment_cfg.get("run_id", "exp2_step2_debug")
    return project_root / "runs" / run_id


def build_eval_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_rows = len(rows)

    before_test_fail = sum(1 for r in rows if r.get("before_error_type") == "TEST_FAIL")
    after_pass = sum(1 for r in rows if r.get("repair_eval_final_error_type") == "PASS")
    after_test_fail = sum(1 for r in rows if r.get("repair_eval_final_error_type") == "TEST_FAIL")
    after_patch_fail = sum(1 for r in rows if r.get("repair_eval_final_error_type") == "PATCH_FAIL")
    after_other_runtime = sum(1 for r in rows if r.get("repair_eval_final_error_type") == "OTHER_RUNTIME")

    final_error_type_counts: Dict[str, int] = {}
    final_signature_counts: Dict[str, int] = {}
    transition_counts: Dict[str, int] = {}

    for row in rows:
        after_et = str(row.get("repair_eval_final_error_type", "") or "")
        after_sig = str(row.get("repair_eval_final_signature", "") or "")
        before_et = str(row.get("before_error_type", "") or "")
        transition = f"{before_et}->{after_et}"

        if after_et:
            final_error_type_counts[after_et] = final_error_type_counts.get(after_et, 0) + 1
        if after_sig:
            final_signature_counts[after_sig] = final_signature_counts.get(after_sig, 0) + 1
        if transition:
            transition_counts[transition] = transition_counts.get(transition, 0) + 1

    return {
        "total_rows": total_rows,
        "before_test_fail_rows": before_test_fail,
        "after_pass_rows": after_pass,
        "after_test_fail_rows": after_test_fail,
        "after_patch_fail_rows": after_patch_fail,
        "after_other_runtime_rows": after_other_runtime,
        "semantic_recovery_rate_over_before_test_fail": (
            after_pass / before_test_fail if before_test_fail > 0 else 0.0
        ),
        "final_error_type_counts": final_error_type_counts,
        "final_signature_counts": final_signature_counts,
        "transition_counts": transition_counts,
    }


def preview_summary(summary: Dict[str, Any]) -> None:
    logger.info("===== EXP2_STEP2 EVAL SUMMARY =====")
    logger.info("total_rows=%s", summary["total_rows"])
    logger.info("before_test_fail_rows=%s", summary["before_test_fail_rows"])
    logger.info("after_pass_rows=%s", summary["after_pass_rows"])
    logger.info("after_test_fail_rows=%s", summary["after_test_fail_rows"])
    logger.info("after_patch_fail_rows=%s", summary["after_patch_fail_rows"])
    logger.info("after_other_runtime_rows=%s", summary["after_other_runtime_rows"])
    logger.info(
        "semantic_recovery_rate_over_before_test_fail=%.4f",
        summary["semantic_recovery_rate_over_before_test_fail"],
    )
    logger.info("final_error_type_counts=%s", summary["final_error_type_counts"])
    logger.info("final_signature_counts=%s", summary["final_signature_counts"])
    logger.info("transition_counts=%s", summary["transition_counts"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge Step2 repair harness evaluation results")
    parser.add_argument("--config", required=True, help="Path to config file")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    config = load_config(args.config)

    experiment_cfg = config.get("experiment", {})
    agent_cfg = config.get("agent", {})

    run_id = experiment_cfg["run_id"]
    model_name = agent_cfg["model"]
    eval_run_prefix = f"{run_id}_repair_eval"

    run_dir = build_run_output_dir(project_root, config)
    setup_logging(run_dir / "eval_merge.log")

    logger.info("[main_exp2_step2_eval_merge] project_root=%s", project_root)
    logger.info("[main_exp2_step2_eval_merge] config_path=%s", args.config)
    logger.info("[main_exp2_step2_eval_merge] run_id=%s", run_id)
    logger.info("[main_exp2_step2_eval_merge] eval_run_prefix=%s", eval_run_prefix)
    logger.info("[main_exp2_step2_eval_merge] run_dir=%s", run_dir)

    merged_path = merge_repair_eval_results(
        run_dir=run_dir,
        eval_run_prefix=eval_run_prefix,
        model_name=model_name,
        repair_results_filename="semantic_repair_results.jsonl",
        merged_filename="repair_eval_merged_results.jsonl",
    )

    logger.info("[main_exp2_step2_eval_merge] merged_path=%s", merged_path)

    merged_rows = read_jsonl(merged_path)
    summary = build_eval_summary(merged_rows)

    summary_path = run_dir / "repair_eval_summary.json"
    save_json(summary_path, summary)

    logger.info("[main_exp2_step2_eval_merge] summary_path=%s", summary_path)
    preview_summary(summary)


if __name__ == "__main__":
    main()