# Migration to Lightweight Document Parser & Streamlit Streaming UI

## Tổng quan
Quyết định chuyển đổi kiến trúc Ingestion Pipeline từ việc sử dụng các model OCR nặng (như MinerU) sang các thư viện xử lý tài liệu gọn nhẹ. Cải tiến giao diện người dùng (Streamlit) với cơ chế Streaming (trả kết quả theo thời gian thực), hiển thị nội dung Markdown chuẩn xác và hỗ trợ xem trước (Preview) file PDF trực tiếp.

## Quyết định Kiến trúc & Thay đổi Quan trọng

### 1. Ingestion Pipeline (Parser)
- **Vấn đề:** Các thư viện như `magic-pdf` (MinerU) sử dụng các mô hình Deep Learning để bóc tách bố cục (Layout Analysis) và OCR. Quá trình này tiêu tốn nhiều CPU/RAM và rất chậm trên các máy tính cấu hình giới hạn (như MSI Modern 15).
- **Giải pháp:** 
  - Tạo `LightweightDocumentParser` tại `src/pipelines/parser.py`.
  - **PDF:** Sử dụng `pymupdf4llm` để chuyển đổi cực nhanh sang định dạng Markdown chuẩn, giữ vững cấu trúc bảng.
  - **DOCX:** Sử dụng `python-docx` để duyệt qua các paragraph và tables, chuyển đổi tự động thành Header (`#`, `##`) và Markdown Table (`| --- | --- |`). Đảm bảo `smart_markdown_chunker` nhận diện đúng.
  - **PPTX:** Sử dụng `python-pptx` để trích xuất chữ từ các slide shape.

### 2. Giao diện Người Dùng (Streamlit UI)
- **Vấn đề:** Khi kết quả trả về có chứa các cấu trúc Markdown phức tạp (như danh sách số 1, 2, 3), việc chèn trực tiếp nội dung vào thẻ `<div>` bằng cơ chế của Streamlit khiến văn bản bị dồn cục (không xuống dòng). Ngoài ra, file PDF không thể được preview ở dạng văn bản thuần túy (như `.md`).
- **Giải pháp:**
  - **Streaming:** Tích hợp endpoint `/chat/stream` từ Backend vào UI. Thêm hiệu ứng con trỏ nhấp nháy (`.stream-cursor`) để cải thiện trải nghiệm UX.
  - **Pre-render Markdown:** Dùng thư viện `markdown` (Python) để render câu trả lời (bao gồm cả Tables và Code blocks) thành HTML trước khi nhúng vào khung chat bubble.
  - **PDF Preview:** Sử dụng Base64 string và thẻ `<iframe>` (`application/pdf`) để nhúng trực tiếp nội dung file PDF lên trình duyệt khi người dùng nhấp vào nút Xem nguồn.

### 3. Tối ưu hạ tầng (Docker)
- Cập nhật `docker-compose.yml` để mount thư mục `~/.cache/huggingface` vào môi trường của container `api`.
- Ngăn chặn tình trạng hệ thống bị "treo" quá lâu (hơn 10 phút) do Docker tải lại mô hình Embedding kích thước lớn khi không có xác thực (HuggingFace throttling).

## Lưu ý Kỹ thuật
- Khi chạy script Ingestion (`python -m src.pipelines.ingestion`), môi trường local venv cần cài đặt: `pip install pymupdf4llm python-docx python-pptx`.
- Đối với Docker UI (`Dockerfile.ui`), phải cài thêm thư viện `markdown` để xử lý việc render giao diện chat.
- Vì PPTX hiện chỉ trích xuất text đơn giản, nếu có tài liệu PowerPoint phức tạp, có thể cần thiết kế lại logic parse cho format này.
