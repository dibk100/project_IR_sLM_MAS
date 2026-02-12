import argparse
import yaml
import sys
import shutil
import hashlib
import random
from datetime import datetime
from pathlib import Path
from src.task_loader import TaskLoader
from src.generate_agent import GenerateAgent
from src.executor import Executor
from src.verifier import Verifier
from src.recorder import Recorder
from src.utils import setup_logging, count_diff_lines, check_docker

def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()

def main():
    parser = argparse.ArgumentParser(description="Run Experiment 1")
    parser.add_argument("--config", default="configs/exp1.yaml", help="Path to config file")
    args = parser.parse_args()
    
    # Load Config
    with open(args.config, "r") as f:
        config = yaml.safe_load(f)
        
    # Setup Logging
    project_root = Path(__file__).resolve().parent.parent
    runs_dir = project_root / "runs"
    
    recorder = Recorder(runs_dir, config["experiment"]["name"])
    recorder.save_config_snapshot(config)
    
    logger = setup_logging("Exp1", recorder.run_dir / "experiment.log")
    logger.info(f"Starting Experiment 1: {config['experiment']['name']}")

    # Seed (reproducibility)
    seed = int(config["experiment"].get("seed", 42))
    random.seed(seed)
    try:
        import numpy as np
        np.random.seed(seed)
    except Exception:
        pass
    logger.info(f"Seed set to {seed}")

    # # 확인용 : patch/test_patch를 정말 제거했는지
    # logger.info(f"Task keys: {sorted(task.keys())}")

    # Check Docker
    if not check_docker():
        logger.error("Docker is not running or not installed. Exiting.")
        sys.exit(1)
    
    # Components
    loader = TaskLoader(project_root / config["experiment"]["task_subset"],max_tasks=config["experiment"].get("max_tasks"))
    agent = GenerateAgent(config["agent"]["model"], config["agent"])
    executor = Executor(config["environment"]["timeout_seconds"], work_dir=project_root / "workspace")
    verifier = Verifier()
    
    try:
        tasks = loader.load_tasks()
        logger.info(f"Loaded {len(tasks)} tasks.")
    except Exception as e:
        logger.error(f"Failed to load tasks: {e}")
        sys.exit(1)
    
    max_tasks = config["experiment"].get("max_tasks", None)  # null => None
    max_trials = int(config["experiment"].get("max_trials", 1))  # task당 trial 수

    processed = 0
    for i, task in enumerate(tasks):
        if max_tasks is not None and processed >= int(max_tasks):
            break

        task_id = task.get("instance_id", "unknown")
        logger.info(f"Processing Task ({processed+1}): {task_id}")

        for trial_id in range(max_trials):  # 0-based (trial0) 유지
            run_ts = datetime.utcnow().isoformat()

            # 1. Generate (GEN_FAIL fail-fast)
            logger.info("Generating patch...")
            try:
                diff = agent.generate(task)
            except Exception as e:
                logger.error(f"GEN_FAIL: LLM generation failed for {task_id} trial{trial_id}: {e}")
                recorder.log_trial({
                    "task_id": task_id,
                    "trial_id": trial_id,
                    "model": config["agent"]["model"],
                    "prompt_hash": _sha256(f"{task.get('repo','')}|{task.get('base_commit','')}|{task.get('problem_statement','')}"),
                    "success": False,
                    "error_type": "GEN_FAIL",
                    "signature": "llm_call_fail",
                    "returncode": "",
                    "elapsed_sec": "",
                    "diff": "",
                    "patch_lines_added": 0,
                    "patch_lines_removed": 0,
                    "files_changed": 0,
                    "timestamp": run_ts,
                    "seed": seed,
                    "repo": task.get("repo"),
                    "base_commit": task.get("base_commit"),
                })
                continue

            if not diff or not diff.strip():
                logger.error(f"GEN_FAIL: empty diff for {task_id} trial{trial_id}")
                recorder.log_trial({
                    "task_id": task_id,
                    "trial_id": trial_id,
                    "model": config["agent"]["model"],
                    "prompt_hash": _sha256(f"{task.get('repo','')}|{task.get('base_commit','')}|{task.get('problem_statement','')}"),
                    "success": False,
                    "error_type": "GEN_FAIL",
                    "signature": "empty_diff",
                    "returncode": "",
                    "elapsed_sec": "",
                    "diff": "",
                    "patch_lines_added": 0,
                    "patch_lines_removed": 0,
                    "files_changed": 0,
                    "timestamp": run_ts,
                    "seed": seed,
                    "repo": task.get("repo"),
                    "base_commit": task.get("base_commit"),
                })
                continue

            patch_added, patch_removed, files_changed = count_diff_lines(diff)
            logger.info(f"Generated diff: +{patch_added} -{patch_removed} lines in {files_changed} files.")

            # 2. Execute
            logger.info("Executing test in Docker...")
            exec_result = executor.execute(task, diff)

            # 3. Verify
            verify_result = verifier.verify(exec_result)

            logger.info(f"Task {task_id} Result: {verify_result['error_type']} ({verify_result['signature']})")

            # 4. Record
            full_result = {
                "task_id": task_id,
                "trial_id": trial_id,
                "model": config["agent"]["model"],
                "prompt_hash": _sha256(f"{task.get('repo','')}|{task.get('base_commit','')}|{task.get('problem_statement','')}"),
                "diff": diff,
                "patch_lines_added": patch_added,
                "patch_lines_removed": patch_removed,
                "files_changed": files_changed,
                "timestamp": run_ts,
                "seed": seed,
                "repo": task.get("repo"),
                "base_commit": task.get("base_commit"),
                "taxonomy_version": config["experiment"].get("taxonomy_version", "B-v2"),
                **exec_result,
                **verify_result
            }
            recorder.log_trial(full_result)

        processed += 1
        
    logger.info("Experiment Completed.")

if __name__ == "__main__":
    main()
