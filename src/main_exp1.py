import argparse
import yaml
import sys
import shutil
from pathlib import Path
from src.task_loader import TaskLoader
from src.generate_agent import GenerateAgent
from src.executor import Executor
from src.verifier import Verifier
from src.recorder import Recorder
from src.utils import setup_logging, count_diff_lines, check_docker

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

    # Check Docker
    if not check_docker():
        logger.error("Docker is not running or not installed. Exiting.")
        sys.exit(1)
    
    # Components
    loader = TaskLoader(project_root / config["experiment"]["task_subset"])
    agent = GenerateAgent(config["agent"]["model"], config["agent"])
    executor = Executor(config["environment"]["timeout_seconds"], work_dir=project_root / "workspace")
    verifier = Verifier()
    
    try:
        tasks = loader.load_tasks()
        logger.info(f"Loaded {len(tasks)} tasks.")
    except Exception as e:
        logger.error(f"Failed to load tasks: {e}")
        sys.exit(1)
    
    for i, task in enumerate(tasks):
        if i >= config["experiment"].get("max_trials", 999999):
            break

        task_id = task.get("instance_id", "unknown")
        logger.info(f"Processing Task ({i+1}): {task_id}")
        
        # 1. Generate
        logger.info("Generating patch...")
        diff = agent.generate(task)
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
            "trial_id": 0, # Single trial for now
            "model": config["agent"]["model"],
            "prompt_hash": "hash_placeholder", # TODO: Implement prompt hashing
            "diff": diff,
            "patch_lines_added": patch_added,
            "patch_lines_removed": patch_removed,
            "files_changed": files_changed,
            "timestamp": exec_result.get("timestamp", ""), # Executor doesn't pass timestamp, usually Recorder adds it? No, Recorder has column.
            "repo": task.get("repo"),
            "base_commit": task.get("base_commit"),
            **exec_result,
            **verify_result
        }
        
        recorder.log_trial(full_result)
        
    logger.info("Experiment Completed.")

if __name__ == "__main__":
    main()
