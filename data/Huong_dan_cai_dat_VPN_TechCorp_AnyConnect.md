# Hướng dẫn cài đặt và kết nối VPN TechCorp-AnyConnect

## Mục đích

Hướng dẫn này giúp nhân viên TechCorp thiết lập và sử dụng VPN (Virtual Private Network) khi làm việc từ xa, đảm bảo kết nối an toàn đến hệ thống nội bộ.

## Đối tượng áp dụng

- Toàn bộ nhân viên chính thức TechCorp
- Nhân viên làm việc hybrid hoặc remote
- Contractor có nhu cầu truy cập nội bộ

## Yêu cầu trước khi cài đặt

- Thiết bị được công ty cấp phát (hoặc thiết bị cá nhân đã được IT approve)
- Hệ điều hành: Windows 10/11, macOS 11+, Ubuntu 20.04+, iOS 14+, Android 10+
- Tài khoản công ty (email + mật khẩu) có kích hoạt MFA

## Các bước thực hiện

### Bước 1: Tải và cài đặt AnyConnect

1. Truy cập cổng nội bộ: `https://it-portal.techcorp.local/downloads`
2. Chọn mục **VPN Clients** → **TechCorp-AnyConnect**
3. Tải file cài đặt phù hợp với hệ điều hành của bạn.
4. Chạy file cài đặt với quyền Administrator (Windows) hoặc mở gói `.dmg` (macOS).

> **Lưu ý:** Nếu không truy cập được cổng nội bộ, liên hệ IT Support qua số **8888** hoặc email `it-support@techcorp.com`.

### Bước 2: Cấu hình kết nối VPN

1. Mở ứng dụng **TechCorp-AnyConnect**.
2. Nhập địa chỉ server: `vpn.techcorp.com`
3. Nhấn **Connect**.
4. Đăng nhập bằng email công ty và mật khẩu.
5. Xác thực MFA qua ứng dụng **Microsoft Authenticator** ho **Google Authenticator** (theo hướng dẫn của Security Team).
6. Sau khi xác thực thành công, trạng thái sẽ hiển thị **Connected**.

### Bước 3: Kiểm tra kết nối

- Mở trình duyệt, truy cập `https://portal.techcorp.local`
- Nếu hiển thị trang đăng nhập nội bộ → kết nối thành công.

## Xử lý sự cố thường gặp

| Sự cố | Nguyên nhân | Giải pháp |
|-------|-------------|------------|
| Không kết nối được, báo "Connection timeout" | Tường lửa chặn hoặc sai server | Kiểm tra tường lửa, thử lại với mạng khác, liên hệ IT nếu vẫn lỗi |
| Sai mật khẩu dù đã nhập đúng | Tài khoản bị khóa hoặc hết hạn | Mở ticket trên Jira Service Management (Dự án: IT-Access-Request) |
| Kết nối nhưng không truy cập được nội bộ | Split tunnel chưa đúng | Khởi động lại AnyConnect, chạy lệnh `ipconfig /flushdns` (Windows) hoặc `sudo dscacheutil -flushcache` (macOS) |
| MFA không nhận được mã | Đồng hồ thiết bị lệch | Đồng bộ thời gian qua internet, thử lại sau 1 phút |

## Câu hỏi thường gặp (FAQ)

**1. VPN có tự động kết nối khi tôi mở máy không?**  
Có, bạn có thể bật tính năng **Auto-connect** trong cài đặt AnyConnect. Tuy nhiên vẫn cần đăng nhập MFA mỗi lần.

**2. Tôi có thể dùng VPN trên điện thoại cá nhân không?**  
Được, nhưng phải cài đặt ứng dụng **TechCorp-AnyConnect** từ cửa hàng chính thức và đăng ký thiết bị với IT (gửi MAC address qua email).

**3. VPN ảnh hưởng đến tốc độ mạng như thế nào?**  
Có thể giảm 10-20% do mã hóa. Nếu cần truyền tải dữ liệu lớn, hãy sử dụng mạng công ty trực tiếp hoặc dùng chế độ **Split Tunnel** (đã được cấu hình mặc định).

**4. Làm sao để ngắt kết nối VPN?**  
Nhấn **Disconnect** trong giao diện AnyConnect. Luôn ngắt kết nối khi không làm việc để giảm tải cho gateway.

## Chính sách bảo mật bổ sung

- **Cấm** chia sẻ tài khoản VPN với bất kỳ ai.
- **Cấm** kết nối VPN từ máy tính công cộng (quán cà phê, thư viện).
- **Bắt buộc** báo cáo ngay cho IT nếu nghi ngờ tài khoản bị xâm phạm.
- Kết nối VPN sẽ tự động ngắt sau 8 giờ không hoạt động.

## Metadata (RAG)

doc_type: end_user_guide  
system: vpn  
category: remote_access  
security_level: internal  
platform: anyconnect  
embedding_priority: high