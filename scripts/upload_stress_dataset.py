"""
upload_stress_dataset.py — Chạy 1 lần để upload stress_data.jsonl lên LangSmith.

Usage:
    python scripts/upload_stress_dataset.py
    python scripts/upload_stress_dataset.py --file path/to/stress_data.jsonl
"""

import json
import argparse
from pathlib import Path
from dotenv import load_dotenv
from langsmith import Client

load_dotenv()

DATASET_NAME = "TechCorp_Stress_Test_v1"
BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_FILE = BASE_DIR / "data" / "stress_data.jsonl"


def main(file_path: str):
    client = Client()

    # Kiểm tra dataset đã tồn tại chưa
    existing = [d for d in client.list_datasets() if d.name == DATASET_NAME]
    if existing:
        print(f"⚠️  Dataset '{DATASET_NAME}' đã tồn tại. Dừng để tránh duplicate.")
        print(f"    Nếu muốn re-upload, xoá dataset cũ trên LangSmith UI trước.")
        return

    # Đọc JSONL
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Không tìm thấy file: {file_path}")

    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))

    print(f"📂 Đọc {len(rows)} examples từ {file_path}")

    # Tạo dataset
    dataset = client.create_dataset(
        DATASET_NAME,
        description="KnowBot stress test — OOD, Adversarial, Counterfactual, Ambiguity, Complex",
    )

    # Upload examples
    client.create_examples(
        inputs   = [{"question": r["question"]}                   for r in rows],
        outputs  = [{"ground_truth": r.get("ground_truth", "")}   for r in rows],
        metadata = [{"stress_id": r["id"], "category": r["category"]} for r in rows],
        dataset_id = dataset.id,
    )

    print(f"✅ Uploaded {len(rows)} examples → dataset '{DATASET_NAME}'")
    print(f"   URL: https://smith.langchain.com/datasets/{dataset.id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default=str(DEFAULT_FILE))
    args = parser.parse_args()
    main(args.file)