import csv
import json
import time
from pathlib import Path
from typing import Any, Dict

class Recorder:
    def __init__(self, runs_dir: Path, experiment_name: str):
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        self.run_dir = runs_dir / f"{experiment_name}_{timestamp}"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        
        self.traces_dir = self.run_dir / "traces"
        self.traces_dir.mkdir(exist_ok=True)
        
        self.results_csv_path = self.run_dir / "results.csv"
        self.csv_headers = [
            "task_id", "trial_id", "model", "prompt_hash", "success", 
            "error_type", "signature", "returncode", "elapsed_sec", 
            "patch_lines_added", "patch_lines_removed", "files_changed", 
            "timestamp", "seed"
        ]
        self._init_csv()

    def _init_csv(self):
        with open(self.results_csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(self.csv_headers)

    def log_trial(self, result: Dict[str, Any]):
        """
        Logs a single trial execution.
        Expected keys in result match csv_headers + extra for traces.
        """
        # 1. Write to CSV
        row = [result.get(h) for h in self.csv_headers]
        with open(self.results_csv_path, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(row)
            
        # 2. Write Trace JSON and distinct files
        task_id = result.get("task_id", "unknown")
        trial_id = result.get("trial_id", "0")
        base_filename = f"{task_id}_trial{trial_id}"
        
        # Save JSON
        trace_path = self.traces_dir / f"{base_filename}.json"
        trace_data = {
            "task_id": task_id,
            "trial_id": trial_id,
            "issue_text": result.get("issue_text"),
            "test_command": result.get("test_command"),
            "diff": result.get("diff"),
            "stdout": result.get("stdout"),
            "stderr": result.get("stderr"),
            "repo_commit": result.get("repo_commit"),
            "docker_image": result.get("docker_image"),
            "model_config": result.get("model_config"),
            "full_result": result # include everything else
        }
        with open(trace_path, "w") as f:
            json.dump(trace_data, f, indent=2)

        # Save individual files for easy inspection
        if result.get("diff"):
            (self.traces_dir / f"{base_filename}.patch.diff").write_text(result["diff"])
        
        if result.get("stdout"):
            (self.traces_dir / f"{base_filename}.stdout.txt").write_text(result["stdout"])
            
        if result.get("stderr"):
            (self.traces_dir / f"{base_filename}.stderr.txt").write_text(result["stderr"])

    def save_config_snapshot(self, config: Dict[str, Any]):
        path = self.run_dir / "config_snapshot.yaml"
        # dumping as json for simplicity or yaml if available, using json here mostly or just str
        with open(path, "w") as f:
            json.dump(config, f, indent=2)
