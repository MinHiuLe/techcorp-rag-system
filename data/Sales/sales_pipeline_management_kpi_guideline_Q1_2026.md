# Sales Pipeline Management & KPI Guideline – Q1 2026

## 1. Mục đích & phạm vi

Tài liệu này dành cho toàn bộ Sales team TechCorp (bao gồm SDR, AE, Sales Manager) nhằm chuẩn hóa cách quản lý **pipeline bán hàng B2B**, theo dõi **KPI doanh số** và thực hiện **dự báo doanh thu (forecast)** chính xác theo tháng/quý.

Mọi hoạt động cập nhật deal bắt buộc phải ghi nhận đầy đủ trên **Salesforce CRM** trước 17:00 mỗi thứ Sáu.

---

## 2. Definitions – Các giai đoạn (Deal Stages) trong Pipeline

| Stage | Mô tả | Thời gian tối đa ở stage | Xác suất closing | Quyền cập nhật |
|-------|-------|------------------------|------------------|----------------|
| 1. Prospecting | Lead mới từ marketing hoặc tự tìm, chưa tiếp xúc | 7 ngày | 10% | SDR / AE |
| 2. Qualified | Đã xác thực nhu cầu, ngân sách sơ bộ, DM đã nghe pitch | 14 ngày | 25% | AE |
| 3. Proposal Sent | Đã gửi báo giá/kế hoạch triển khai | 21 ngày | 40% | AE |
| 4. Negotiation | Đang thương lượng giá, điều khoản, có đối thủ cạnh tranh | 30 ngày | 60% | AE + Sales Manager |
| 5. Legal / Procurement | Hợp đồng được legal review, khách hàng xử lý nội bộ | 15 ngày | 80% | Sales Manager |
| 6. Closed Won | Ký kết thành công, đã nhận PO | – | 100% | Sales Admin |
| 7. Closed Lost | Thua deal, có lý do rõ ràng | – | 0% | AE |

> 🔁 **Stale deal** – Nếu một deal không có hoạt động nào trong 14 ngày, hệ thống tự động chuyển về stage **Prospecting** và giảm 50% trọng số forecast.

---

## 3. KPI Sales cá nhân & Team (Q1 2026)

### 3.1 Mục tiêu doanh số (Quota) theo role

| Role | Monthly Quota (VNĐ) | Quarterly Target (VNĐ) | Minimum Activity (cuộc gọi / email / tuần) |
|------|---------------------|------------------------|---------------------------------------------|
| SDR | 0 (chỉ chịu trách nhiệm meeting) | Tạo 20 Qualified meetings | 60 cuộc gọi + 40 email |
| AE (Junior) | 400 triệu | 1.2 tỷ | 30 cuộc gọi + 20 email |
| AE (Senior) | 800 triệu | 2.4 tỷ | 20 cuộc gọi + 15 email |
| Sales Manager | 2 tỷ (team) | 6 tỷ | không yêu cầu, nhưng phải review pipeline 2 lần/tuần |

### 3.2 Bảng theo dõi KPI pipeline – Tháng 2/2026 (giả lập)

| AE Name | Total Pipeline (tỷ) | Weighted Pipeline (tỷ) | # Deals in Negotiation | Forecasted Revenue (tỷ) | Actual Closed Won (tỷ) | Conversion Rate |
|---------|---------------------|-------------------------|------------------------|--------------------------|------------------------|------------------|
| Nguyễn Văn A | 3.2 | 1.9 | 2 | 1.4 | 0.9 | 64% |
| Trần Thị B | 5.0 | 3.1 | 4 | 2.5 | 1.7 | 68% |
| Lê Văn C | 1.5 | 0.8 | 1 | 0.6 | 0.2 | 33% |

> **Note:** Weighted Pipeline được tính bằng tổng (giá trị deal * xác suất closing theo stage).  
> AE nào có **weighted pipeline < 1.5x monthly quota** trong 2 tuần cuối tháng sẽ bị **quản lý kèm cặp hàng ngày** và có thể yêu cầu cải thiện forecast.

---

## 4. Quy trình xử lý Enterprise Deal (>1 tỷ)

### 4.1 Kích hoạt “Deal Desk”

Khi một deal có tổng giá trị hợp đồng **trên 1 tỷ VNĐ** (hoặc ACV > 500 triệu), AE phải:

- Tạo **Salesforce Task** với loại `Enterprise Deal – Request Deal Desk`
- Đính kèm:
  - Thông tin khách hàng (industry, revenue, decision maker)
  - Bản dự thảo giải pháp (solution outline)
  - Đối thủ cạnh tranh dự kiến
- **Trong vòng 24h**, Deal Desk (gồm Sales Manager + Product + Legal) họp để duyệt discount < 15% và tài liệu đấu thầu.

> ⚠️ **Nghiêm cấm** tự ý commit mức chiết khấu > 10% hoặc điều khoản thanh toán trả chậm > 30 ngày nếu chưa qua Deal Desk.

### 4.2 Enterprise forecast tracker

Mỗi thứ Hai, Sales Manager gửi email cập nhật **Top 5 Enterprise Deals** (theo mẫu dưới đây) đến VP of Sales và Finance:

| Account | Deal Value (tỷ) | Stage | Expected Sign Date | Risk Level (High/Medium/Low) | Mitigation Plan |
|---------|----------------|-------|--------------------|------------------------------|------------------|
| FPT Software | 2.5 | Legal | 20/03/2026 | Medium – chờ pháp lý bên đối tác | Đã gửi bản hợp đồng sửa theo yêu cầu, follow-up hàng ngày |
| VNG Corp | 1.8 | Negotiation | 25/03/2026 | High – đối thủ IBM giảm giá 12% | Đề xuất tặng thêm 50 giờ hỗ trợ triển khai (đã được Deal Desk duyệt) |

---

## 5. Hướng dẫn nhập liệu trên Salesforce CRM

Các trường bắt buộc khi tạo/ cập nhật deal:

- `Account Name` – phải khớp với mã khách hàng trên hệ thống **Dynamics 365** (tham khảo tài liệu [IT Support - CRM Integration](v.v. chưa có, như nếu cần thì cross-reference: "Xem thêm hướng dẫn đồng bộ từ IT tại `//it-portal/crm-dynamics`"))
- `Deal Stage` – theo bảng ở Section 2
- `Expected Close Date` – không được nằm ngoài quý hiện tại nếu stage >= Proposal
- `Competitors` – nếu có >2 đối thủ, phải ghi rõ **chiến lược khác biệt** (không bỏ trống)
- `Next Step` – cụ thể, có ngày tháng, không được ghi chung chung như “call again”

> Mỗi tuần, **Sales Ops** sẽ chạy script kiểm tra dữ liệu dirty (thiếu next step, expected close date trong quá khứ) và gửi báo cáo vi phạm vào thứ Ba hàng tuần. AE vi phạm 3 lần trở lên trong quý sẽ bị **trừ 10% thưởng KPI**.

---

## 6. Quy trình dự báo doanh thu hàng tháng (Sales Forecast)

- **Ngày 25 hàng tháng:** Sales Manager tổng hợp commit forecast từ các AE (dựa trên weighted pipeline, nhưng chỉ tính các deal có xác suất >= 60%)
- **Ngày 27:** Gửi bảng forecast dạng Excel cho Finance và CEO qua email với tiêu đề `Forecast <tháng>_<năm> - Sales Dept`
- **Cuối tháng:** So sánh forecast với actual closed won. Sai số **dưới 15%** được chấp nhận. Sai số > 30% yêu cầu giải trình bằng văn bản và kèm kế hoạch cải thiện.

**Cách tính Forecast Accuracy:**

`(1 - |Forecast - Actual| / Actual) * 100%`

(Áp dụng khi Actual > 0. Nếu Actual = 0 và Forecast > 0 => Accuracy = 0%)

---

## 7. Một số lưu ý và xử lý tình huống thực tế

### ❌ Deal bị “chôn” (Inactive)

- **Dấu hiệu:** không thay đổi stage trong 21 ngày, khách hàng không trả lời email.
- **Hành động:** AE phải gắn tag `At Risk` và đề xuất chiến dịch “unfreeze” (gọi trực tiếp, gặp mặt, offer dùng thử mở rộng). Nếu sau 7 ngày không tiến triển, Manager có quyền chuyển deal đó cho AE khác hoặc đóng thành Lost.

### ✅ Deal cần đẩy nhanh cuối quý

Nếu cần áp dụng chính sách **“end-of-quarter discount”** (tối đa 5% ngoại lệ), phải có email phê duyệt từ Sales Director. Tham khảo thêm quy trình phê duyệt discount chung trong **Sales Approval Policy** (chưa có trong hệ thống, giả định).

### 🧾 Ghi chú trên CRM (không được làm gì?)

- **Cấm** ghi thông tin bảo mật của khách hàng (mật khẩu, thông tin thẻ tín dụng) lên CRM.  
  Nếu cần lưu trữ thông tin nhạy cảm, sử dụng hệ thống quản lý tài liệu bảo mật theo [Chính sách bảo mật TechCorp](Chinh_sach_Bao_mat_TechCorp.md) (chỉ Manager mới có quyền truy cập file đính kèm được mã hóa).

- **Nên** ghi nhật ký ngắn gọn mỗi lần tiếp xúc: “25/2 gọi anh Tuấn – được confirm budget 700tr, hẹn demo 28/2”

---
