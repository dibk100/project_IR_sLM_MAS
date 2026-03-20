"""
기존 Executor.execute_edits()가 너무 많은 작업을 다룸
-> DiffMaterializer 역할로 축소(수정 완료)
-> harness(install, test)

Executor has been reduced to a diff materializer for Exp1.

Old responsibility:
- repo setup
- edit parse
- edit apply
- diff export
- install
- test

New responsibility:
- repo setup
- edit parse
- edit apply
- diff export
- cleanup

Install/test must be handled only by the SWE-bench harness (Docker).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict


class DiffMaterializer:
    def __init__(self, timeout_seconds: int = 300, work_dir: Path = Path("workspace")):
        self.timeout = int(timeout_seconds)
        self.work_dir = Path(work_dir)
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
            "success": success,
            "stage": stage,
            "error_type": error_type,
            "signature": signature,
            "stdout": stdout,
            "stderr": stderr,
            "returncode": returncode,
            "timeout": timeout,
            "elapsed_sec": time.time() - start_time,
            "test_command": test_command,   # kept for backward compatibility
            "generated_diff": generated_diff,
            "exception": exception,
        }

    def execute_edits(self, task: Dict[str, Any], edit_script: str) -> Dict[str, Any]:
        """
        Backward-compatible entrypoint.
        Now only:
            1) setup repo
            2) parse edit script
            3) apply edits
            4) export git diff
            5) cleanup
        """
        return self.materialize_diff(task, edit_script)

    def materialize_diff(self, task: Dict[str, Any], edit_script: str) -> Dict[str, Any]:
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
                    error_type="EDIT_PARSE_FAIL",
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
                        )

                    file_path = repo_path / path
                    if not file_path.exists():
                        raise FileNotFoundError(path)

                    content = file_path.read_text(encoding="utf-8").splitlines(keepends=True)

                    if op == "replace_range":
                        start = int(edit["start_line"]) - 1
                        end = int(edit["end_line"])
                        if start < 0 or end > len(content) or start > end:
                            raise IndexError("range_oob")

                        new_lines = str(edit["text"]).splitlines(keepends=True)
                        content[start:end] = new_lines

                    elif op == "insert_after":
                        line = int(edit["line"])
                        if line < 1 or line > len(content):
                            raise IndexError("insert_oob")

                        new_lines = str(edit["text"]).splitlines(keepends=True)
                        content[line:line] = new_lines

                    else:
                        raise ValueError("unknown_op")

                    file_path.write_text("".join(content), encoding="utf-8")
                    applied = True

            except FileNotFoundError as e:
                return self._result(
                    success=False,
                    stage="EDIT_APPLY",
                    error_type="APPLY_FAIL",
                    signature="edit_apply_path_missing",
                    start_time=start_time,
                    stderr=str(e),
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
                    exception=repr(e),
                )

            except ValueError as e:
                sig = "edit_apply_unknown_op" if str(e) == "unknown_op" else "edit_apply_value_error"
                return self._result(
                    success=False,
                    stage="EDIT_APPLY",
                    error_type="APPLY_FAIL",
                    signature=sig,
                    start_time=start_time,
                    stderr=str(e),
                    exception=repr(e),
                )

            except Exception as e:
                return self._result(
                    success=False,
                    stage="EDIT_APPLY",
                    error_type="APPLY_FAIL",
                    signature="edit_apply_exception",
                    start_time=start_time,
                    stderr=str(e),
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
                timeout=self.timeout,
            )
            generated_diff = diff_proc.stdout or ""

            if diff_proc.returncode != 0:
                return self._result(
                    success=False,
                    stage="DIFF_EXPORT",
                    error_type="PATCH_FAIL",
                    signature="git_diff_failed",
                    start_time=start_time,
                    stdout=diff_proc.stdout,
                    stderr=diff_proc.stderr,
                    returncode=diff_proc.returncode,
                    generated_diff=generated_diff,
                )

            if not generated_diff.strip():
                return self._result(
                    success=False,
                    stage="DIFF_EXPORT",
                    error_type="PATCH_FAIL",
                    signature="empty_generated_diff",
                    start_time=start_time,
                    stdout=diff_proc.stdout,
                    stderr=diff_proc.stderr,
                    returncode=diff_proc.returncode,
                    generated_diff="",
                )

            # Success here means: ready to hand off to harness
            return self._result(
                success=True,
                stage="DIFF_EXPORT",
                error_type="PRED_READY",
                signature="ready_for_harness",
                start_time=start_time,
                stdout=diff_proc.stdout,
                stderr=diff_proc.stderr,
                returncode=diff_proc.returncode,
                generated_diff=generated_diff,
            )

        except subprocess.TimeoutExpired as e:
            return self._result(
                success=False,
                stage="DIFF_EXPORT",
                error_type="TIMEOUT",
                signature="git_diff_timeout",
                start_time=start_time,
                stdout=e.stdout or "",
                stderr=e.stderr or "",
                returncode=-1,
                timeout=True,
                exception=repr(e),
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
            # 5. Cleanup repo
            # -------------------------------
            if applied and repo_path.exists():
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

    def _setup_repo(self, task: Dict[str, Any], repo_path: Path) -> Dict[str, Any]:
        repo = task.get("repo")
        if not repo:
            return {
                "ok": False,
                "signature": "repo_missing",
                "returncode": -1,
                "stdout": "",
                "stderr": "task['repo'] is missing",
            }

        repo_url = f"https://github.com/{repo}.git"
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
                    timeout=self.timeout,
                )

            # Ensure remote objects are available for reset
            subprocess.run(
                ["git", "fetch", "--all"],
                cwd=repo_path,
                check=True,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )

            subprocess.run(
                ["git", "reset", "--hard", str(base_commit)],
                cwd=repo_path,
                check=True,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )

            subprocess.run(
                ["git", "clean", "-fd"],
                cwd=repo_path,
                check=True,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )

            return {"ok": True}

        except subprocess.TimeoutExpired as e:
            return {
                "ok": False,
                "signature": "repo_setup_timeout",
                "returncode": -1,
                "stdout": e.stdout or "",
                "stderr": e.stderr or "",
            }

        except subprocess.CalledProcessError as e:
            stderr = e.stderr or ""
            stdout = e.stdout or ""
            cmd = " ".join(e.cmd) if isinstance(e.cmd, (list, tuple)) else str(e.cmd)

            sig = "git_cmd_failed"
            if "clone" in cmd:
                sig = "git_clone_failed"
            elif "fetch" in cmd:
                sig = "git_fetch_failed"
            elif "reset" in cmd:
                sig = "git_reset_failed"

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