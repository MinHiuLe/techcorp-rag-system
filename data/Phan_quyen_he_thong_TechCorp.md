# Chính sách Phân quyền Hệ thống Tri thức TechCorp

Tài liệu này quy định quyền hạn truy cập thông tin của các vai trò trong hệ thống trợ lý AI.

## Quy định vai trò
1. **Public**: Nhân viên mới, thực tập sinh. Được tiếp cận quy trình cơ bản và văn hóa công ty.
2. **Manager**: Trưởng nhóm, Quản lý dự án. Được tiếp cận thêm các quy trình phê duyệt và điều phối nhân sự.
3. **Lead**: Tech Lead, Giám đốc kỹ thuật. Được tiếp cận toàn bộ dữ liệu, bao gồm các chính sách bảo mật tối mật.

## Cơ chế bảo mật
Hệ thống sử dụng cơ chế Filter ngay tại tầng Database (Qdrant). Khi người dùng hỏi, hệ thống sẽ tự động lọc bỏ các tài liệu vượt quá cấp độ bảo mật của người đó trước khi đưa dữ liệu cho AI xử lý.

## Metadata (for RAG)
- category: Security
- security_level: Public