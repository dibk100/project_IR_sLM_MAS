import json
import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


def setup_logging(name: str, log_file: Path | None = None, level: int = logging.INFO):
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.handlers:
        return logger

    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    if log_file:
        fh = logging.FileHandler(log_file)
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    return logger


def count_diff_lines(diff_content: str) -> tuple[int, int, int]:
    added = 0
    removed = 0
    files_changed = 0

    for line in diff_content.splitlines():
        if line.startswith("diff --git "):
            files_changed += 1
        elif line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1

    return added, removed, files_changed


def is_docker_available() -> bool:
    if not shutil.which("docker"):
        return False

    try:
        subprocess.run(["docker", "info"], check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError:
        return False

def write_predictions_jsonl(path: Path, predictions: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in predictions:
            f.write(json.dumps(dict(row), ensure_ascii=False) + "\n")


def run_swebench_harness(
    run_dir: Path,
    run_id: str,
    model_name: str,
    max_workers: int = 1,
    dataset_name: str = "princeton-nlp/SWE-bench_Lite",
    predictions_path: Path | None = None,
) -> None:
    run_dir = Path(run_dir)

    if predictions_path is None:
        pred_path = run_dir / "predictions.jsonl"
    else:
        pred_path = Path(predictions_path)

    if not pred_path.exists():
        raise FileNotFoundError(f"predictions.jsonl not found: {pred_path}")

    cmd = [
        sys.executable,
        "-m",
        "swebench.harness.run_evaluation",
        "--dataset_name",
        dataset_name,
        "--predictions_path",
        str(pred_path),
        "--max_workers",
        str(max_workers),
        "--run_id",
        run_id,
        "--namespace",
        "none",
    ]

    log_path = run_dir / f"{run_id}_harness_output.log"
    with log_path.open("w", encoding="utf-8") as log_file:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=run_dir,            # if mistral : "/home/dibaeck/workspace/project_IR_sLM_MAS/SWE-bench"
        )
        assert proc.stdout is not None

        try:
            for line in proc.stdout:
                print(line, end="", flush=True)
                log_file.write(line)
                log_file.flush()
        finally:
            proc.stdout.close()

        rc = proc.wait()
        subprocess.run(["docker", "container", "prune", "-f"])
        subprocess.run(["docker", "system", "prune", "-a", "-f"])
        summary = f"\n[run_swebench_harness] exit_code={rc} log_path={log_path}\n"
        print(summary, end="", flush=True)
        log_file.write(summary)
        log_file.flush()

        if rc != 0:
            raise subprocess.CalledProcessError(
                rc,
                cmd,
                output=f"See log: {log_path}"
            )

    print(f"Harness output saved to: {log_path}")


def split_jsonl(input_path: Path, chunk_size: int = 100):
    with input_path.open() as f:
        lines = f.readlines()

    chunks = []
    for i in range(0, len(lines), chunk_size):
        chunk = lines[i:i + chunk_size]
        chunks.append(chunk)

    return chunks

def run_in_chunks(run_dir, run_id, model_name, chunk_size=100):
    run_dir = Path(run_dir)
    pred_path = run_dir / "predictions.jsonl"

    chunks = split_jsonl(pred_path, chunk_size)

    for idx, chunk in enumerate(chunks):
        chunk_path = run_dir / f"predictions_chunk_{idx}.jsonl"
        log_path = run_dir / f"{run_id}_part{idx}_harness_output.log"

        # ✅ 진짜 skip (완료 기준)
        if log_path.exists():
            print(f"⏭️ Skipping chunk {idx} (already completed)")
            continue

        # chunk 저장
        with chunk_path.open("w") as f:
            f.writelines(chunk)

        print(f"\n🚀 Running chunk {idx} ({len(chunk)} tasks)\n")

        run_swebench_harness(
            run_dir=run_dir,
            run_id=f"{run_id}_part{idx}",
            model_name=model_name,
            predictions_path=chunk_path,
        )

        subprocess.run(["docker", "system", "prune", "-a", "-f"])

def run_jsonl_in_chunks(
    run_dir,
    run_id,
    model_name,
    input_jsonl: Path,
    chunk_size: int = 100,
    chunk_prefix: str = "predictions",
):
    run_dir = Path(run_dir)
    input_jsonl = Path(input_jsonl)

    chunks = split_jsonl(input_jsonl, chunk_size)

    for idx, chunk in enumerate(chunks):
        chunk_path = run_dir / f"{chunk_prefix}_chunk_{idx}.jsonl"
        log_path = run_dir / f"{run_id}_part{idx}_harness_output.log"

        if log_path.exists():
            print(f"⏭️ Skipping chunk {idx} (already completed)")
            continue

        with chunk_path.open("w", encoding="utf-8") as f:
            f.writelines(chunk)

        print(f"\n🚀 Running chunk {idx} ({len(chunk)} tasks)\n")

        run_swebench_harness(
            run_dir=run_dir,
            run_id=f"{run_id}_part{idx}",
            model_name=model_name,
            predictions_path=chunk_path,
        )

        subprocess.run(["docker", "system", "prune", "-a", "-f"])


