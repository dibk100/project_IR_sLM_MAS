import json
from datasets import load_dataset
from pathlib import Path

def download_swebench_lite(output_path: Path, split="test"):
    print(f"Downloading SWE-bench_Lite ({split} split)...")
    dataset = load_dataset("princeton-nlp/SWE-bench_Lite", split=split)
    
    print(f"Downloaded {len(dataset)} examples. Saving to {output_path}...")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Save as JSONL
    dataset.to_json(output_path)
    print("Done!")

if __name__ == "__main__":
    output_file = Path("data/swe_bench_lite_test.jsonl")
    download_swebench_lite(output_file)


'''
import json
from datasets import load_dataset
from pathlib import Path

def download_swebench_lite(output_path: Path, split="test"):
    print(f"Downloading SWE-bench_Lite ({split} split)...")
    dataset = load_dataset("princeton-nlp/SWE-bench_Lite", split=split)

    print(f"Downloaded {len(dataset)} examples.")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Saving filtered dataset to {output_path}...")

    with output_path.open("w", encoding="utf-8") as f:
        for ex in dataset:
            record = {
                "instance_id": ex["instance_id"],
                "repo": ex["repo"],
                "base_commit": ex["base_commit"],
                "problem_statement": ex["problem_statement"],
                "hints_text": ex.get("hints_text", None),
            }
            f.write(json.dumps(record) + "\n")

    print("Done!")

if __name__ == "__main__":
    output_file = Path("data/swe_bench_lite_test.jsonl")
    download_swebench_lite(output_file)
'''