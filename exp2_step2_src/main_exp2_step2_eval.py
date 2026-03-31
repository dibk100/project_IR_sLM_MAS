from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Dict

import yaml

from exp2_step2_src.pipeline.repaired_prediction_writer import (
    write_repair_predictions_from_results,
)

logger = logging.getLogger(__name__)


def setup_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def load_config(config_path: Path | str) -> Dict[str, Any]:
    config_path = Path(config_path)
    with config_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def build_run_output_dir(project_root: Path, config: Dict[str, Any]) -> Path:
    experiment_cfg = config.get("experiment", {})
    run_id = experiment_cfg.get("run_id", "exp2_step2_debug")
    return project_root / "runs" / run_id


def build_eval_summary(
    repair_results_path: Path,
    output_predictions_path: Path,
    num_predictions: int,
) -> Dict[str, Any]:
    return {
        "repair_results_path": str(repair_results_path),
        "repair_predictions_path": str(output_predictions_path),
        "num_repair_predictions": num_predictions,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Experiment 2 Step2 evaluation prep")
    parser.add_argument(
        "--config",
        default="configs/exp2/exp2_step2_base.yaml",
        help="Path to config file",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    config = load_config(args.config)

    experiment_cfg = config.get("experiment", {})
    run_id = experiment_cfg.get("run_id", "exp2_step2_debug")

    run_dir = build_run_output_dir(project_root, config)
    setup_logging(run_dir / "eval_prep.log")

    logger.info("[main_exp2_step2_eval] project_root=%s", project_root)
    logger.info("[main_exp2_step2_eval] config_path=%s", args.config)
    logger.info("[main_exp2_step2_eval] run_id=%s", run_id)
    logger.info("[main_exp2_step2_eval] run_dir=%s", run_dir)

    repair_results_path = run_dir / "semantic_repair_results.jsonl"
    if not repair_results_path.exists():
        raise FileNotFoundError(
            f"semantic_repair_results.jsonl not found: {repair_results_path}"
        )

    output_predictions_path = run_dir / "repair_predictions.jsonl"

    prediction_rows = write_repair_predictions_from_results(
        repair_results_path=repair_results_path,
        output_predictions_path=output_predictions_path,
    )

    logger.info(
        "[main_exp2_step2_eval] wrote repair predictions to %s (count=%d)",
        output_predictions_path,
        len(prediction_rows),
    )

    summary = build_eval_summary(
        repair_results_path=repair_results_path,
        output_predictions_path=output_predictions_path,
        num_predictions=len(prediction_rows),
    )

    summary_path = run_dir / "repair_eval_prep_summary.json"
    save_json(summary_path, summary)

    logger.info("[main_exp2_step2_eval] wrote eval prep summary to %s", summary_path)
    logger.info("[main_exp2_step2_eval] done")


if __name__ == "__main__":
    main()