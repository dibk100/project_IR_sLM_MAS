"""
main_exp2_step1.py

Policy v0:
- initial context 수집
- generation 시도
- materialize
- taxonomy state 읽기
- policy action 선택
- action이 retry면 설정 바꿔서 한 번 더 generate/materialize
- 최종적으로 PRED_READY면 harness로 전달, 아니면 reject/log

Scope:
- Pre-harness hard-coded retry only
- Post-harness repair loop는 아직 다루지 않음
"""
import argparse
import random
import sys
from datetime import datetime
from pathlib import Path
import yaml
import subprocess

from exp2_step1_src.agent.context_collector import ContextCollector
from exp2_step1_src.agent.generate_agent import GenerateAgent
from exp2_step1_src.pipeline.diff_materializer import DiffMaterializer
from exp2_step1_src.pipeline.harness_result_merger import merge_harness_results
from exp2_step1_src.pipeline.policy_executor import run_policy_attempts
from exp2_step1_src.data.recorder import Recorder
from exp2_step1_src.data.task_loader import TaskLoader
from exp2_step1_src.utils.utils import (
    is_docker_available,
    write_predictions_jsonl,
    setup_logging,
    run_in_chunks,
)


def main():
    parser = argparse.ArgumentParser(description="Run Experiment 2 Step1")
    parser.add_argument("--config", default="configs/exp2_step1.yaml", help="Path to config file")
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    project_root = Path(__file__).resolve().parent.parent
    runs_dir = project_root / "runs"

    recorder = Recorder(runs_dir, config["experiment"]["name"])
    recorder.save_config_snapshot(config)

    logger = setup_logging("Exp2-Step1", recorder.run_dir / "experiment.log")
    logger.info("Starting Experiment 2 Step1: %s", config["experiment"]["name"])

    run_id = config["experiment"]["run_id"]
    model_name = config["agent"]["model"]

    seed = int(config["experiment"].get("seed", 42))
    random.seed(seed)
    try:
        import numpy as np
        np.random.seed(seed)
    except Exception:
        pass
    logger.info("Seed set to %d", seed)

    loader = TaskLoader(
        project_root / config["experiment"]["task_subset"],
        max_tasks=config["experiment"].get("max_tasks"),
    )
    agent = GenerateAgent(config["agent"]["model"], config["agent"])
    materializer = DiffMaterializer(
        config["environment"]["timeout_seconds"],
        work_dir=project_root / "workspace",
    )

    max_ctx_files = int(config.get("constraints", {}).get("context_max_files", 80))
    ctx = ContextCollector(max_files=max_ctx_files)

    try:
        tasks = loader.load_tasks()
        logger.info("Loaded %d tasks.", len(tasks))
    except Exception as e:
        logger.error("Failed to load tasks: %s", e)
        sys.exit(1)

    max_trials = int(config["experiment"].get("max_trials", 1))
    predictions_by_instance: dict[str, dict] = {}

    for i, task in enumerate(tasks):
        repo_name = task.get("repo", "unknown_repo").replace("/", "__")
        repo_path = project_root / "workspace" / repo_name
        task_id = task.get("instance_id", "unknown")

        logger.info("Processing Task (%d/%d): %s", i + 1, len(tasks), task_id)

        repo_ctx = ctx.collect(repo_path)
        base_file_candidates = list(getattr(repo_ctx, "file_candidates", []) or [])

        logger.info(
            "Base context collected for %s: repo_path=%s num_files=%d",
            task_id,
            repo_path,
            len(base_file_candidates),
        )

        for trial_id in range(max_trials):
            run_ts = datetime.utcnow().isoformat()

            final_result = run_policy_attempts(
                task=task,
                repo_path=repo_path,
                task_id=task_id,
                trial_id=trial_id,
                model_name=model_name,
                seed=seed,
                run_ts=run_ts,
                recorder=recorder,
                logger=logger,
                agent=agent,
                materializer=materializer,
                config=config,
                base_file_candidates=base_file_candidates,
            )

            # 참고:
            # final_selected / terminated_by_policy 값은 현재 in-memory에서만 갱신되며,
            # 이미 recorder.log_trial()가 끝난 뒤라 trials.jsonl에는 반영되지 않을 수 있음.
            final_result["final_selected"] = True
            final_result["terminated_by_policy"] = final_result.get("error_type") != "PRED_READY"

            if (
                final_result.get("success")
                and final_result.get("error_type") == "PRED_READY"
                and final_result.get("diff_export_ok")
            ):
                predictions_by_instance[task_id] = {
                    "instance_id": task_id,
                    "model_name_or_path": model_name,
                    "model_patch": final_result.get("diff", ""),
                }
                logger.info("Accepted final prediction for %s trial%d", task_id, trial_id)
            else:
                logger.info(
                    "Rejected final prediction for %s trial%d: error=%s signature=%s",
                    task_id,
                    trial_id,
                    final_result.get("error_type"),
                    final_result.get("signature"),
                )

    logger.info("Pre-harness policy execution completed.")

    predictions = list(predictions_by_instance.values())
    logger.info("Harness-ready predictions: %d", len(predictions))

    pred_path = recorder.run_dir / "predictions.jsonl"
    write_predictions_jsonl(pred_path, predictions)
    logger.info("Wrote predictions to %s", pred_path)

    if not is_docker_available():
        logger.error("Docker is required for SWE-bench evaluation but is not available.")
        sys.exit(1)

    target_dir = Path("/home/dibaeck/workspace/project_IR_sLM_MAS/workspace/psf__requests")

    if target_dir.exists():
        subprocess.run([
            "bash", "-c",
            f"find {target_dir} -type f -name '*.py' -exec sed -i "
            "'s/collections.MutableMapping/collections.abc.MutableMapping/g' {{}} +"
        ])
        subprocess.run([
            "bash", "-c",
            f"find {target_dir} -type f -name '*.py' -exec sed -i "
            "'s/from collections import MutableMapping/from collections.abc import MutableMapping/g' {{}} +"
        ])
        logger.info("Patched entire psf__requests for Python 3.11 compatibility")

    logger.info("Starting SWE-bench harness evaluation (chunked)...")
    run_in_chunks(
        run_dir=recorder.run_dir,
        run_id=run_id,
        model_name=model_name,
        chunk_size=100,
    )

    merged_path = merge_harness_results(
        recorder.run_dir,
        run_id=run_id,
        model_name=model_name,
    )

    logger.info("Merged final results written to %s", merged_path)


if __name__ == "__main__":
    main()