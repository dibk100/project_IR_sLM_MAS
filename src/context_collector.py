"""
Exp1.B-v2-Step2-1 : 최소 컨텍스트 수집기(Min-Context Collector)

A안 — “파일 경로 힌트 + git apply 친화 프롬프트” (가장 가벼움)
- 이미 workspace에 클론돼있으면 그걸 활용하는 방식

구현: ContextCollector 모듈 추가 (새 파일 1개) + GenerateAgent 수정(1곳) + main_exp1.py 수정(1곳)

역할: repo_path에서 .py 파일 상위 일부를 뽑아서 “존재하는 파일 후보 리스트”를 생성
"""
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
    def __init__(self, max_files: int = 80):
        self.max_files = int(max_files)

    def collect(self, repo_path: Path) -> RepoContext:
        if not repo_path.exists():
            return RepoContext(repo_path=repo_path, file_candidates=[])

        # Prefer python files (SWE-bench tasks are mostly python repos, but not always)
        py_files = [p for p in repo_path.rglob("*.py") if p.is_file()]
        # Keep it stable-ish: sort by path length then lexicographic
        py_files.sort(key=lambda p: (len(str(p)), str(p)))

        rels: List[str] = []
        for p in py_files[: self.max_files]:
            try:
                rels.append(str(p.relative_to(repo_path)))
            except Exception:
                rels.append(str(p))

        return RepoContext(repo_path=repo_path, file_candidates=rels)
