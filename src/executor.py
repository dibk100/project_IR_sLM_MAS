import subprocess
import time
from pathlib import Path
import shutil
from typing import Dict, Any
import json

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
        setup = self._setup_repo(task, repo_path)
        if not setup.get("ok", False):
            return {
                "success": False,
                "stage": "REPO",
                "error_type": "REPO_FAIL",
                "signature": setup.get("signature", "repo_setup_failed"),
                "stderr": setup.get("stderr", "Failed to setup repository"),
                "stdout": setup.get("stdout", ""),
                "returncode": setup.get("returncode", -1),
                "elapsed_sec": time.time() - start_time,
                "timeout": False,
                "test_command": "",
                "docker_image": self.docker_image,
            }

        patch_path = repo_path / "patch.diff"
        applied = False

        try:
            # 2. Apply Diff
            if diff.strip():
                patch_path.write_text(diff)
                apply_cmd = ["git", "apply", str(patch_path)]
                subprocess.run(apply_cmd, cwd=repo_path, check=True, capture_output=True, text=True)
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
                timeout=self.timeout,
                text=True
            )
            
            elapsed = time.time() - start_time

            err = (proc.stderr or "").lower()
            sig = "docker_nonzero_returncode"
            if "pull access denied" in err or "repository does not exist" in err:
                sig = "docker_image_not_found"
            elif "docker login" in err:
                sig = "docker_login_required"
            elif "cannot connect to the docker daemon" in err:
                sig = "docker_daemon_unreachable"
            elif "permission denied" in err and "docker.sock" in err:
                sig = "docker_permission_denied"
            elif "tls handshake timeout" in err or "i/o timeout" in err or "connection refused" in err:
                sig = "docker_network_error"

            if proc.returncode != 0:
                return {
                    "success": False,
                    "stage": "EXEC",
                    "error_type": "EXEC_FAIL",
                    "signature": sig,
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "returncode": proc.returncode,
                    "timeout": False,
                    "elapsed_sec": elapsed,
                    "test_command": test_cmd,
                    "docker_image": self.docker_image,
                }
            return {
                "success": True,
                "stage": "EXEC",
                "error_type": "PASS",
                "signature": "success",
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "returncode": proc.returncode,
                "timeout": False,
                "elapsed_sec": elapsed,
                "test_command": test_cmd,
                "docker_image": self.docker_image,
            }
        except subprocess.TimeoutExpired as e:
            elapsed = time.time() - start_time
            return {
                "stage": "EXEC",
                "stdout": e.stdout if e.stdout else "",
                "stderr": e.stderr if e.stderr else "Timeout Expired",
                "returncode": 124,
                "timeout": True,
                "elapsed_sec": elapsed,
                "test_command": task.get("test_command", ""),
                "success": False,
                "error_type": "TIMEOUT",
                "signature": "timeout",
                "docker_image": self.docker_image,
            }
        except subprocess.CalledProcessError as e:
            elapsed = time.time() - start_time
            # 여기선 git apply 실패만 발생 (docker는 check=True 안 씀)
            return {
                "stage": "PATCH",
                "stdout": e.stdout if e.stdout else "",
                "stderr": f"Git Apply Failed: {e.stderr if e.stderr else str(e)}",
                "returncode": e.returncode,
                "timeout": False,
                "elapsed_sec": elapsed,
                "test_command": "git apply",
                "success": False,
                "error_type": "PATCH_FAIL",
                # Let taxonomy.py infer 4-bucket signature from stderr:
                # # - git_apply_corrupt_patch / git_apply_path_missing / git_apply_hunk_failed / git_apply_failed
                # "signature": "git_apply_failed",
                "signature": "",
                "docker_image": self.docker_image,
            }
        except Exception as e:
            elapsed = time.time() - start_time
            return {
                "stage": "EXEC",
                "stdout": "",
                "stderr": f"Executor Exception: {str(e)}",
                "returncode": -1,
                "timeout": False,
                "elapsed_sec": elapsed,
                "test_command": "executor_internal",
                "success": False,
                "error_type": "EXEC_FAIL",
                "signature": "executor_exception",
                "docker_image": self.docker_image,
            }
        finally:
            # 4. Cleanup: Revert patch
            if applied:
                subprocess.run(["git", "restore", "."], cwd=repo_path, check=False, capture_output=True, text=True)
                subprocess.run(["git", "clean", "-fd"], cwd=repo_path, check=False, capture_output=True, text=True)

    def _setup_repo(self, task: Dict[str, Any], repo_path: Path) -> Dict[str, Any]:
        """
        Clones or updates the repo and resets to base_commit.
        """
        repo_url = f"https://github.com/{task.get('repo')}.git"
        base_commit = task.get("base_commit", "HEAD")
        
        try:
            if not (repo_path / ".git").exists():
                if repo_path.exists():
                    shutil.rmtree(repo_path, ignore_errors=True)
                print(f"Cloning {repo_url} to {repo_path}...")
                subprocess.run(
                    ["git", "clone", repo_url, str(repo_path)],
                    check=True,
                    capture_output=True,
                    text=True
                )
            
            # Fetch and Reset (ensure base_commit exists locally)
            subprocess.run(["git", "fetch", "--all", "--tags"], cwd=repo_path, check=True, capture_output=True, text=True)
            subprocess.run(["git", "reset", "--hard", base_commit], cwd=repo_path, check=True, capture_output=True, text=True)
            subprocess.run(["git", "clean", "-fd"], cwd=repo_path, check=True, capture_output=True, text=True)
            return {"ok": True}

        except subprocess.CalledProcessError as e:
            # git clone/fetch/reset/clean failures
            stderr = e.stderr or ""
            stdout = e.stdout or ""
            sig = "git_cmd_failed"
            # 좀 더 구체적으로
            cmd = " ".join(e.cmd) if isinstance(e.cmd, (list, tuple)) else str(e.cmd)
            if "reset" in cmd:
                sig = "git_reset_failed"
            elif "fetch" in cmd:
                sig = "git_fetch_failed"
            elif "clone" in cmd:
                sig = "git_clone_failed"
            print(f"Repo setup failed: {e}")
            return {
                "ok": False,
                "signature": sig,
                "returncode": e.returncode,
                "stdout": stdout,
                "stderr": stderr or str(e),
            }
        except Exception as e:
            print(f"Repo setup failed: {e}")
            return {
                "ok": False,
                "signature": "repo_setup_exception",
                "returncode": -1,
                "stdout": "",
                "stderr": str(e),
            }

    def execute_edits(self, task: Dict[str, Any], edit_script: str) -> Dict[str, Any]:
        start_time = time.time()
        applied = False

        repo_name = task.get("repo", "unknown_repo").replace("/", "__")
        repo_path = self.work_dir / repo_name

        try:
            # 1. Setup
            setup = self._setup_repo(task, repo_path)
            if not setup.get("ok", False):
                return {
                    "success": False,
                    "stage": "REPO",
                    "error_type": "REPO_FAIL",
                    "signature": setup.get("signature", "repo_setup_failed"),
                    "stderr": setup.get("stderr", ""),
                    "stdout": setup.get("stdout", ""),
                    "returncode": setup.get("returncode", -1),
                    "timeout": False,
                    "elapsed_sec": time.time() - start_time,
                    "test_command": "",
                    "docker_image": self.docker_image,
                }

            # 2. Parse JSON 실패
            try:
                data = json.loads(edit_script)
                edits = data.get("edits", [])
                if not isinstance(edits, list) or not edits:
                    raise ValueError("missing_or_empty_edits")
            except Exception as e:
                return {
                    "success": False,
                    "stage": "EDIT_PARSE",
                    "error_type": "GEN_FAIL",
                    "signature": "invalid_edit_script",
                    "stderr": str(e),
                    "stdout": "",
                    "returncode": -1,
                    "timeout": False,
                    "elapsed_sec": time.time() - start_time,
                    "test_command": "",
                    "docker_image": self.docker_image,
                    "generated_diff": "",
                }

            # 3. Apply edits
            try:
                for edit in edits:
                    op = edit.get("op")
                    path = edit.get("path")

                    file_path = repo_path / path
                    if not file_path.exists():
                        raise FileNotFoundError(path)

                    content = file_path.read_text().splitlines(keepends=True)

                    if op == "replace_range":
                        start = edit["start_line"] - 1
                        end = edit["end_line"]
                        if start < 0 or end > len(content):
                            raise IndexError("range_oob")
                        new_lines = edit["text"].splitlines(keepends=True)
                        content[start:end] = new_lines

                    elif op == "insert_after":
                        line = edit["line"]
                        if line < 1 or line > len(content):
                            raise IndexError("insert_oob")
                        new_lines = edit["text"].splitlines(keepends=True)
                        content[line:line] = new_lines

                    else:
                        raise ValueError("unknown_op")

                    file_path.write_text("".join(content))
                    applied = True  # 첫 write 발생 시점부터 dirty 가능성 존재

            except FileNotFoundError as e:
                return {
                    "success": False,
                    "stage": "EDIT_APPLY",
                    "error_type": "APPLY_FAIL",
                    "signature": "edit_apply_path_missing",
                    "stderr": str(e),
                    "stdout": "",
                    "returncode": -1,
                    "timeout": False,
                    "elapsed_sec": time.time() - start_time,
                    "test_command": "edit_apply",
                    "docker_image": self.docker_image,
                    "generated_diff": "",
                }

            except IndexError as e:
                return {
                    "success": False,
                    "stage": "EDIT_APPLY",
                    "error_type": "APPLY_FAIL",
                    "signature": "edit_apply_range_oob",
                    "stderr": str(e),
                    "stdout": "",
                    "returncode": -1,
                    "timeout": False,
                    "elapsed_sec": time.time() - start_time,
                    "test_command": "edit_apply",
                    "docker_image": self.docker_image,
                    "generated_diff": "",
                }

            except ValueError as e:
                return {
                    "success": False,
                    "stage": "EDIT_APPLY",
                    "error_type": "APPLY_FAIL",
                    "signature": "edit_apply_unknown_op",
                    "stderr": str(e),
                    "stdout": "",
                    "returncode": -1,
                    "timeout": False,
                    "elapsed_sec": time.time() - start_time,
                    "test_command": "edit_apply",
                    "docker_image": self.docker_image,
                    "generated_diff": "",
                }

            # 4. Export git diff
            diff_proc = subprocess.run(["git", "diff"], cwd=repo_path, capture_output=True, text=True)
            generated_diff = diff_proc.stdout

            # 5. Docker test
            test_cmd = task.get("test_command", "echo 'No test command'")
            docker_cmd = [
                "docker", "run", "--rm",
                "-v", f"{repo_path.absolute()}:/testbed",
                "-w", "/testbed",
                self.docker_image,
                "/bin/bash", "-c", test_cmd
            ]

            try:
                proc = subprocess.run(
                    docker_cmd,
                    capture_output=True,
                    timeout=self.timeout,
                    text=True
                )
            except subprocess.TimeoutExpired as e:
                elapsed = time.time() - start_time
                return {
                    "success": False,
                    "stage": "EXEC",
                    "error_type": "TIMEOUT",
                    "signature": "timeout",
                    "stdout": e.stdout if e.stdout else "",
                    "stderr": e.stderr if e.stderr else "Timeout Expired",
                    "returncode": 124,
                    "timeout": True,
                    "elapsed_sec": elapsed,
                    "test_command": test_cmd,
                    "docker_image": self.docker_image,
                    "generated_diff": generated_diff,
                }

            elapsed = time.time() - start_time
            
            err = (proc.stderr or "").lower()
            sig = "docker_nonzero_returncode"
            if "pull access denied" in err or "repository does not exist" in err:
                sig = "docker_image_not_found"
            elif "docker login" in err:
                sig = "docker_login_required"
            elif "cannot connect to the docker daemon" in err:
                sig = "docker_daemon_unreachable"
            elif "permission denied" in err and "docker.sock" in err:
                sig = "docker_permission_denied"
            elif "tls handshake timeout" in err or "i/o timeout" in err or "connection refused" in err:
                sig = "docker_network_error"

            if proc.returncode != 0:
                return {
                    "success": False,
                    "stage": "EXEC",
                    "error_type": "EXEC_FAIL",
                    "signature": sig,
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "returncode": proc.returncode,
                    "timeout": False,
                    "elapsed_sec": elapsed,
                    "test_command": test_cmd,
                    "docker_image": self.docker_image,
                    "generated_diff": generated_diff,
                }

            return {
                "success": True,
                "stage": "EXEC",
                "error_type": "PASS",
                "signature": "success",
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "returncode": proc.returncode,
                "timeout": False,
                "elapsed_sec": elapsed,
                "test_command": test_cmd,
                "docker_image": self.docker_image,
                "generated_diff": generated_diff,
            }

        finally:
            if applied:
                subprocess.run(["git", "restore", "."], cwd=repo_path, check=False, capture_output=True, text=True)
                subprocess.run(["git", "clean", "-fd"], cwd=repo_path, check=False, capture_output=True, text=True)