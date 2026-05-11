# Multi-Format Parsing: Excel, CSV & PDF Table OCR

## Tổng quan
Nâng cấp `LightweightDocumentParser` để hỗ trợ đa dạng định dạng bảng biểu và cải thiện trải nghiệm người dùng cuối qua giao diện Preview:
1. **Excel (.xlsx / .xls)** & **CSV** — Hỗ trợ đầy đủ các định dạng bảng phổ biến.
2. **PDF Table OCR** — Áp dụng `pdfplumber` như một lớp thứ hai cho các bảng phức tạp.
3. **Interactive UI Preview** — Tự động render CSV/Excel thành bảng DataFrame thay vì text thô.

---

## Quyết định Kiến trúc

### 1. Excel & CSV Parsing

**Chiến lược cho Excel (openpyxl):**
- Mỗi sheet → một section `## <TênSheet>` trong Markdown.
- `data_only=True` để lấy giá trị đã tính từ công thức.
- Tự động chuyển đổi thành Markdown Table chuẩn để AI dễ dàng trích xuất.

**Chiến lược cho CSV (csv module):**
- Sử dụng thư viện `csv` (built-in) để tối ưu hiệu suất.
- **Auto-detect:** Sử dụng `csv.Sniffer` để tự nhận diện dấu phân cách (phẩy, chấm phẩy, tab).
- **Thống nhất định dạng:** Khuyến nghị dùng CSV chuẩn (`aa,bb,cc`) thay vì dùng khoảng trắng để căn lề trong file.

### 2. PDF Table OCR (pdfplumber fallback)

**Kiến trúc 2-Pass:**
- Pass 1: `pymupdf4llm` bóc tách text và layout nhanh.
- Pass 2: `pdfplumber` quét lại các trang có mật độ bảng cao (Table Density ≥ 15%).
- Kết quả từ Pass 2 được **append** vào cuối tài liệu để bổ sung thông tin trích xuất bảng bị thiếu.

### 3. Cải tiến UI Preview (Streamlit + Pandas)

- **Vấn đề:** CSV thô nhìn qua `st.text` rất khó đọc cho người dùng.
- **Giải pháp:** Khi người dùng nhấn "Xem nguồn", UI sẽ kiểm tra đuôi file.
  - Nếu là `.csv`, `.xlsx`, `.xls`: Sử dụng `pandas` để render thành `st.dataframe` (Grid view).
  - Hỗ trợ sắp xếp, lọc và tìm kiếm trực tiếp trên bảng Preview.

---

## Thư Viện Cần Cài

```bash
pip install openpyxl pdfplumber pandas
```

Cập nhật trong `requirements.txt`:
```
openpyxl
pdfplumber
pandas
```

---

## Các File Đã Thay Đổi

| File | Thay đổi |
| --- | --- |
| `src/pipelines/parser.py` | Thêm `_parse_excel()`, `_parse_csv()`, `_enrich_pdf_tables()`. |
| `src/api/streamlit_app.py` | Nâng cấp `preview_source_dialog` hỗ trợ DataFrame view cho CSV/Excel. |
| `src/pipelines/ingestion.py` | Cập nhật định tuyến file để hỗ trợ thêm CSV và Excel. |
| `requirements.txt` | Thêm `openpyxl`, `pdfplumber`, `pandas`. |
| `GEMINI.md` | Cập nhật Mandates cho hệ thống Ingestion 5+ format. |

---

## Lưu Ý Kỹ Thuật & Thống Nhất

1. **Định dạng CSV:** Tuyệt đối không dùng khoảng trắng để căn lề trong file CSV. Hãy dùng dấu phẩy chuẩn. Nếu muốn viết bảng đẹp mắt trong Editor, hãy dùng định dạng `.md`.
2. **Merged cells:** Trong Excel, ô gộp sẽ được hiểu là giá trị nằm ở ô đầu tiên, các ô còn lại để rỗng.
3. **Thứ tự Ingestion:** Khi thêm file mới vào MinIO, hệ thống sẽ tự động nhận diện dựa trên đuôi file và kích hoạt Parser tương ứng.
4. **Re-ingestion:** Cần chạy lại `python -m src.pipelines.ingestion` để cập nhật các tài liệu bảng biểu cũ vào Vector DB theo logic trích xuất mới.
