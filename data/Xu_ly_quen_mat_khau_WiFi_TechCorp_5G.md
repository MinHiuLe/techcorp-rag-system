# Hướng dẫn xử lý sự cố quên mật khẩu Wi-Fi công ty (TechCorp_5G)

## Mục đích

Hướng dẫn này giúp nhân viên TechCorp khôi phục hoặc đặt lại mật khẩu Wi-Fi nội bộ **TechCorp_5G** khi quên hoặc gặp lỗi xác thực.

## Đối tượng áp dụng

- Nhân viên, thực tập sinh, contractor làm việc tại văn phòng TechCorp
- Khách mới (cần đăng nhập qua guest network)

## Thông tin mạng Wi-Fi văn phòng

| Tên mạng (SSID) | Mục đích | Xác thực |
|----------------|----------|----------|
| TechCorp_5G | Nhân viên (băng tần 5GHz, tốc độ cao) | Mật khẩu cá nhân + 802.1X (RADIUS) |
| TechCorp_Guest | Khách, thiết bị IoT | Mật khẩu chung thay đổi hàng tuần (lấy từ reception) |

> **Lưu ý:** Mật khẩu **TechCorp_5G** được đồng bộ với mật khẩu đăng nhập máy tính (Active Directory). Nếu bạn đổi mật khẩu AD, mật khẩu Wi-Fi cũng thay đổi theo.

## Các bước xử lý khi quên mật khẩu

### Trường hợp 1: Bạn vẫn đang đăng nhập được vào máy tính công ty

1. Kết nối vào mạng có dây (LAN) hoặc sử dụng VPN từ xa (nếu ở nhà).
2. Mở trình duyệt, truy cập `https://portal.techcorp.local/selfservice/wifi`
3. Đăng nhập bằng tài khoản công ty.
4. Chọn **"Hiển thị mật khẩu Wi-Fi hiện tại"** → hệ thống gửi mật khẩu qua email công ty.
5. (Tùy chọn) Chọn **"Đặt lại mật khẩu Wi-Fi"** để đồng bộ với mật khẩu AD mới.

### Trường hợp 2: Bạn không thể đăng nhập máy tính (quên cả mật khẩu AD)

- Liên hệ IT Support qua số **8888** hoặc nhờ đồng nghiệp tạo ticket Jira (dự án `IT-Support`, loại `Password Reset`).
- IT sẽ xác thực danh tính qua câu hỏi bảo mật hoặc MFA dự phòng.
- Sau khi đặt lại mật khẩu AD, mật khẩu Wi-Fi sẽ được cập nhật sau 5 phút.

### Trường hợp 3: Bạn ở văn phòng và chưa có kết nối mạng nào

1. Đến quầy **IT Support** (tầng 5, tòa nhà A) mang theo thẻ nhân viên.
2. Yêu cầu IT cấp mật khẩu tạm thời cho **TechCorp_5G** (có hiệu lực 24 giờ).
3. Sau khi kết nối, thực hiện các bước ở **Trường hợp 1** để đổi mật khẩu vĩnh viễn.

## Kết nối Wi-Fi lần đầu (cho nhân viên mới)

1. Bật Wi-Fi trên thiết bị, chọn mạng **TechCorp_5G**.
2. Nhập **tên đăng nhập**: `ten_dang_nhap_AD@techcorp.com` (ví dụ: `nguyen.vanA@techcorp.com`)
3. Nhập **mật khẩu** là mật khẩu AD (cấp khi onboarding).
4. Nếu thiết bị hỏi chứng chỉ (CA), chọn **"Chấp nhận"**.
5. Kết nối thành công → thiết bị sẽ tự động lưu mạng.

> **Dành cho macOS:** Khi kết nối, có thể xuất hiện cửa sổ yêu cầu nhập **tên người dùng và mật khẩu máy** để cập nhật vào keychain. Hãy nhập mật khẩu máy của bạn.

## Xử lý sự cố thường gặp

| Sự cố | Nguyên nhân có thể | Giải pháp |
|-------|--------------------|------------|
| "Unable to join network" | Sai mật khẩu | Xóa mạng khỏi danh sách đã nhớ, kết nối lại, nhập lại mật khẩu |
| "Authentication failed" | Tài khoản AD bị khóa hoặc hết hạn | Liên hệ IT để kiểm tra trạng thái tài khoản |
| Kết nối được nhưng không có internet | IP conflict hoặc DNS lỗi | Chạy lệnh `ipconfig /release && renew` (Windows) hoặc tắt/bật Wi-Fi |
| Wi-Fi liên tục ngắt kết nối | Nhiễu tần số, driver cũ | Cập nhật driver card mạng, chuyển sang băng tần 2.4GHz (nếu có SSID TechCorp_2G) |

## Câu hỏi thường gặp (FAQ)

**1. Tôi có thể dùng Wi-Fi cho điện thoại cá nhân không?**  
Có, nhưng phải đăng ký thiết bị với IT (MAC address) qua cổng self-service. Không được chia sẻ mật khẩu.

**2. Mật khẩu Wi-Fi có thay đổi định kỳ không?**  
Có, mỗi 90 ngày hoặc khi bạn đổi mật khẩu AD. Hệ thống sẽ gửi email nhắc nhở trước 7 ngày.

**3. Tôi quên mật khẩu AD và không có quyền truy cập email công ty?**  
Liên hệ trực tiếp IT Support hoặc gọi hotline 8888. Họ sẽ xác thực bằng CMND/CCCD và cấp lại mật khẩu.

**4. Khách hàng của tôi cần dùng Wi-Fi thì làm thế nào?**  
Hướng dẫn khách kết nối vào **TechCorp_Guest** và lấy mật khẩu từ lễ tân (thay đổi hàng tuần). Không cho khách dùng mạng nội bộ.
