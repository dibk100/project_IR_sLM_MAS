import logging
import sys
from pathlib import Path
from typing import Tuple, List
import re

def setup_logging(name: str, log_file: Path = None, level=logging.INFO):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    
    # File handler
    if log_file:
        fh = logging.FileHandler(log_file)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
        
    return logger

def count_diff_lines(diff_content: str) -> tuple[int, int, int]:
    """
    Returns (added, removed, files_changed)
    """
    added = 0
    removed = 0
    files_changed = 0
    
    lines = diff_content.splitlines()
    for line in lines:
        if line.startswith("+++ "):
            files_changed += 1
        elif line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
            
    return added, removed, files_changed

def check_docker():
    """Checks if docker is available and running."""
    import shutil
    import subprocess
    
    if not shutil.which("docker"):
        return False
    
    try:
        subprocess.run(["docker", "info"], check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        return False

def validate_unified_diff(diff_text: str, max_files: int = 2) -> Tuple[bool, str, List[str]]:
    """
    Minimal unified-diff guardrail (B-v2 Step2-B).
    Returns: (ok, reason, files)

    Checks (cheap & robust):
    - Not empty
    - Has at least one file header pair: '--- ' and '+++ '
    - Paths look like 'a/...' and 'b/...' (or /dev/null for add/delete)
    - Number of files <= max_files (approx by counting file header pairs)
    - Has at least one hunk header '@@' (strong heuristic)
    """
    if not diff_text or not diff_text.strip():
        return False, "empty_diff", []

    lines = diff_text.splitlines()

    # Disallow markdown fences that survived cleaning
    if any(l.strip().startswith("```") for l in lines[:5]):
        return False, "contains_markdown_fence", []

    minus_headers = [i for i, l in enumerate(lines) if l.startswith("--- ")]
    plus_headers = [i for i, l in enumerate(lines) if l.startswith("+++ ")]
    if not minus_headers or not plus_headers:
        return False, "missing_file_headers", []

    mh_set = set(minus_headers)
    ph_set = set(plus_headers)

    files: List[str] = []
    file_count = 0
    i = 0
    while i < len(lines):
        if i in mh_set:
            # expect immediate +++ on next line (basic pairing)
            if i + 1 >= len(lines) or (i + 1) not in ph_set:
                return False, "unpaired_headers", []

            a_path = lines[i][4:].strip()
            b_path = lines[i + 1][4:].strip()

            if not (a_path.startswith("a/") or a_path == "/dev/null"):
                return False, "bad_a_path_header", []
            if not (b_path.startswith("b/") or b_path == "/dev/null"):
                return False, "bad_b_path_header", []

            # Track file path (prefer b/ if present)
            if b_path.startswith("b/"):
                files.append(b_path[2:])
                file_count += 1
            elif a_path.startswith("a/"):
                files.append(a_path[2:])
                file_count += 1

            i += 2
            continue
        i += 1

    if file_count > max_files:
        return False, f"too_many_files({file_count})", files

    if not any(l.startswith("@@") for l in lines):
        return False, "missing_hunk_header", files

    return True, "ok", files
