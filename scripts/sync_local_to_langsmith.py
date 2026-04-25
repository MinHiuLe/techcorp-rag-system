import os
import sys
import json
from dotenv import load_dotenv
from langsmith import Client

# --- 1. SETUP ĐƯỜNG DẪN VÀ BIẾN MÔI TRƯỜNG ---
# Định vị chính xác file .env ở thư mục gốc để tránh lỗi 401 Unauthorized
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(CURRENT_DIR) 
dotenv_path = os.path.join(BASE_DIR, '.env')

load_dotenv(dotenv_path=dotenv_path)

# Kiểm tra nhanh xem đã có API Key chưa
if not os.getenv("LANGCHAIN_API_KEY"):
    print("❌ LỖI: Không tìm thấy LANGCHAIN_API_KEY. Hãy kiểm tra lại file .env!")
    sys.exit(1)

print("[System] Khởi tạo LangSmith Client...")
client = Client()

# --- 2. HÀM ĐỒNG BỘ DỮ LIỆU ---
def sync_local_to_langsmith(json_path: str, dataset_name: str, description: str = ""):
    print(f"📦 Đang đọc dữ liệu từ: {json_path}")
    
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"❌ Không tìm thấy file dữ liệu: {json_path}")
        print("💡 Hãy tạo file này với định dạng chuẩn trước khi chạy script.")
        return
    except json.JSONDecodeError:
        print(f"❌ File {json_path} bị sai định dạng JSON. Hãy kiểm tra lại dấu phẩy, ngoặc kép.")
        return

    print(f"🔍 Tìm thấy {len(data)} examples. Đang đồng bộ lên LangSmith...")

    # --- 3. KIỂM TRA HOẶC TẠO MỚI DATASET ---
    try:
        # Thử lấy dataset hiện tại
        dataset = client.read_dataset(dataset_name=dataset_name)
        print(f"⚠️ Dataset '{dataset_name}' ĐÃ TỒN TẠI. Sẽ bơm thêm data vào dataset này.")
    except Exception:
        # Nếu chưa có thì tạo mới
        print(f"✨ Tạo mới Dataset: '{dataset_name}'")
        dataset = client.create_dataset(
            dataset_name=dataset_name, 
            description=description
        )

    # --- 4. UPLOAD TỪNG DÒNG (EXAMPLES) ---
    success_count = 0
    for i, item in enumerate(data):
        try:
            # Inputs và Outputs phải đặt tên giống y hệt lúc gọi trong evaluator.py
            client.create_example(
                inputs={"question": item["question"]},
                outputs={"ground_truth": item["ground_truth"]},
                dataset_id=dataset.id
            )
            success_count += 1
        except KeyError as ke:
            print(f"⚠️ Dòng {i+1} thiếu key {ke}. Bỏ qua.")
        except Exception as e:
            print(f"⚠️ Lỗi không xác định ở dòng {i+1}: {e}")

    print("-" * 50)
    print(f"✅ HOÀN TẤT! Đã upload thành công {success_count}/{len(data)} câu hỏi vào '{dataset_name}'.")
    print(f"🔗 Xem trực tiếp tại: https://smith.langchain.com/")


if __name__ == "__main__":
    # --- CẤU HÌNH CHẠY SCRIPT ---
    # Đặt tên Dataset mà bạn muốn tạo hoặc cập nhật
    TARGET_DATASET_NAME = "TechCorp_IT_Onboarding_GT"
    
    # Đường dẫn trỏ tới file JSON chứa danh sách câu hỏi mẫu ở máy local
    LOCAL_JSON_FILE = os.path.join(BASE_DIR, "data", "ground_truth.json")
    
    sync_local_to_langsmith(
        json_path=LOCAL_JSON_FILE, 
        dataset_name=TARGET_DATASET_NAME,
        description="Dataset chuẩn (Ground Truth) để đánh giá RAG TechCorp (Sales, HR, IT)"
    )