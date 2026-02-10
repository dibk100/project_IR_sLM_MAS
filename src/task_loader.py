import json
from pathlib import Path

class TaskLoader:
    def __init__(self, path: str):
        self.path = Path(path)
        
    def load_tasks(self) -> list[dict]:
        tasks = []
        if not self.path.exists():
            raise FileNotFoundError(f"Task file not found: {self.path}")
            
        with open(self.path, "r") as f:
            for line in f:
                if line.strip():
                    try:
                        tasks.append(json.loads(line))
                    except json.JSONDecodeError:
                        print(f"Skipping invalid json line in {self.path}")
        return tasks
