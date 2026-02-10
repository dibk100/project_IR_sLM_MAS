import subprocess
import time
import os
import shutil
from pathlib import Path
from typing import Dict, Any, Tuple

class Executor:
    def __init__(self, timeout_seconds: int = 300, work_dir: Path = Path("workspace")):
        self.timeout = timeout_seconds
        self.work_dir = work_dir
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.docker_image = "swebench/sweb.eval.x86_64:latest"

    def execute(self, task: Dict[str, Any], diff: str) -> Dict[str, Any]:
        """
        1. Setup Repo (Checkout base commit)
        2. Apply Diff
        3. Run Test in Docker
        4. Cleanup (Revert)
        """
        start_time = time.time()
        
        repo_name = task.get("repo", "unknown_repo").replace("/", "__")
        repo_path = self.work_dir / repo_name
        
        # 1. Setup Repo
        if not self._setup_repo(task, repo_path):
            return {
                "success": False,
                "error_type": "REPO_SETUP_FAIL",
                "stderr": "Failed to setup repository",
                "returncode": -1,
                "elapsed_sec": time.time() - start_time,
                "timeout": False
            }

        patch_path = repo_path / "patch.diff"
        applied = False

        try:
            # 2. Apply Diff
            if diff.strip():
                patch_path.write_text(diff)
                apply_cmd = ["git", "apply", str(patch_path)]
                subprocess.run(apply_cmd, cwd=repo_path, check=True, capture_output=True)
                applied = True
            
            # 3. Run Test (Docker)
            test_cmd = task.get("test_command", "echo 'No test command'")
            # Using a simplified docker run for now. 
            # In real SWE-bench, we might need specific envs, but user said "sweb.eval.x86_64".
            # We mount the repo to /testbed
            
            docker_cmd = [
                "docker", "run", "--rm",
                "-v", f"{repo_path.absolute()}:/testbed",
                "-w", "/testbed",
                self.docker_image,
                "/bin/bash", "-c", test_cmd
            ]
            
            proc = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            elapsed = time.time() - start_time
            return {
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "returncode": proc.returncode,
                "timeout": False,
                "elapsed_sec": elapsed,
                "test_command": test_cmd
            }

        except subprocess.TimeoutExpired as e:
            elapsed = time.time() - start_time
            return {
                "stdout": e.stdout.decode() if e.stdout else "",
                "stderr": e.stderr.decode() if e.stderr else "Timeout Expired",
                "returncode": 124,
                "timeout": True,
                "elapsed_sec": elapsed,
                "test_command": task.get("test_command", "")
            }
        except subprocess.CalledProcessError as e:
            elapsed = time.time() - start_time
            return {
                "stdout": e.stdout.decode() if e.stdout else "",
                "stderr": f"Git Apply Failed: {e.stderr.decode() if e.stderr else str(e)}",
                "returncode": e.returncode,
                "timeout": False,
                "elapsed_sec": elapsed,
                "test_command": "git apply"
            }
        except Exception as e:
            elapsed = time.time() - start_time
            return {
                "stdout": "",
                "stderr": f"Executor Exception: {str(e)}",
                "returncode": -1,
                "timeout": False,
                "elapsed_sec": elapsed,
                "test_command": "executor_internal"
            }
        finally:
            # 4. Cleanup: Revert patch
            if applied:
                 subprocess.run(["git", "restore", "."], cwd=repo_path, check=False, capture_output=True)
                 subprocess.run(["git", "clean", "-fd"], cwd=repo_path, check=False, capture_output=True)

    def _setup_repo(self, task: Dict[str, Any], repo_path: Path) -> bool:
        """
        Clones or updates the repo and resets to base_commit.
        """
        repo_url = f"https://github.com/{task.get('repo')}.git"
        base_commit = task.get("base_commit", "HEAD")
        
        try:
            if not repo_path.exists():
                print(f"Cloning {repo_url} to {repo_path}...")
                subprocess.run(["git", "clone", repo_url, str(repo_path)], check=True, capture_output=True)
            
            # Fetch and Reset
            # subprocess.run(["git", "fetch", "--all"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "reset", "--hard", base_commit], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "clean", "-fd"], cwd=repo_path, check=True, capture_output=True)
            return True
        except Exception as e:
            print(f"Repo setup failed: {e}")
            return False
