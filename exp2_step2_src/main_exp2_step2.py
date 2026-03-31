from __future__ import annotations
"""
main_exp2_step2.py
Post-harness repair loop~~

config 로드
step1 결과 로드
repair 대상 필터링
semantic repair 실행
결과 저장
"""
import argparse
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

import yaml

from exp2_step2_src.agent.repair_agent import RepairAgent
from exp2_step2_src.data.step1_result_loader import load_step1_results
from exp2_step2_src.pipeline.semantic_repair_executor import SemanticRepairExecutor

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


def load_config(config_path: Path) -> Dict[str, Any]:
    with config_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def save_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def save_config_snapshot(config: Dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, sort_keys=False, allow_unicode=True)


def build_run_output_dir(project_root: Path, config: Dict[str, Any]) -> Path:
    experiment_cfg = config.get("experiment", {})
    run_id = experiment_cfg.get("run_id", "exp2_step2_debug")
    return project_root / "runs" / run_id


def apply_output_policy(results: List[Dict[str, Any]], config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    output.save_* 옵션에 따라 저장 시 포함할 필드를 제어한다.
    """
    output_cfg = config.get("output", {})
    save_prompts = bool(output_cfg.get("save_prompts", True))
    save_raw_output = bool(output_cfg.get("save_raw_output", True))
    save_repair_patch = bool(output_cfg.get("save_repair_patch", True))

    filtered_results: List[Dict[str, Any]] = []

    for row in results:
        copied = dict(row)

        if not save_prompts:
            copied["repair_system_prompt"] = ""
            copied["repair_user_prompt"] = ""

        if not save_raw_output:
            copied["repair_raw_output"] = ""

        if not save_repair_patch:
            copied["repair_patch"] = ""

        filtered_results.append(copied)

    return filtered_results


def build_summary(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(results)
    eligible = sum(1 for r in results if r.get("repair_eligible", False))
    attempted = sum(1 for r in results if r.get("repair_attempted", False))
    success = sum(1 for r in results if r.get("repair_success", False))

    failure_stage_counts: Dict[str, int] = {}
    trigger_reason_counts: Dict[str, int] = {}
    final_error_type_counts: Dict[str, int] = {}

    for r in results:
        failure_stage = str(r.get("repair_failure_stage", "") or "")
        trigger_reason = str(r.get("repair_trigger_reason", "") or "")
        final_error_type = str(r.get("final_error_type", "") or "")

        if failure_stage:
            failure_stage_counts[failure_stage] = failure_stage_counts.get(failure_stage, 0) + 1
        if trigger_reason:
            trigger_reason_counts[trigger_reason] = trigger_reason_counts.get(trigger_reason, 0) + 1
        if final_error_type:
            final_error_type_counts[final_error_type] = final_error_type_counts.get(final_error_type, 0) + 1

    return {
        "total_rows": total,
        "repair_eligible_rows": eligible,
        "repair_attempted_rows": attempted,
        "repair_success_rows": success,
        "repair_success_rate_over_attempted": (success / attempted) if attempted > 0 else 0.0,
        "failure_stage_counts": failure_stage_counts,
        "trigger_reason_counts": trigger_reason_counts,
        "final_error_type_counts": final_error_type_counts,
    }


def preview_summary(summary: Dict[str, Any]) -> None:
    logger.info("===== EXP2_STEP2 SUMMARY =====")
    logger.info("total_rows=%s", summary["total_rows"])
    logger.info("repair_eligible_rows=%s", summary["repair_eligible_rows"])
    logger.info("repair_attempted_rows=%s", summary["repair_attempted_rows"])
    logger.info("repair_success_rows=%s", summary["repair_success_rows"])
    logger.info(
        "repair_success_rate_over_attempted=%.4f",
        summary["repair_success_rate_over_attempted"],
    )
    logger.info("failure_stage_counts=%s", summary["failure_stage_counts"])
    logger.info("trigger_reason_counts=%s", summary["trigger_reason_counts"])
    logger.info("final_error_type_counts=%s", summary["final_error_type_counts"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Experiment 2 Step2")
    parser.add_argument("--config", default="configs/exp2_step2.yaml", help="Path to config file")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    config = load_config(Path(args.config))

    experiment_cfg = config.get("experiment", {})
    repair_cfg = config.get("repair", {})

    run_id = experiment_cfg.get("run_id", "exp2_step2_debug")
    input_run_name = experiment_cfg["input_run_name"]
    max_tasks = int(experiment_cfg.get("max_tasks", -1))
    repair_enabled = bool(repair_cfg.get("enabled", True))

    output_dir = build_run_output_dir(project_root, config)
    setup_logging(output_dir / "experiment.log")

    logger.info("[main_exp2_step2] project_root=%s", project_root)
    logger.info("[main_exp2_step2] config_path=%s", args.config)
    logger.info("[main_exp2_step2] run_id=%s", run_id)
    logger.info("[main_exp2_step2] input_run_name=%s", input_run_name)
    logger.info("[main_exp2_step2] output_dir=%s", output_dir)
    logger.info("[main_exp2_step2] repair_enabled=%s", repair_enabled)

    save_config_snapshot(config, output_dir / "config_snapshot.yaml")

    if not repair_enabled:
        logger.warning("[main_exp2_step2] repair.enabled is False. Exiting without execution.")
        return

    logger.info(
        "[main_exp2_step2] loading step1 results input_run_name=%s max_tasks=%s",
        input_run_name,
        max_tasks,
    )

    rows = load_step1_results(project_root=project_root, run_name=input_run_name)

    if max_tasks > 0:
        rows = rows[:max_tasks]

    logger.info("[main_exp2_step2] loaded_rows=%d", len(rows))

    agent = RepairAgent(
        model_name=config["agent"]["model"],
        config=config["agent"],
    )
    executor = SemanticRepairExecutor(repair_agent=agent)

    raw_results: List[Dict[str, Any]] = []

    for idx, row in enumerate(rows, start=1):
        instance_id = row.get("instance_id", "unknown")
        logger.info(
            "[main_exp2_step2] processing idx=%d/%d instance_id=%s",
            idx,
            len(rows),
            instance_id,
        )

        result = executor.run_on_row(row)
        raw_results.append(result)

    results_to_save = apply_output_policy(raw_results, config)

    results_path = output_dir / "semantic_repair_results.jsonl"
    write_jsonl(results_path, results_to_save)
    logger.info("[main_exp2_step2] wrote results to %s", results_path)

    summary = build_summary(raw_results)

    summary_path = output_dir / "semantic_repair_summary.json"
    save_json(summary_path, summary)
    logger.info("[main_exp2_step2] wrote summary to %s", summary_path)

    preview_summary(summary)


if __name__ == "__main__":
    main()