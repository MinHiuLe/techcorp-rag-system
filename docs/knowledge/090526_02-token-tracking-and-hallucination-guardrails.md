# KI: Xử lý Token Tracking và Thắt chặt Guardrails chống Ảo giác [090526_02]

## Bối cảnh (Context)
Trong phiên làm việc này, chúng tôi đã triển khai tính năng **Streaming Response** để cải thiện UX. Tuy nhiên, việc streaming gây ra lỗi trong việc theo dõi (tracking) token trên LangSmith do Groq SDK không hỗ trợ `stream_options` đồng bộ và việc bóc tách `usage` từ chunk cuối cùng không ổn định đối với các manual traces (`@traceable`). 

Đồng thời, khi thực hiện "Stress Test" với dữ liệu thực tế, hệ thống gặp hiện tượng **Over-eager AI** (AI trả lời quá nhiệt tình dựa trên ngữ cảnh chung chung khi không tìm thấy thông tin cụ thể).

## Các thay đổi quan trọng (Core Changes)

### 1. Chuyển đổi sang API Đồng bộ (Synchronous API)
- **Quyết định:** Loại bỏ cơ chế Streaming để ưu tiên tính chính xác của dữ liệu đo lường (Token usage).
- **Lý do:** LangSmith yêu cầu thông tin `usage` (prompt_tokens, completion_tokens) để tính toán Cost và Latency chuẩn xác. Streaming làm gãy luồng bóc tách metadata này.
- **Giải pháp UX:** Thay thế Streaming bằng hiệu ứng **"Thinking Bubble"** (ba dấu chấm chạy) trong Streamlit để người dùng vẫn cảm nhận được hệ thống đang xử lý.
- **Mã nguồn:** `streamlit_app.py` quay về gọi `/chat` (POST) thay vì `/chat/stream`.

### 2. Thắt chặt Guardrails chống Hallucination
- **Vấn đề:** AI cố gắng áp dụng "Kịch bản Sales chung" cho câu hỏi cụ thể về "Dự án ERP ngành y tế" dù tài liệu không đề cập.
- **Giải pháp:** Cập nhật Prompt `STANDARD` và `FULL` trong `generator.py`. 
- **Chỉ thị mới:** *"Nếu CONTEXT không chứa thông tin TRỰC TIẾP và CỤ THỂ về chủ đề người dùng hỏi, BẮT BUỘC phải trả lời: 'Tôi không tìm thấy thông tin cụ thể về...'. KHÔNG được suy diễn hoặc ép buộc dùng dữ liệu không liên quan."*

### 3. Sửa lỗi Render HTML trong Source Viewer
- **Vấn đề:** Do thụt lề (indentation) trong chuỗi `f"""..."""`, Streamlit hiểu nhầm thẻ HTML là Code Block và hiển thị thô đoạn mã `<div id="retrieval-target">`.
- **Giải pháp:** Loại bỏ hoàn toàn thụt lề đầu dòng trong các chuỗi HTML literal chèn vào Markdown.

## Lưu ý kỹ thuật (Technical Notes)
- Để LangSmith nhận diện được token, metadata phải sử dụng key có tiền tố `ls_` (ví dụ: `ls_prompt_tokens`).
- Biến `CHAT_URL` trong `streamlit_app.py` hiện là endpoint chính thức, `CHAT_STREAM_URL` vẫn tồn tại nhưng không được sử dụng ở frontend.

## Git Commit
`feat: revert to sync API for reliable token tracking and strengthen hallucination guardrails`
