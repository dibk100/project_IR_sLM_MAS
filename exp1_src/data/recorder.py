"""
역할 :
- run dir 생성
- trials.jsonl append
- optional trace files 저장
- config snapshot 저장

JSONL logger 중심

output :
- pre-harness 결과 → trials.jsonl
- predictions → predictions.jsonl
- post-harness merge → merged_results.jsonl
"""
import json
import time
from pathlib import Path
from typing import Any, Dict

import yaml


class Recorder:
    def __init__(self, runs_dir: Path, experiment_name: str):
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        self.run_dir = runs_dir / f"{experiment_name}_{timestamp}"
        self.run_dir.mkdir(parents=True, exist_ok=True)

        self.traces_dir = self.run_dir / "traces"
        self.traces_dir.mkdir(exist_ok=True)

        self.trials_jsonl_path = self.run_dir / "trials.jsonl"

    def log_trial(self, result: Dict[str, Any]) -> None:
        task_id = result.get("task_id", "unknown")
        trial_id = result.get("trial_id", 0)
        base_filename = f"{task_id}_trial{trial_id}"

        # 1) main append-only log
        with open(self.trials_jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")

        # 2) trace json for debugging
        trace_path = self.traces_dir / f"{base_filename}.json"
        trace_data = {
            "task_id": task_id,
            "trial_id": trial_id,
            "stage": result.get("stage"),
            "error_type": result.get("error_type"),
            "signature": result.get("signature"),
            "context_used": result.get("context_used", False),
            "context_num_files": result.get("context_num_files", 0),
            "repo_context_preview": result.get("repo_context_preview", ""),
            "edit_parse_ok": result.get("edit_parse_ok", False),
            "edit_parse_reason": result.get("edit_parse_reason", ""),
            "diff_export_ok": result.get("diff_export_ok", False),
            "diff_export_reason": result.get("diff_export_reason", ""),
            "edit_script": result.get("edit_script"),
            "diff": result.get("diff"),
            "stdout": result.get("stdout"),
            "stderr": result.get("stderr"),
        }
        with open(trace_path, "w", encoding="utf-8") as f:
            json.dump(trace_data, f, indent=2, ensure_ascii=False)

        # 3) separate artifacts for easy inspection
        if result.get("edit_script"):
            (self.traces_dir / f"{base_filename}.edit.json").write_text(
                result["edit_script"], encoding="utf-8"
            )

        if result.get("diff"):
            (self.traces_dir / f"{base_filename}.patch.diff").write_text(
                result["diff"], encoding="utf-8"
            )

        if result.get("stdout"):
            (self.traces_dir / f"{base_filename}.stdout.txt").write_text(
                result["stdout"], encoding="utf-8"
            )

        if result.get("stderr"):
            (self.traces_dir / f"{base_filename}.stderr.txt").write_text(
                result["stderr"], encoding="utf-8"
            )

    def save_config_snapshot(self, config: Dict[str, Any]) -> None:
        path = self.run_dir / "config_snapshot.yaml"
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(config, f, sort_keys=False, allow_unicode=True)