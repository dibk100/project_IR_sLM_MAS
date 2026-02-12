import json
from pathlib import Path

'''
patch/test_patch 제거 + 필요한 필드만 유지
'''

class TaskLoader:
    def __init__(self, path: str):
        self.path = Path(path)
        
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

                    ex.pop("patch", None)
                    ex.pop("test_patch", None)

                    tasks.append(ex)
                except json.JSONDecodeError:
                    print(f"Skipping invalid json line in {self.path}")
        return tasks
