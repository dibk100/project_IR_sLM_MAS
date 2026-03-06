import json
from pathlib import Path
from typing import Optional, List, Dict, Any


class TaskLoader:
    def __init__(self, path: str, max_tasks: Optional[int] = None):
        self.path = Path(path)
        self.max_tasks = max_tasks

    def _normalize(self, ex: Dict[str, Any]) -> Dict[str, Any]:
        # --- ID ---
        if "instance_id" not in ex:
            ex["instance_id"] = ex.get("task_id") or ex.get("id") or ex.get("instance") or "unknown"

        # --- Repo ---
        if "repo" not in ex:
            ex["repo"] = ex.get("repo_name") or ex.get("repository") or ex.get("project") or "unknown_repo"

        # --- Base commit ---
        if "base_commit" not in ex:
            ex["base_commit"] = ex.get("base_sha") or ex.get("commit") or ex.get("base") or "HEAD"

        # --- Problem text ---
        if "problem_statement" not in ex:
            ex["problem_statement"] = ex.get("issue_text") or ex.get("text") or ex.get("problem") or ""

        # --- Test command (IMPORTANT) ---
        if "test_command" not in ex or not ex.get("test_command"):
            # common variants across SWE-bench exports
            ex["test_command"] = ex.get("test_cmd") or ex.get("test") or ex.get("command") or ""

        return ex

    def load_tasks(self) -> List[Dict[str, Any]]:
        tasks: List[Dict[str, Any]] = []

        if not self.path.exists():
            raise FileNotFoundError(f"Task file not found: {self.path}")

        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    ex = json.loads(line)

                    # remove ground-truth patches
                    ex.pop("patch", None)
                    ex.pop("test_patch", None)

                    ex = self._normalize(ex)

                    tasks.append(ex)

                    if self.max_tasks is not None and len(tasks) >= self.max_tasks:
                        break

                except json.JSONDecodeError:
                    print(f"Skipping invalid json line in {self.path}")

        return tasks