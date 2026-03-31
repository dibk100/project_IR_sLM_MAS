from pathlib import Path

from exp2_step2_src.data.step1_result_loader import load_step1_results
from exp2_step2_src.repair.repair_trigger import analyze_repair_target


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    run_name = "exp2_qwen2p5_policy_v0_smoke_100"  # 네 실제 run 이름으로 수정

    rows = load_step1_results(project_root=project_root, run_name=run_name)

    eligible = []
    for row in rows:
        result = analyze_repair_target(row)
        if result["eligible"]:
            eligible.append((row, result))

    print(f"total rows: {len(rows)}")
    print(f"eligible rows: {len(eligible)}")

    for row, result in eligible[:5]:
        print("=" * 80)
        print("instance_id:", row["instance_id"])
        print("final_error_type:", row["final_error_type"])
        print("final_signature:", row["final_signature"])
        print("reason:", result["reason"])
        print("harness_text:", row["harness_text"][:500])


if __name__ == "__main__":
    main()