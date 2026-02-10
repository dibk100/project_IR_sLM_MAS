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
