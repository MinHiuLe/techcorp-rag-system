# Chính sách cấp phát, bảo hành và thu hồi thiết bị phần cứng (Macbook / Dell)

## Mục đích

Quy định này nhằm đảm bảo việc quản lý, sử dụng và bảo vệ tài sản phần cứng của TechCorp (laptop, màn hình, phụ kiện) được thống nhất, minh bạch và tuân thủ an ninh thông tin.

## Đối tượng áp dụng

- Tất cả nhân viên chính thức và thử việc
- Thực tập sinh (Intern) được cấp thiết bị
- Contractor làm việc dài hạn (>3 tháng)

## Phân loại thiết bị

| Loại | Thương hiệu | Cấu hình tối thiểu | Đối tượng |
|------|-------------|--------------------|------------|
| Laptop tiêu chuẩn | MacBook Pro 14" (M3) | 16GB RAM, 512GB SSD | Kỹ sư, thiết kế, quản lý |
| Laptop phổ thông | Dell Latitude 5440 | 16GB RAM, 256GB SSD | Hành chính, nhân sự, kế toán |
| Workstation | Dell Precision 7680 | 32GB RAM, 1TB SSD, RTX A2000 | AI/ML, đồ họa nặng |
| Màn hình phụ | Dell UltraSharp 27" 4K | 60Hz, USB-C | Theo nhu cầu được phê duyệt |

## Quy trình cấp phát

### Bước 1: Đề xuất nhu cầu

- Nhân viên mới: HR gửi yêu cầu đến IT qua **Jira Service Management** (dự án `Hardware-Request`) trước ngày nhận việc 5 ngày làm việc.
- Nhân viên hiện tại: tạo ticket với lý do (nâng cấp, thay thế hư hỏng, thay đổi vai trò).

### Bước 2: Phê duyệt

- Manager duyệt nhu cầu.
- IT kiểm tra kho và cấu hình phù hợp.
- Budget (nếu thiết bị đặc biệt) cần phê duyệt của Head of Finance.

### Bước 3: Bàn giao

- Nhân viên ký **Biên bản bàn giao tài sản** (lưu trên HR system).
- IT cài đặt hệ điều hành chuẩn (macOS Ventura hoặc Windows 11 Pro), phần mềm bảo mật (CrowdStrike, BitLocker/FileVault), và agent giám sát.
- Nhân viên xác nhận nhận thiết bị qua email.

## Chính sách bảo hành và hỗ trợ

### Bảo hành tiêu chuẩn

- **Thời gian:** 24 tháng kể từ ngày cấp phát (tương ứng bảo hành nhà sản xuất).
- **Phạm vi:** Lỗi phần cứng không do va đập, rơi vỡ, vào nước.
- **Hỗ trợ:** IT sẽ xử lý đổi trả trong vòng 7 ngày làm việc.

### Hết bảo hành (tháng thứ 25 trở đi)

- Sửa chữa tính phí theo báo giá của đối tác.
- Thay thế thiết bị tương đương nếu chi phí sửa > 50% giá trị thiết bị (phải có phê duyệt cấp cao).

### Quyền lợi nâng cấp

- Mỗi nhân viên được nâng cấp laptop tối đa 1 lần sau 3 năm sử dụng.
- Yêu cầu nâng cấp phải kèm lý do kỹ thuật (ví dụ: không đủ RAM cho công việc mới).

## Quy trình thu hồi thiết bị

### Các trường hợp thu hồi

- Nhân viên nghỉ việc (tự nguyện hoặc bị sa thải)
- Chuyển đổi vị trí không cần thiết bị cũ
- Thiết bị hư hỏng nặng, thay thế bằng máy mới
- Kết thúc hợp đồng contractor

### Các bước thực hiện

1. **Thông báo:** HR gửi yêu cầu thu hồi đến IT và nhân viên.
2. **Bàn giao:** Nhân viên mang thiết bị (kèm sạc, phụ kiện) đến IT Support (tầng 5, tòa nhà A) trong vòng 5 ngày làm việc.
3. **Kiểm tra:** IT kiểm tra tình trạng, ghi nhận hư hỏng (nếu có) và xóa dữ liệu theo tiêu chuẩn NIST 800-88.
4. **Xác nhận:** IT cập nhật trạng thái trên hệ thống quản lý tài sản, gửi email xác nhận hoàn tất cho HR và nhân viên.
5. **Phí phạt (nếu có):** Mất phụ kiện (sạc, dây cáp) sẽ bị khấu trừ vào lương cuối kỳ theo bảng giá nội bộ.

## Xử lý sự cố thường gặp

| Sự cố | Hành động ngay |
|-------|----------------|
| Máy bị mất cắp | Báo Security (hotline 8888) và IT trong vòng 2 giờ, nộp báo cáo công an (nếu có) |
| Hỏng màn hình do rơi vỡ | Tạo ticket mô tả chi tiết, chờ IT báo giá sửa chữa (chi phí do nhân viên chịu nếu không có bảo hiểm) |
| Không nhận được thiết bị khi mới vào | Kiểm tra email onboarding, liên hệ IT Support qua số **8888** hoặc ticket Jira |

## Câu hỏi thường gặp (FAQ)

**1. Tôi có thể mượn thiết bị về nhà cuối tuần không?**  
Có, nhưng phải đảm bảo an toàn và không được cài phần mềm trái phép.

**2. Tôi tự ý nâng cấp RAM/SSD có được không?**  
Không, việc này làm mất bảo hành và vi phạm chính sách. Mọi nâng cấp phải do IT thực hiện.

**3. Làm thế nào để yêu cầu màn hình phụ?**  
Tạo ticket trên Jira (Hardware-Request), ghi rõ lý do (ví dụ: cần màn hình rộng cho lập trình giao diện). Manager duyệt → IT cấp.

**4. Thiết bị cũ của tôi có được giữ lại sau khi nghỉ việc không?**  
Không. Tất cả tài sản công ty phải được hoàn trả, trừ khi có thỏa thuận mua lại bằng văn bản và được CFO phê duyệt.
