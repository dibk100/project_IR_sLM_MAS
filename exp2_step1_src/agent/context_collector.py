from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class RepoContext:
    repo_path: Path
    file_candidates: List[str]


class ContextCollector:
    """
    Minimal context collector for Step2-1:
    - Collect a small list of existing file paths to reduce PATCH_FAIL.
    - No heavy parsing / no grep / no AST. Just filesystem listing.
    """
    def __init__(self, max_files: int = 20):
        self.max_files = int(max_files)

    def collect(self, repo_path: Path) -> RepoContext:
        if not repo_path.exists():
            return RepoContext(repo_path=repo_path, file_candidates=[])

        # Prefer python files (SWE-bench tasks are mostly python repos, but not always)
        py_files = [p for p in repo_path.rglob("*.py") if p.is_file()]
        
        py_files.sort(key=lambda p: (
            "test" not in str(p).lower(),  # test files 먼저
            len(str(p)),
            str(p),
        ))

        rels: List[str] = []
        for p in py_files[: self.max_files]:
            try:
                rels.append(str(p.relative_to(repo_path)))
            except Exception:
                rels.append(str(p))

        return RepoContext(repo_path=repo_path, file_candidates=rels)
