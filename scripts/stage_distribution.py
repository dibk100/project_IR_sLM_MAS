"""
Exp1.Failure Measurement Framework(B-v2)
Step 1 : Failure → Policy State로 압축

Goal : 
stage 분포(카운트/비율) + Error_type 분포 추출하는 스크립트(확인용)
-> scripts 버전은 유지 (논문/재현용)

Usage(ex) : 
python3 scripts/stage_distribution.py --latest
python3 scripts/stage_distribution.py --run_dir runs/exp1_20260212_124011
python3 scripts/stage_distribution.py \
  --results runs/exp1_20260212_124011/results.csv \
  --out_csv runs/exp1_20260212_124011/stage_dist.csv
  
python3 scripts/stage_distribution.py \
  --results runs_archive/exp1_B-v2-step1_no_context_200tasks/results.csv \
  --out_csv runs_archive/exp1_B-v2-step1_no_context_200tasks/failure_landscape

"""
#!/usr/bin/env python3
import argparse
import csv
import os
from pathlib import Path
from collections import Counter, defaultdict
from statistics import mean, median

_ET_TO_STAGE = {
    "PASS": "DONE",
    "GEN_FAIL": "GEN",
    "REPO_FAIL": "REPO",
    "PATCH_FAIL": "PATCH",
    "TIMEOUT": "EXEC",
    "EXEC_FAIL": "EXEC",
    "TEST_FAIL": "TEST",
    "OTHER_RUNTIME": "EXEC",   # B-v2: OTHER_RUNTIME는 EXEC로 흡수
}

def _fallback_stage(stage: str, error_type: str) -> str:
    return stage if stage and stage != "UNKNOWN" else _ET_TO_STAGE.get(error_type, "UNKNOWN")

def _as_bool(x: str) -> bool:
    if x is None:
        return False
    return str(x).strip().lower() in {"1", "true", "t", "yes", "y"}

def _as_float(x):
    try:
        if x is None:
            return None
        s = str(x).strip()
        if s == "":
            return None
        return float(s)
    except Exception:
        return None

def _find_latest_run(runs_dir: Path) -> Path:
    if not runs_dir.exists():
        raise FileNotFoundError(f"runs_dir not found: {runs_dir}")
    candidates = [p for p in runs_dir.iterdir() if p.is_dir()]
    if not candidates:
        raise FileNotFoundError(f"No run directories under: {runs_dir}")
    # exp1_xxx_YYYYMMDD_HHMMSS 형태 가정: 폴더명으로 정렬해도 보통 OK
    # 더 안전하게는 mtime 정렬
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]

def _load_rows(results_csv: Path):
    if not results_csv.exists():
        raise FileNotFoundError(f"results.csv not found: {results_csv}")
    with open(results_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows:
        raise ValueError(f"No rows in: {results_csv}")
    return rows

def _pct(n, d):
    return 0.0 if d == 0 else (100.0 * n / d)

def _print_stage_table(stage_counts: Counter, total: int):
    print("\n=== Stage distribution ===")
    print(f"Total rows: {total}")
    print(f"{'stage':<10} {'count':>8} {'percent':>9}")
    for stage, cnt in stage_counts.most_common():
        print(f"{stage:<10} {cnt:>8} {_pct(cnt,total):>8.2f}%")

def _print_success(rows):
    total = len(rows)
    succ = sum(1 for r in rows if _as_bool(r.get("success")))
    print("\n=== Success rate ===")
    print(f"success: {succ}/{total} ({_pct(succ,total):.2f}%)")

def _print_stage_error_crosstab(stage_error_counts, stage_counts):
    print("\n=== Stage x ErrorType (counts) ===")
    # stage별로 상위 error_type 몇 개만 출력(너무 길어지는 것 방지)
    for stage, _ in stage_counts.most_common():
        sub = stage_error_counts.get(stage, Counter())
        if not sub:
            continue
        print(f"\n[{stage}] (top 10)")
        for et, cnt in sub.most_common(10):
            print(f"  {et:<20} {cnt}")

def _print_time_stats(rows):
    # 있으면만
    gen_list = [_as_float(r.get("gen_elapsed_sec")) for r in rows]
    exe_list = [_as_float(r.get("elapsed_sec")) for r in rows]
    gen_list = [x for x in gen_list if x is not None]
    exe_list = [x for x in exe_list if x is not None]

    if not gen_list and not exe_list:
        return

    print("\n=== Time stats (sec) ===")
    if gen_list:
        print(f"gen_elapsed_sec: mean={mean(gen_list):.4f}, median={median(gen_list):.4f}, n={len(gen_list)}")
    if exe_list:
        print(f"elapsed_sec:     mean={mean(exe_list):.4f}, median={median(exe_list):.4f}, n={len(exe_list)}")

def _write_stage_csv(out_csv: Path, stage_counts: Counter, total: int):
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["stage", "count", "percent"])
        for stage, cnt in stage_counts.most_common():
            w.writerow([stage, cnt, f"{_pct(cnt,total):.4f}"])
    print(f"\n[Saved] stage distribution -> {out_csv}")

def main():
    ap = argparse.ArgumentParser(description="Compute stage distribution from runs/*/results.csv")
    ap.add_argument("--runs_dir", default="runs", help="Base runs directory (default: runs)")
    ap.add_argument("--latest", action="store_true", help="Use latest run dir under runs_dir")
    ap.add_argument("--run_dir", default=None, help="Specific run dir (e.g., runs/exp1_20260212_124011)")
    ap.add_argument("--results", default=None, help="Path to results.csv (overrides run_dir/latest)")
    ap.add_argument("--out_csv", default=None, help="If set, save stage distribution csv to this path")
    args = ap.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    runs_dir = (project_root / args.runs_dir).resolve()

    # pick results.csv
    if args.results:
        results_csv = Path(args.results).expanduser().resolve()
    else:
        if args.run_dir:
            run_dir = Path(args.run_dir).expanduser()
            run_dir = run_dir if run_dir.is_absolute() else (project_root / run_dir)
            run_dir = run_dir.resolve()
        else:
            if not args.latest:
                raise SystemExit("Need one of: --results OR --run_dir OR --latest")
            run_dir = _find_latest_run(runs_dir)

        results_csv = run_dir / "results.csv"

    rows = _load_rows(results_csv)

    # Counters
    total = len(rows)
    stage_counts = Counter()
    stage_error_counts = defaultdict(Counter)

    for r in rows:
        et = (r.get("error_type") or "UNKNOWN").strip() or "UNKNOWN"
        stage = (r.get("stage") or "UNKNOWN").strip() or "UNKNOWN"
        stage = _fallback_stage(stage, et)
        stage_counts[stage] += 1
        stage_error_counts[stage][et] += 1

    print(f"[Input] {results_csv}")
    _print_success(rows)
    _print_stage_table(stage_counts, total)
    _print_stage_error_crosstab(stage_error_counts, stage_counts)
    _print_time_stats(rows)

    if args.out_csv:
        base = Path(args.out_csv).with_suffix("")
        _write_stage_csv(base.with_name(base.name + "_stage.csv"), stage_counts, total)
        _write_stage_error_csv(base.with_name(base.name + "_stage_error.csv"),
                            stage_error_counts, stage_counts)

def _write_stage_error_csv(out_csv: Path, stage_error_counts, stage_counts):
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["stage", "error_type", "count"])
        for stage, _ in stage_counts.most_common():
            sub = stage_error_counts.get(stage, {})
            for et, cnt in sub.items():
                w.writerow([stage, et, cnt])
    print(f"[Saved] stage x error_type -> {out_csv}")

if __name__ == "__main__":
    main()
