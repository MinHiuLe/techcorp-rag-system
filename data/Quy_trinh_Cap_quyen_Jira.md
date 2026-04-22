# Quy trình Cấp Quyền Jira - TechCorp

## 1. Mục tiêu

Quy trình này quy định cách thức yêu cầu, phê duyệt và cấp quyền truy cập vào hệ thống Jira của TechCorp nhằm đảm bảo:

- Kiểm soát truy cập theo nguyên tắc Least Privilege
- Đảm bảo an toàn thông tin dự án
- Truy vết đầy đủ các hành động cấp quyền
- Tuân thủ chính sách bảo mật nội bộ

---

## 2. Phạm vi áp dụng

Áp dụng cho toàn bộ:

- Nhân viên chính thức TechCorp
- Intern / Contractor
- Team dự án sử dụng Jira (Software / Service Management / Product Boards)

---

## 3. Phân loại quyền trong Jira

### 3.1 Project Roles

| Role | Mô tả | Quyền chính |
|------|------|-------------|
| Viewer | Chỉ xem ticket | Read-only |
| Developer | Tham gia xử lý ticket | Create / Update issue |
| Tester | Kiểm thử | Update status / comment |
| Project Manager | Quản lý dự án | Full project control |
| Admin | Quản trị hệ thống project | Configure project settings |

---

### 3.2 Permission Scheme

Jira permission được chia thành các nhóm:

- Browse Projects
- Create Issues
- Edit Issues
- Assign Issues
- Transition Issues
- Manage Sprints
- Administer Projects

---

## 4. Điều kiện cấp quyền

### 4.1 Điều kiện chung

Người dùng chỉ được cấp quyền khi:

- Có email công ty hợp lệ
- Có role rõ ràng trong dự án
- Có nhu cầu công việc cụ thể (need-to-know)
- Được Project Manager hoặc Team Lead phê duyệt

---

### 4.2 Điều kiện theo cấp độ quyền

#### Viewer
- Tự động cấp nếu được add vào project
- Không cần phê duyệt nâng cao

#### Developer / Tester
- Phải có xác nhận từ Team Lead
- Phải thuộc team dự án liên quan

#### Project Manager / Admin
- Phải có phê duyệt từ Head of Department
- Security Team review bắt buộc

---

## 5. Quy trình cấp quyền (Workflow)

### Bước 1: Tạo yêu cầu

Người dùng tạo ticket trên Jira Service Management:

- Project: IT-Access-Request
- Issue Type: Access Request
- Thông tin bắt buộc:
  - Họ tên
  - Email công ty
  - Project cần truy cập
  - Role mong muốn
  - Lý do sử dụng

---

### Bước 2: Xác thực yêu cầu

IT Support kiểm tra:

- Email hợp lệ
- Project tồn tại
- Role phù hợp với vị trí

Nếu thiếu thông tin → trả lại yêu cầu

---

### Bước 3: Phê duyệt

Luồng phê duyệt:

- Level 1: Team Lead
- Level 2 (nếu cần): Project Manager
- Level 3 (Admin / Sensitive project): Security Team

---

### Bước 4: Cấp quyền

Sau khi phê duyệt:

- Thêm user vào Project Role tương ứng
- Cập nhật Permission Scheme nếu cần
- Ghi log vào hệ thống audit

---

### Bước 5: Xác nhận

- Gửi email xác nhận cho người dùng
- Cập nhật trạng thái ticket: DONE
- Lưu log vào hệ thống compliance

---

## 6. Thời gian xử lý (SLA)

| Loại yêu cầu | Thời gian |
|--------------|----------|
| Viewer access | ≤ 4 giờ |
| Developer / Tester | ≤ 1 ngày |
| Admin / Sensitive project | ≤ 3 ngày |

---

## 7. Thu hồi quyền (Access Revocation)

Quyền truy cập sẽ bị thu hồi khi:

- Nhân viên rời dự án
- Chuyển team
- Kết thúc hợp đồng
- Phát hiện vi phạm bảo mật

### Quy trình thu hồi:

1. Nhận yêu cầu từ HR / Manager
2. Xác minh lý do
3. Remove user khỏi project roles
4. Revoke active sessions
5. Ghi log audit

---

## 8. Nguyên tắc bảo mật

- Không chia sẻ tài khoản Jira
- Không cấp quyền vượt cấp không có phê duyệt
- Không giữ quyền sau khi không còn nhu cầu
- Tất cả thay đổi quyền phải được log lại

---

## 9. Các lỗi thường gặp

### ❌ Không truy cập được project

- Nguyên nhân: chưa được add vào role
- Giải pháp: kiểm tra ticket cấp quyền

---

### ❌ Không thấy board / sprint

- Nguyên nhân: thiếu permission Browse Project
- Giải pháp: yêu cầu Team Lead bổ sung quyền

---

### ❌ Bị mất quyền đột ngột

- Nguyên nhân: thu hồi quyền do chuyển team / audit
- Giải pháp: tạo lại request nếu cần thiết

---

## 10. Audit & Compliance

- Tất cả thay đổi quyền được log trong 180 ngày
- Audit định kỳ mỗi tháng bởi Security Team
- Báo cáo quyền truy cập gửi cho Head of Engineering

---

## 11. Metadata (RAG Indexing)

- doc_type: access_control_procedure
- system: jira
- category: devops_access_management
- security_level: internal
- compliance: audit_required
- chunking_strategy: procedural_steps
- embedding_priority: high