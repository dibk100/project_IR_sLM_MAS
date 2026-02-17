import argparse
import yaml
import sys
import time
import hashlib
import random
from datetime import datetime
from pathlib import Path
from src.task_loader import TaskLoader
from src.generate_agent import GenerateAgent
from src.context_collector import ContextCollector
from src.executor import Executor
from src.verifier import Verifier
from src.recorder import Recorder
from src.utils import setup_logging, count_diff_lines, check_docker, validate_unified_diff

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

    # Check Docker
    if not check_docker():
        logger.error("Docker is not running or not installed. Exiting.")
        sys.exit(1)
    
    # Components
    loader = TaskLoader(project_root / config["experiment"]["task_subset"],max_tasks=config["experiment"].get("max_tasks"))
    agent = GenerateAgent(config["agent"]["model"], config["agent"])
    executor = Executor(config["environment"]["timeout_seconds"], work_dir=project_root / "workspace")
    verifier = Verifier()

    # Step2-1 minimal context collector (file candidates only)
    max_ctx_files = int(config.get("constraints", {}).get("context_max_files", 80))
    ctx = ContextCollector(max_files=max_ctx_files)
    
    try:
        tasks = loader.load_tasks()
        logger.info(f"Loaded {len(tasks)} tasks.")
    except Exception as e:
        logger.error(f"Failed to load tasks: {e}")
        sys.exit(1)
    
    max_trials = int(config["experiment"].get("max_trials", 1))  # task당 trial 수

    for i, task in enumerate(tasks):
        # Compute repo_path the same way Executor does (workspace/<repo__name>)
        repo_name = task.get("repo", "unknown_repo").replace("/", "__")
        repo_path = (project_root / "workspace" / repo_name)
             
        task_id = task.get("instance_id", "unknown")
        logger.info(f"Processing Task ({i+1}): {task_id}")

        for trial_id in range(max_trials):  # 0-based (trial0) 유지
            run_ts = datetime.utcnow().isoformat()

            # 1. Generate (GEN_FAIL fail-fast)
            logger.info("Generating patch...")
            t0 = time.time()
            
            # Inject minimal repo context (existing file list) if available.
            # IMPORTANT: do NOT mutate `task` in-place (avoid cross-trial side effects).
            task_in = dict(task)
            repo_ctx = ctx.collect(repo_path)
            
            file_candidates = list(getattr(repo_ctx, "file_candidates", []) or [])
            context_used = bool(file_candidates)
            context_num_files = len(file_candidates)
            repo_context_preview = ""
            if context_used:
                injected_context = "Existing files (choose from these):\n" + "\n".join(file_candidates)
                task_in["repo_context"] = injected_context

                preview_lines = ["Existing files (choose from these):"] + file_candidates[:20]
                repo_context_preview = "\n".join(preview_lines)
                if len(file_candidates) > 20:
                    repo_context_preview += f"\n... (+{len(file_candidates) - 20} more)"
                    
            # Step2-2: formatter bookkeeping (single-sLM 2-call)
            format_used = False
            format_ok = False
            format_reason = ""
            
            try:
                diff = agent.generate(task_in)
            except Exception as e:
                gen_elapsed = time.time() - t0
                logger.error(f"GEN_FAIL: LLM generation failed for {task_id} trial{trial_id}: {e}")
                
                diff = ""
                patch_added = patch_removed = files_changed = 0

                exec_result = {
                    "stdout": "",
                    "stderr": str(e),
                    "returncode": None,
                    "timeout": False,
                    "elapsed_sec": gen_elapsed,             # executor/도커 시간
                    "signature": "llm_call_fail",
                    "test_command": "",
                    "stage": "GEN",
                    "error_type": "GEN_FAIL",
                }
                verify_result = verifier.verify(exec_result)

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
                    "gen_elapsed_sec": gen_elapsed,                         # sLM 생성 시간
                    "context_used": context_used,
                    "context_num_files": context_num_files,
                    "repo_context_preview": repo_context_preview,
                    "format_used": format_used,
                    "format_ok": format_ok,
                    "format_reason": format_reason,
                    **exec_result,
                    **verify_result,
                }
                recorder.log_trial(full_result)
                continue

            gen_elapsed = time.time() - t0
            
            # Step2-2: diff format guardrail + optional formatter (single-sLM 2-call)
            max_files = int(config.get("constraints", {}).get("max_files", 2))
            ok, reason, files = validate_unified_diff(
                diff,
                max_files=max_files,
            )
            # P0: git apply --check trigger (prefer real apply feasibility over string-shape checks)
            # If --check fails, route into formatter once (same as invalid diff format path).
            if ok:
                try:
                    # Ensure repo exists locally (same workspace path as Executor).
                    # This is intentionally minimal and reuses Executor's setup logic.
                    if not (repo_path / ".git").exists():
                        setup = executor._setup_repo(task_in, repo_path)  # minimal reuse
                        if not setup.get("ok", False):
                            ok = False
                            reason = f"repo_setup_failed_for_apply_check:{setup.get('signature','repo_setup_failed')}"

                    if ok:
                        check_patch_path = repo_path / "__patch_check.diff"
                        check_patch_path.write_text(diff, encoding="utf-8")

                        proc = subprocess.run(
                            ["git", "apply", "--check", str(check_patch_path)],
                            cwd=repo_path,
                            capture_output=True,
                            text=True,
                        )

                        if proc.returncode != 0:
                            ok = False
                            reason = "git_apply_check_failed"

                        # best-effort cleanup
                        try:
                            check_patch_path.unlink(missing_ok=True)
                        except Exception:
                            pass

                except Exception as e:
                    ok = False
                    reason = f"git_apply_check_exception:{e}"

            if not ok:
                # Try formatter once (only if agent provides it)
                format_used = True
                format_reason = reason
                issue_text = task_in.get("problem_statement", "") or ""
                repo_context = task_in.get("repo_context", "") or ""
                try:
                    logger.info(f"Formatter call: {task_id} trial{trial_id} (reason={reason})")
                    diff2 = agent.format_diff(
                        raw_diff=diff,
                        issue_text=issue_text,
                        repo_context=repo_context,
                        max_files=max_files,
                    )
                    ok2, reason2, files2 = validate_unified_diff(diff2, max_files=max_files)
                    format_ok = bool(ok2)
                    if ok2:
                        diff = diff2
                        ok, reason, files = ok2, reason2, files2
                        logger.info(f"Formatter success: {task_id} trial{trial_id}")
                    else:
                        logger.error(f"Formatter failed: {task_id} trial{trial_id}: {reason2}")
                except Exception as e:
                    format_ok = False
                    format_reason = f"formatter_exception: {e}"
                    logger.error(f"Formatter exception: {task_id} trial{trial_id}: {e}")

            # If still invalid after formatter attempt, record as GEN_FAIL.
            if not ok:
                logger.error(f"GEN_FAIL: invalid diff format for {task_id} trial{trial_id}: {reason}")
                patch_added = patch_removed = files_changed = 0
                sig = "empty_diff" if (not diff or not diff.strip()) else "invalid_diff_format"

                exec_result = {
                    "stdout": "",
                    "stderr": "",
                    "returncode": None,
                    "timeout": False,
                    "elapsed_sec": gen_elapsed,
                    "signature": sig,
                    "test_command": "",
                    "stage": "GEN",
                    "error_type": "GEN_FAIL",
                }
                verify_result = verifier.verify(exec_result)

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
                    "gen_elapsed_sec": gen_elapsed,
                    "context_used": context_used,
                    "context_num_files": context_num_files,
                    "repo_context_preview": repo_context_preview,
                    "format_used": format_used,
                    "format_ok": format_ok,
                    "format_reason": format_reason,
                    **exec_result,
                    **verify_result,
                }
                recorder.log_trial(full_result)
                continue

            patch_added, patch_removed, files_changed = count_diff_lines(diff)
            logger.info(f"Generated diff: +{patch_added} -{patch_removed} lines in {files_changed} files.")

            # 2. Execute
            logger.info("Executing test in Docker...")
            exec_result = executor.execute(task_in, diff)

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
                "gen_elapsed_sec": gen_elapsed,
                "context_used": context_used,
                "context_num_files": context_num_files,
                "repo_context_preview": repo_context_preview,
                "format_used": format_used,
                "format_ok": format_ok,
                "format_reason": format_reason,
                **exec_result,
                **verify_result
            }
            recorder.log_trial(full_result)

    logger.info("Experiment Completed.")

if __name__ == "__main__":
    main()
