"""
역할:
- generation orchestration
- predictions.jsonl 생성
- harness 호출
- merge 호출

Exp1 main:
- generation orchestration
- predictions.jsonl 생성
- harness 호출

Pre-harness stage only:
- GEN
- REPO
- EDIT_PARSE
- EDIT_APPLY
- DIFF_EXPORT

Install/test must be handled only by SWE-bench harness (Docker).
"""
import argparse
import hashlib
import random
import sys
import time
from datetime import datetime
from pathlib import Path
import yaml

from exp1_src.agent.context_collector import ContextCollector
from exp1_src.agent.generate_agent import GenerateAgent
from exp1_src.pipeline.diff_materializer import DiffMaterializer
from exp1_src.pipeline.harness_result_merger import merge_harness_results
from exp1_src.data.recorder import Recorder
from exp1_src.data.task_loader import TaskLoader
from exp1_src.utils.utils import run_swebench_harness,is_docker_available,write_predictions_jsonl,setup_logging,count_diff_lines, run_in_chunks,split_jsonl


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()

def main():
    parser = argparse.ArgumentParser(description="Run Experiment 1")
    parser.add_argument("--config", default="configs/exp1.yaml", help="Path to config file")
    args = parser.parse_args()

    # Load config
    with open(args.config, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # Setup paths / logging
    project_root = Path(__file__).resolve().parent.parent
    runs_dir = project_root / "runs"

    recorder = Recorder(runs_dir, config["experiment"]["name"])
    recorder.save_config_snapshot(config)

    logger = setup_logging("Exp1", recorder.run_dir / "experiment.log")
    logger.info("Starting Experiment 1: %s", config["experiment"]["name"])

    run_id = config["experiment"]["run_id"]
    model_name = config["agent"]["model"]

    # Seed
    seed = int(config["experiment"].get("seed", 42))
    random.seed(seed)
    try:
        import numpy as np
        np.random.seed(seed)
    except Exception:
        pass
    logger.info("Seed set to %d", seed)

    # Components
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

        for trial_id in range(max_trials):
            run_ts = datetime.utcnow().isoformat()

            # -------------------------------
            # 1) Build task input / context
            # -------------------------------
            task_in = dict(task)
            repo_ctx = ctx.collect(repo_path)

            file_candidates = list(getattr(repo_ctx, "file_candidates", []) or [])
            context_used = bool(file_candidates)
            context_num_files = len(file_candidates)
            repo_context_preview = ""

            logger.info(
                "Context collected for %s: repo_path=%s num_files=%d",
                task_id,
                repo_path,
                context_num_files,
            )
            
            logger.info(
                "Context status for %s trial%d: used=%s num_files=%d",
                task_id,
                trial_id,
                context_used,
                context_num_files,
            )

            if context_used:
                injected_context = "Existing files (choose from these):\n" + "\n".join(file_candidates)
                task_in["repo_context"] = injected_context
                task_in["context_num_files"] = context_num_files
                task_in["repo_path"] = str(repo_path)

                preview_lines = ["Existing files (choose from these):"] + file_candidates[:20]
                repo_context_preview = "\n".join(preview_lines)
                if len(file_candidates) > 20:
                    repo_context_preview += f"\n... (+{len(file_candidates) - 20} more)"

                logger.info(
                    "Context injected for %s: context_num_files=%d preview=%s",
                    task_id,
                    context_num_files,
                    file_candidates[:5],
                )
            else:
                logger.info("Context injected for %s: empty context", task_id)

            # bookkeeping
            edit_used = True
            edit_parse_ok = False
            edit_parse_reason = ""
            diff_export_ok = False
            diff_export_reason = ""

            # -------------------------------
            # 2) Generate
            # -------------------------------
            logger.info("Generating edit script for %s trial%d ...", task_id, trial_id)
            t0 = time.time()

            try:
                edit_script = agent.generate_edits(
                    task_in,
                    max_files=int(config.get("constraints", {}).get("max_files", 2)),
                )
            except Exception as e:
                gen_elapsed = time.time() - t0
                err_msg = str(e)

                if "maximum context length" in err_msg or "Please reduce the length of the input messages" in err_msg:
                    gen_signature = "context_length_exceeded"
                elif "Request timed out" in err_msg or "APITimeoutError" in err_msg:
                    gen_signature = "llm_timeout"
                else:
                    gen_signature = "llm_call_fail"

                logger.exception(
                    "GEN_FAIL for %s trial%d: err=%s gen_elapsed=%.2fs context_num_files=%d signature=%s",
                    task_id,
                    trial_id,
                    e,
                    gen_elapsed,
                    context_num_files,
                    gen_signature,
                )

                full_result = {
                    "task_id": task_id,
                    "trial_id": trial_id,
                    "model": model_name,
                    "prompt_hash": _sha256(
                        f"{task.get('repo','')}|{task.get('base_commit','')}|{task.get('problem_statement','')}"
                    ),
                    "diff": "",
                    "edit_script": "",
                    "patch_lines_added": 0,
                    "patch_lines_removed": 0,
                    "files_changed": 0,
                    "timestamp": run_ts,
                    "seed": seed,
                    "repo": task.get("repo"),
                    "base_commit": task.get("base_commit"),
                    "taxonomy_version": config["experiment"].get("taxonomy_version", "B-v2"),
                    "gen_elapsed_sec": gen_elapsed,
                    "context_used": context_used,
                    "context_num_files": context_num_files,
                    "repo_context_preview": repo_context_preview,
                    "edit_used": edit_used,
                    "edit_parse_ok": False,
                    "edit_parse_reason": gen_signature,
                    "diff_export_ok": False,
                    "diff_export_reason": "",
                    "success": False,
                    "stage": "GEN",
                    "error_type": "GEN_FAIL",
                    "signature": gen_signature,
                    "stdout": "",
                    "stderr": err_msg,
                    "returncode": None,
                    "timeout": False,
                    "elapsed_sec": gen_elapsed,
                    "test_command": "",
                    "generated_diff": "",
                    "exception": repr(e),
                }
                recorder.log_trial(full_result)
                continue

            gen_elapsed = time.time() - t0

            # -------------------------------
            # 3) Materialize diff only
            # -------------------------------
            logger.info("Materializing diff locally for %s trial%d ...", task_id, trial_id)
            exec_result = materializer.execute_edits(task_in, edit_script)

            # parse bookkeeping
            if exec_result.get("error_type") == "EDIT_PARSE_FAIL":
                edit_parse_ok = False
                edit_parse_reason = exec_result.get("signature", "invalid_edit_script")
            elif exec_result.get("stage") == "REPO":
                edit_parse_ok = False
                edit_parse_reason = "not_reached"
            else:
                edit_parse_ok = True
                edit_parse_reason = "ok"

            # diff bookkeeping
            diff = exec_result.get("generated_diff", "") or ""
            diff_export_ok = bool(diff.strip())

            if diff_export_ok:
                diff_export_reason = "ok"
            else:
                st = exec_result.get("stage", "")
                sig = exec_result.get("signature", "")
                diff_export_reason = f"empty_generated_diff:{st}:{sig}"

            patch_added, patch_removed, files_changed = (
                count_diff_lines(diff) if diff_export_ok else (0, 0, 0)
            )

            logger.info(
                "Pre-harness result for %s trial%d: %s (%s), diff_ok=%s, +%d -%d in %d files",
                task_id,
                trial_id,
                exec_result.get("error_type"),
                exec_result.get("signature"),
                diff_export_ok,
                patch_added,
                patch_removed,
                files_changed,
            )

            full_result = {
                "task_id": task_id,
                "trial_id": trial_id,
                "model": model_name,
                "prompt_hash": _sha256(
                    f"{task.get('repo','')}|{task.get('base_commit','')}|{task.get('problem_statement','')}"
                ),
                "diff": diff,
                "edit_script": edit_script,
                "patch_lines_added": patch_added,
                "patch_lines_removed": patch_removed,
                "files_changed": files_changed,
                "timestamp": run_ts,
                "seed": seed,
                "repo": task.get("repo"),
                "base_commit": task.get("base_commit"),
                "taxonomy_version": config["experiment"].get("taxonomy_version", "B-v2"),
                "gen_elapsed_sec": gen_elapsed,
                "context_used": context_used,
                "context_num_files": context_num_files,
                "repo_context_preview": repo_context_preview,
                "edit_used": edit_used,
                "edit_parse_ok": edit_parse_ok,
                "edit_parse_reason": edit_parse_reason,
                "diff_export_ok": diff_export_ok,
                "diff_export_reason": diff_export_reason,
                **exec_result,
            }
            recorder.log_trial(full_result)

            # -------------------------------
            # 4) Add only harness-ready predictions
            # -------------------------------
            if exec_result.get("success") and exec_result.get("error_type") == "PRED_READY" and diff_export_ok:
                predictions_by_instance[task_id] = {
                    "instance_id": task_id,
                    "model_name_or_path": model_name,
                    "model_patch": diff,
                }

    logger.info("Pre-harness generation/materialization completed.")

    predictions = list(predictions_by_instance.values())
    logger.info("Harness-ready predictions: %d", len(predictions))

    pred_path = recorder.run_dir / "predictions.jsonl"
    write_predictions_jsonl(pred_path, predictions)
    logger.info("Wrote predictions to %s", pred_path)

    if not is_docker_available():
        logger.error("Docker is required for SWE-bench evaluation but is not available.")
        sys.exit(1)

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