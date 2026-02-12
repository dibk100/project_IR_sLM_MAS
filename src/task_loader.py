import json
from pathlib import Path
from typing import Optional

class TaskLoader:
    def __init__(self, path: str, max_tasks: Optional[int] = None):
        self.path = Path(path)
        self.max_tasks = max_tasks
        
    def load_tasks(self) -> list[dict]:
        tasks = []

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

                    tasks.append(ex)

                    if self.max_tasks is not None and len(tasks) >= self.max_tasks:
                        break

                except json.JSONDecodeError:
                    print(f"Skipping invalid json line in {self.path}")

        return tasks
