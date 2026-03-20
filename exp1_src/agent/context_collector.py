"""
Exp1.B-v2-Step2-1 : 최소 컨텍스트 수집기(Min-Context Collector)

sLM이 수정할 수 있는 파일 후보 집합을 정의함.
- context 제공이 아니라, sLM의 행동 공간을 제한해서 PATCH_FAIL을 줄이는 핵심 모듈

역할 :
- repo 전체 대신 '존재하는 파일 경로 목록'을 sLM에 제공해서 hallucinated path → PATCH_FAIL을 줄이는 역할
- action space 축소 : max_files로 강제함(config의 yaml파일로)
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
