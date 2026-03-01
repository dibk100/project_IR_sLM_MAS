import logging
import sys
from pathlib import Path
from typing import Tuple, List

import json
import subprocess

def setup_logging(name: str, log_file: Path = None, level=logging.INFO):
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Prevent duplicate handlers if setup_logging() is called multiple times
    if logger.handlers:
        return logger
    
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
        if line.startswith("diff --git "):
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

def validate_edit_script(edit_script: str, max_files: int = 2, max_edits: int = 6) -> Tuple[bool, str, List[str]]:
    """
    Step2-4 minimal JSON edit-script guardrail.
    Returns: (ok, reason, files)

    Schema (v0):
    {
      "edits": [
        {"op":"replace_range","path":str,"start_line":int,"end_line":int,"text":str},
        {"op":"insert_after","path":str,"line":int,"text":str}
      ]
    }
    """
    if not edit_script or not edit_script.strip():
        return False, "empty_edit_script", []

    try:
        data = json.loads(edit_script)
    except Exception:
        return False, "invalid_json", []

    if not isinstance(data, dict):
        return False, "root_not_object", []

    edits = data.get("edits")
    if not isinstance(edits, list) or not edits:
        return False, "missing_or_empty_edits", []

    if len(edits) > max_edits:
        return False, f"too_many_edits({len(edits)})", []

    files: List[str] = []
    file_set = set()

    for e in edits:
        if not isinstance(e, dict):
            return False, "edit_not_object", []

        op = e.get("op")
        path = e.get("path")
        text = e.get("text")
        if op not in ("replace_range", "insert_after"):
            return False, "unknown_op", []
        if not isinstance(path, str) or not path.strip():
            return False, "bad_path", []
        if not isinstance(text, str):
            return False, "bad_text", []

        # op-specific fields
        if op == "replace_range":
            if not isinstance(e.get("start_line"), int) or not isinstance(e.get("end_line"), int):
                return False, "bad_range_type", []
            if e["start_line"] < 1 or e["end_line"] < e["start_line"]:
                return False, "bad_range_value", []
        else:  # insert_after
            if not isinstance(e.get("line"), int):
                return False, "bad_line_type", []
            if e["line"] < 0:
                return False, "bad_line_value", []

        file_set.add(path)

    if len(file_set) > max_files:
        return False, f"too_many_files({len(file_set)})", sorted(list(file_set))

    files = sorted(list(file_set))
    return True, "ok", files

def find_latest_run_dir(runs_dir: Path) -> Path:
    """
    runs_dir 아래에서 가장 최근 수정된 run 디렉토리(exp1_...)를 반환
    """
    cands = [p for p in runs_dir.iterdir() if p.is_dir()]
    if not cands:
        raise FileNotFoundError(f"No run dirs under: {runs_dir}")
    cands.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return cands[0]

def make_predictions_jsonl(run_dir: Path, model_name: str = "Qwen/Qwen2.5-Coder-7B-Instruct") -> Path:
    """
    run_dir/traces/*.patch.diff -> run_dir/predictions.jsonl
    """
    run_dir = Path(run_dir)
    traces_dir = run_dir / "traces"
    if not traces_dir.exists():
        raise FileNotFoundError(f"traces dir not found: {traces_dir}")

    out_path = run_dir / "predictions.jsonl"
    patch_files = sorted(traces_dir.glob("*_trial*.patch.diff"))

    n_written = 0
    with out_path.open("w", encoding="utf-8") as f:
        for pf in patch_files:
            task_id = pf.name.split("_trial")[0]
            patch = pf.read_text(encoding="utf-8", errors="ignore")

            obj = {
                "instance_id": task_id,
                # 하네스 호환 키(버전 차이 대비)
                "model_patch": patch,
                "patch": patch,
                "diff": patch,
                "model_name_or_path": '',
            }
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
            n_written += 1

    print("patch files:", len(patch_files))
    print("wrote:", out_path, "lines:", n_written)
    return out_path

def run_harness(run_dir: Path, run_id: str, max_workers: int = 1,
               dataset_name: str = "princeton-nlp/SWE-bench_Lite",
               predictions_path: Path | None = None) -> None:
    """
    run_dir에 predictions.jsonl이 없으면 생성하고 harness 실행
    """
    run_dir = Path(run_dir)

    if predictions_path is None:
        pred_path = run_dir / "predictions.jsonl"
        if not pred_path.exists():
            pred_path = make_predictions_jsonl(run_dir)
    else:
        pred_path = Path(predictions_path)

    cmd = [
        sys.executable, "-m", "swebench.harness.run_evaluation",
        "--dataset_name", dataset_name,
        "--predictions_path", str(pred_path),
        "--max_workers", str(max_workers),
        "--run_id", run_id,
    ]
    subprocess.run(cmd, check=True)