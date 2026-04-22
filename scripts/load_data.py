import os
import json
from dotenv import load_dotenv
from langsmith import Client

# Load biến môi trường (chứa LANGCHAIN_API_KEY)
load_dotenv()

# Khởi tạo LangSmith Client
client = Client()

DATASET_NAME = "TechCorp_IT_Onboarding_GT"
DATASET_PATH = "data/ground_truth.json" # Đảm bảo đường dẫn này trỏ đúng tới file json của bạn

def upload_to_langsmith():
    print(f"Đang đọc dữ liệu từ {DATASET_PATH}...")
    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        dataset_data = json.load(f)

    # 1. Tạo Dataset mới trên LangSmith
    # Nếu đã tồn tại, chúng ta sẽ bắt lỗi và thông báo
    try:
        dataset = client.create_dataset(
            dataset_name=DATASET_NAME,
            description="Bộ dữ liệu kiểm thử (Ground Truth) cho TechCorp RAG"
        )
        print(f"✅ Đã tạo dataset: {DATASET_NAME}")
    except Exception as e:
        if "already exists" in str(e).lower():
            print(f"⚠️ Dataset '{DATASET_NAME}' đã tồn tại, sẽ upload thêm data vào đây.")
            dataset = client.read_dataset(dataset_name=DATASET_NAME)
        else:
            raise e

    # 2. Đẩy từng câu hỏi (inputs) và đáp án (outputs) lên
    print("Đang đẩy các Test Case lên LangSmith...")
    for item in dataset_data:
        client.create_example(
            inputs={"question": item["question"]},
            outputs={"ground_truth": item["ground_truth"]},
            dataset_id=dataset.id,
        )
    
    print("🎉 Tải lên hoàn tất! Giờ bạn có thể chạy file evaluator.py được rồi.")

if __name__ == "__main__":
    upload_to_langsmith()