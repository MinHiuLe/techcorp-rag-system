# Quy định về An toàn thông tin: Cách nhận biết email Phishing và báo cáo IT

## Mục đích

Tài liệu này trang bị cho nhân viên TechCorp kỹ năng nhận diện email lừa đảo (phishing) và quy trình xử lý, báo cáo kịp thời nhằm bảo vệ dữ liệu công ty và tài khoản cá nhân.

## Đối tượng áp dụng

- Toàn bộ nhân viên chính thức, thực tập sinh, contractor
- Bất kỳ ai có hộp thư công ty `@techcorp.com`

## Dấu hiệu nhận biết email Phishing

### 1. Kiểm tra địa chỉ người gửi

- Tên hiển thị có thể giả (ví dụ: "IT Support") nhưng email thực sự lại từ `techcorp-secure@gmail.com` hoặc `support@techcorp-security.net`.
- Miền `@techcorp.com` chính thống chỉ có đuôi `@techcorp.com`, không có ký tự lạ như `@techcorp-verify.com`.

### 2. Nội dung tạo cảm giác cấp bách hoặc đe dọa

- "Tài khoản của bạn sẽ bị khóa trong 24h"
- "Bạn đã trúng thưởng, hãy click vào link để nhận quà"
- "Yêu cầu xác minh khẩn cấp do vi phạm bảo mật"

### 3. Đường dẫn (link) giả mạo

- Di chuột vào link (không click) sẽ thấy URL không phải `techcorp.com`. Ví dụ: `http://techcorp.xyz/login` hoặc `https://techcorp-security. net`.
- Link rút gọn (bit.ly, tinyurl) không rõ đích đến.

### 4. Tệp đính kèm đáng ngờ

- File `.exe`, `.scr`, `.zip` có mật khẩu, `.docm` (macro) gửi từ người lạ.
- Hóa đơn, thông báo chuyển tiền bất ngờ.

### 5. Lỗi chính tả, ngữ pháp kỳ lạ

- Câu cú lủng củng, dùng sai dấu câu, viết hoa tùy tiện.
- Tên công ty viết sai (TechCorp → TechCrop, TechCorp).

## Quy trình xử lý khi nghi ngờ

### Nếu bạn chưa tương tác gì với email (chưa click link, chưa mở file)

1. **Chụp màn hình** email (che dấu thông tin cá nhân nếu cần).
2. **Chuyển tiếp email** (dưới dạng attachment) đến địa chỉ: `phishing@techcorp.com`
3. **Xóa email** khỏi hộp thư và thư mục đã xóa.

### Nếu bạn đã click vào link hoặc tải file

1. **Ngắt kết nối mạng ngay lập tức** (tắt Wi-Fi, rút cáp mạng).
2. **Không nhập bất kỳ thông tin nào** nếu trang web yêu cầu.
3. **Báo cáo khẩn cấp** qua hotline **8888** (nội bộ) hoặc gửi ticket Jira với mức **Severity 1**.
4. **Chạy quét toàn bộ máy tính** bằng phần mềm CrowdStrike (có sẵn trên máy công ty) theo hướng dẫn của IT.

### Nếu bạn đã nhập mật khẩu hoặc thông tin nhạy cảm

- Ngay lập tức **đổi mật khẩu AD và tất cả mật khẩu** có liên quan (email, VPN, Jira, GitHub).
- Kích hoạt MFA lại nếu bị vô hiệu hóa.
- Thông báo cho Security Team để họ kiểm tra log đăng nhập và thu hồi session.

## Trách nhiệm của nhân viên

- **Luôn kiểm tra** email trước khi click.
- **Không chuyển tiếp** email lừa đảo cho đồng nghiệp (có thể gây hoang mang). Chỉ chuyển cho `phishing@techcorp.com`.
- **Hoàn thành khóa đào tạo** "Nhận biết lừa đảo trực tuyến" mỗi năm một lần (bắt buộc).
- **Báo cáo ngay** dù chỉ nghi ngờ nhẹ – không có hình phạt cho báo cáo sai.

## Các hình thức lừa đảo nâng cao cần biết

- **Spear phishing:** Email được cá nhân hóa, biết tên bạn, dự án bạn đang làm. Nguồn có thể từ lộ thông tin công khai.
- **Clone phishing:** Email gần giống với email thật từ nội bộ (ví dụ: thông báo lương, thay đổi chính sách) nhưng đường dẫn thay đổi.
- **Vishing / Smishing:** Cuộc gọi điện hoặc tin nhắn SMS giả mạo IT Support yêu cầu cung cấp mã OTP.

## Câu hỏi thường gặp (FAQ)

**1. Làm thế nào để phân biệt email thật từ IT và email giả?**  
IT TechCorp **không bao giờ** yêu cầu bạn click link để xác thực mật khẩu hoặc cung cấp MFA qua email. Nếu nghi ngờ, hãy gọi hotline 8888 để xác nhận.

**2. Tôi đã báo cáo phishing nhưng không thấy hồi âm, có sao không?**  
Security Team sẽ xử lý trong vòng 4 giờ làm việc. Nếu email thực sự nguy hiểm, họ sẽ gửi cảnh báo toàn công ty. Bạn không cần phản hồi thêm.

**3. Tôi có thể tự xóa email mà không báo cáo không?**  
Nên báo cáo trước khi xóa. Việc báo cáo giúp Security Team cập nhật bộ lọc chống spam và bảo vệ đồng nghiệp khác.

**4. Nếu tôi vô tình click link khi đang dùng điện thoại cá nhân thì sao?**  
Cũng báo cáo ngay. Điện thoại cá nhân không được quản lý bởi IT, bạn cần tự cài phần mềm diệt malware (ví dụ: Malwarebytes) và đổi mật khẩu các tài khoản công ty đã đăng nhập trên đó.
