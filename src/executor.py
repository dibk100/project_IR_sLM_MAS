import subprocess
import time
from pathlib import Path
import shutil
from typing import Dict, Any
import json
import ast

class Executor:
    def __init__(self, timeout_seconds: int = 300, work_dir: Path = Path("workspace")):
        self.timeout = timeout_seconds
        self.work_dir = work_dir
        self.work_dir.mkdir(parents=True, exist_ok=True)
        
    def _result(
        self,
        success: bool,
        stage: str,
        error_type: str,
        signature: str,
        start_time: float,
        stdout: str = "",
        stderr: str = "",
        returncode: int = -1,
        timeout: bool = False,
        test_command: str = "",
        generated_diff: str = "",
        exception: str = "",
    ) -> Dict[str, Any]:
        return {
            "success": success, "stage": stage, "error_type": error_type, "signature": signature,
            "stdout": stdout, "stderr": stderr, "returncode": returncode, "timeout": timeout,
            "elapsed_sec": time.time() - start_time, "test_command": test_command,
            "generated_diff": generated_diff,"exception": exception,
        }

    def execute_edits(self, task: Dict[str, Any], edit_script: str) -> Dict[str, Any]:
        start_time = time.time()
        applied = False

        repo_name = task.get("repo", "unknown_repo").replace("/", "__")
        repo_path = self.work_dir / repo_name

        try:
            # -------------------------------
            # 1. Setup repository
            # -------------------------------
            setup = self._setup_repo(task, repo_path)
            if not setup.get("ok", False):
                return self._result(
                    success=False,
                    stage="REPO",
                    error_type="REPO_FAIL",
                    signature=setup.get("signature", "repo_setup_failed"),
                    start_time=start_time,
                    stdout=setup.get("stdout", ""),
                    stderr=setup.get("stderr", ""),
                    returncode=setup.get("returncode", -1),
                )

            # -------------------------------
            # 2. Parse edit script
            # -------------------------------
            try:
                data = json.loads(edit_script)
                edits = data.get("edits", [])
                if not isinstance(edits, list) or not edits:
                    raise ValueError("missing_or_empty_edits")
            except Exception as e:
                return self._result(
                    success=False,
                    stage="EDIT_PARSE",
                    error_type="GEN_FAIL",
                    signature="invalid_edit_script",
                    start_time=start_time,
                    stderr=str(e),
                    exception=repr(e),
                )

            # -------------------------------
            # 3. Apply edits
            # -------------------------------
            try:
                for edit in edits:
                    op = edit.get("op")
                    path = edit.get("path")

                    if path is None:
                        return self._result(
                            success=False,
                            stage="EDIT_APPLY",
                            error_type="APPLY_FAIL",
                            signature="edit_apply_path_missing",
                            start_time=start_time,
                            test_command="edit_apply",
                        )

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
                    applied = True

            except FileNotFoundError as e:
                return self._result(
                    success=False,
                    stage="EDIT_APPLY",
                    error_type="APPLY_FAIL",
                    signature="edit_apply_path_missing",
                    start_time=start_time,
                    stderr=str(e),
                    test_command="edit_apply",
                    exception=repr(e),
                )

            except IndexError as e:
                return self._result(
                    success=False,
                    stage="EDIT_APPLY",
                    error_type="APPLY_FAIL",
                    signature="edit_apply_range_oob",
                    start_time=start_time,
                    stderr=str(e),
                    test_command="edit_apply",
                    exception=repr(e),
                )

            except ValueError as e:
                return self._result(
                    success=False,
                    stage="EDIT_APPLY",
                    error_type="APPLY_FAIL",
                    signature="edit_apply_unknown_op",
                    start_time=start_time,
                    stderr=str(e),
                    test_command="edit_apply",
                    exception=repr(e),
                )

            # -------------------------------
            # 4. Export diff
            # -------------------------------
            diff_proc = subprocess.run(
                ["git", "diff"],
                cwd=repo_path,
                capture_output=True,
                text=True,
            )
            generated_diff = diff_proc.stdout

            # -------------------------------
            # 5. Build test command
            # -------------------------------
            try:
                fail_tests = self._parse_test_list(task["FAIL_TO_PASS"])
                pass_tests = self._parse_test_list(task["PASS_TO_PASS"])
            except Exception as e:
                return self._result(
                    success=False,
                    stage="TEST_SPEC",
                    error_type="TEST_SPEC_FAIL",
                    signature="invalid_test_spec",
                    start_time=start_time,
                    stderr=str(e),
                    generated_diff=generated_diff,
                    exception=repr(e),
                )

            tests = fail_tests + pass_tests
            test_cmd = "pytest -q " + " ".join(tests)
            python_bin = "python"

            # -------------------------------
            # 6. Install bootstrap tools
            # -------------------------------
            try:
                pip_bootstrap = subprocess.run(
                    [python_bin, "-m", "pip", "install", "-U", "pip", "setuptools", "wheel"],
                    cwd=repo_path,
                    capture_output=True,
                    timeout=self.timeout,
                    text=True,
                )
            except subprocess.TimeoutExpired as e:
                return self._result(
                    success=False,
                    stage="INSTALL",
                    error_type="INSTALL_TIMEOUT",
                    signature="pip_bootstrap_timeout",
                    start_time=start_time,
                    stdout=e.stdout or "",
                    stderr=e.stderr or "",
                    returncode=-1,
                    timeout=True,
                    test_command=test_cmd,
                    generated_diff=generated_diff,
                    exception=repr(e),
                )

            if pip_bootstrap.returncode != 0:
                return self._result(
                    success=False,
                    stage="INSTALL",
                    error_type="INSTALL_FAIL",
                    signature="pip_bootstrap_failed",
                    start_time=start_time,
                    stdout=pip_bootstrap.stdout,
                    stderr=pip_bootstrap.stderr,
                    returncode=pip_bootstrap.returncode,
                    test_command=test_cmd,
                    generated_diff=generated_diff,
                )

            # -------------------------------
            # 7. Editable install
            # -------------------------------
            try:
                install_proc = subprocess.run(
                    [python_bin, "-m", "pip", "install", "-e", "."],
                    cwd=repo_path,
                    capture_output=True,
                    timeout=self.timeout,
                    text=True,
                )
            except subprocess.TimeoutExpired as e:
                return self._result(
                    success=False,
                    stage="INSTALL",
                    error_type="INSTALL_TIMEOUT",
                    signature="editable_install_timeout",
                    start_time=start_time,
                    stdout=e.stdout or "",
                    stderr=e.stderr or "",
                    returncode=-1,
                    timeout=True,
                    test_command=test_cmd,
                    generated_diff=generated_diff,
                )

            if install_proc.returncode != 0:
                return self._result(
                    success=False,
                    stage="INSTALL",
                    error_type="INSTALL_FAIL",
                    signature="editable_install_failed",
                    start_time=start_time,
                    stdout=install_proc.stdout,
                    stderr=install_proc.stderr,
                    returncode=install_proc.returncode,
                    test_command=test_cmd,
                    generated_diff=generated_diff,
                )

            # -------------------------------
            # 8. Run tests
            # -------------------------------
            try:
                proc = subprocess.run(
                    [python_bin, "-m", "pytest", "-q", *tests],
                    cwd=repo_path,
                    capture_output=True,
                    timeout=self.timeout,
                    text=True,
                )
            except subprocess.TimeoutExpired as e:
                return self._result(
                    success=False,
                    stage="TEST",
                    error_type="TEST_TIMEOUT",
                    signature="test_timeout",
                    start_time=start_time,
                    stdout=e.stdout or "",
                    stderr=e.stderr or "",
                    returncode=-1,
                    timeout=True,
                    test_command=test_cmd,
                    generated_diff=generated_diff,
                )

            if proc.returncode != 0:
                return self._result(
                    success=False,
                    stage="TEST",
                    error_type="TEST_FAIL",
                    signature="test_failed",
                    start_time=start_time,
                    stdout=proc.stdout,
                    stderr=proc.stderr,
                    returncode=proc.returncode,
                    test_command=test_cmd,
                    generated_diff=generated_diff,
                )

            return self._result(
                success=True,
                stage="EXEC",
                error_type="DONE",
                signature="success",
                start_time=start_time,
                stdout=proc.stdout,
                stderr=proc.stderr,
                returncode=proc.returncode,
                test_command=test_cmd,
                generated_diff=generated_diff,
            )
        except Exception as e:
            return self._result(
                success=False,
                stage="EXEC",
                error_type="EXEC_EXCEPTION",
                signature="unhandled_exception",
                start_time=start_time,
                stderr=str(e),
                exception=repr(e),
            )
        finally:
            # -------------------------------
            # 9. Cleanup repo
            # -------------------------------
            if applied:
                subprocess.run(
                    ["git", "restore", "."],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                )

                subprocess.run(
                    ["git", "clean", "-fd"],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                )
                
    def _parse_test_list(self, value):
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            parsed = ast.literal_eval(value)
            if isinstance(parsed, list):
                return parsed
        raise ValueError("invalid_test_list")

    def _setup_repo(self, task: Dict[str, Any], repo_path: Path) -> Dict[str, Any]:
        repo_url = f"https://github.com/{task.get('repo')}.git"
        base_commit = task.get("base_commit", "HEAD")

        try:
            if not (repo_path / ".git").exists():
                if repo_path.exists():
                    shutil.rmtree(repo_path, ignore_errors=True)

                subprocess.run(
                    ["git", "clone", repo_url, str(repo_path)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                subprocess.run(
                    ["git", "fetch", "--all"],
                    cwd=repo_path,
                    check=True,
                    capture_output=True,
                    text=True,
                )

            subprocess.run(
                ["git", "reset", "--hard", base_commit],
                cwd=repo_path,
                check=True,
                capture_output=True,
                text=True,
            )

            subprocess.run(
                ["git", "clean", "-fd"],
                cwd=repo_path,
                check=True,
                capture_output=True,
                text=True,
            )

            return {"ok": True}

        except subprocess.CalledProcessError as e:
            stderr = e.stderr or ""
            stdout = e.stdout or ""

            sig = "git_cmd_failed"
            cmd = " ".join(e.cmd) if isinstance(e.cmd, (list, tuple)) else str(e.cmd)

            if "reset" in cmd:
                sig = "git_reset_failed"
            elif "clone" in cmd:
                sig = "git_clone_failed"

            return {
                "ok": False,
                "signature": sig,
                "returncode": e.returncode,
                "stdout": stdout,
                "stderr": stderr or str(e),
            }

        except Exception as e:
            return {
                "ok": False,
                "signature": "repo_setup_exception",
                "returncode": -1,
                "stdout": "",
                "stderr": str(e),
                
            }