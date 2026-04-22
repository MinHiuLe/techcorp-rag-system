# Chính sách bảo mật - TechCorp

## Mục tiêu
Thiết lập các nguyên tắc và quy định nhằm bảo vệ hệ thống, dữ liệu và hạ tầng công nghệ của TechCorp trước các rủi ro bảo mật.

---

## 1. Nguyên tắc bảo mật cốt lõi

### 1.1 Least Privilege
- Mỗi người dùng chỉ được cấp quyền tối thiểu cần thiết để thực hiện công việc

### 1.2 Zero Trust
- Không tin tưởng bất kỳ truy cập nào nếu chưa được xác thực và kiểm tra

### 1.3 Defense in Depth
- Áp dụng nhiều lớp bảo mật (network, application, data)

---

## 2. Quản lý truy cập (Access Control)

- Mỗi nhân viên có tài khoản riêng
- Cấm chia sẻ tài khoản dưới mọi hình thức
- Bắt buộc bật Multi-Factor Authentication (MFA)
- Session timeout sau 15 phút không hoạt động

---

## 3. Phân loại dữ liệu

| Level        | Mô tả |
|-------------|------|
| Public      | Có thể công khai |
| Internal    | Chỉ dùng trong công ty |
| Confidential| Nhạy cảm, hạn chế truy cập |

---

## 4. Xử lý dữ liệu nhạy cảm

- Dữ liệu Confidential phải được mã hóa:
  - Khi lưu trữ (at rest)
  - Khi truyền tải (in transit - HTTPS/TLS)
- Không lưu dữ liệu nhạy cảm trên máy cá nhân
- Không upload dữ liệu lên dịch vụ bên thứ 3 nếu chưa được phê duyệt

---

## 5. Bảo mật hệ thống

### 5.1 Infrastructure
- Sử dụng firewall và network segmentation
- Chỉ mở port cần thiết

### 5.2 Application
- Validate input để tránh SQL Injection / XSS
- Không expose API nội bộ ra public

### 5.3 Logging & Monitoring
- Ghi log toàn bộ hoạt động quan trọng
- Sử dụng hệ thống monitoring để phát hiện bất thường

---

## 6. Quản lý thiết bị

- Chỉ sử dụng thiết bị được công ty cấp phát
- Bắt buộc cài đặt antivirus và cập nhật định kỳ
- Cấm cài phần mềm không rõ nguồn gốc

---

## 7. Incident Response

### 7.1 Khi phát hiện sự cố
- Báo ngay cho IT/Security Team
- Không tự ý xử lý nếu chưa được phép

### 7.2 Quy trình xử lý
1. Xác định mức độ nghiêm trọng (Severity)
2. Cô lập hệ thống bị ảnh hưởng
3. Phân tích nguyên nhân
4. Khắc phục và khôi phục
5. Báo cáo hậu kiểm (Post-mortem)

---

## 8. Phân quyền theo vai trò (RBAC Mapping)

| Role      | Quyền truy cập |
|----------|--------------|
| Intern   | Chỉ truy cập dữ liệu Public / Internal (hạn chế) |
| Engineer | Truy cập dữ liệu Internal + một phần Confidential |
| Manager  | Truy cập toàn bộ hệ thống |

---

## 9. Các hành vi bị cấm

- Truy cập trái phép vào hệ thống
- Cố gắng bypass security
- Chia sẻ thông tin nội bộ ra bên ngoài
- Sử dụng tài nguyên công ty cho mục đích cá nhân không được phép

---

## 10. Kiểm toán & tuân thủ

- Kiểm tra bảo mật định kỳ hàng quý
- Audit log phải được lưu trữ tối thiểu 90 ngày
- Tuân thủ các tiêu chuẩn bảo mật nội bộ

---

## 11. Lỗi thường gặp & cách xử lý

### ❌ Quên bật MFA
- Nguy cơ: tài khoản dễ bị chiếm quyền
- Giải pháp: kích hoạt MFA ngay trong hệ thống

### ❌ Truy cập bị từ chối (Access Denied)
- Nguyên nhân: chưa đủ quyền
- Giải pháp: tạo ticket yêu cầu cấp quyền

### ❌ Lộ credentials
- Nguyên nhân: commit lên Git
- Giải pháp:
  - Rotate credentials ngay lập tức
  - Xóa thông tin khỏi repository

---

## Metadata (for RAG)

- category: security
- domain: security_policy
- security_level: confidential
- access_scope: restricted
- requires_role: manager_or_above