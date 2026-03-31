from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Dict

import yaml

from exp2_step2_src.utils.utils import run_jsonl_in_chunks,setup_logging

logger = logging.getLogger(__name__)


def load_config(config_path: Path | str) -> Dict[str, Any]:
    config_path = Path(config_path)
    with config_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Step2 repaired predictions through harness")
    parser.add_argument("--config", required=True, help="Path to config file")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    config = load_config(args.config)

    experiment_cfg = config.get("experiment", {})
    agent_cfg = config.get("agent", {})
    eval_cfg = config.get("eval_harness", {})

    run_id = experiment_cfg["run_id"]
    model_name = agent_cfg["model"]
    chunk_size = int(eval_cfg.get("chunk_size", 100))

    run_dir = project_root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    log_path = run_dir / "eval_harness.log"
    setup_logging(__name__, log_file=log_path)

    repair_predictions_path = run_dir / "repair_predictions.jsonl"

    logger.info("[main_exp2_step2_eval_harness] project_root=%s", project_root)
    logger.info("[main_exp2_step2_eval_harness] config_path=%s", args.config)
    logger.info("[main_exp2_step2_eval_harness] run_id=%s", run_id)
    logger.info("[main_exp2_step2_eval_harness] run_dir=%s", run_dir)
    logger.info("[main_exp2_step2_eval_harness] repair_predictions_path=%s", repair_predictions_path)
    logger.info("[main_exp2_step2_eval_harness] chunk_size=%s", chunk_size)

    if not repair_predictions_path.exists():
        raise FileNotFoundError(f"repair_predictions.jsonl not found: {repair_predictions_path}")

    run_jsonl_in_chunks(
        run_dir=run_dir,
        run_id=f"{run_id}_repair_eval",
        model_name=model_name,
        input_jsonl=repair_predictions_path,
        chunk_size=chunk_size,
        chunk_prefix="repair_predictions",
    )

    summary = {
        "run_id": run_id,
        "repair_predictions_path": str(repair_predictions_path),
        "chunk_size": chunk_size,
        "eval_run_prefix": f"{run_id}_repair_eval",
    }
    save_json(run_dir / "repair_eval_harness_prep_summary.json", summary)

    logger.info("[main_exp2_step2_eval_harness] done")


if __name__ == "__main__":
    main()