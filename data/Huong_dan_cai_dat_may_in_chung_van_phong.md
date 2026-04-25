# Hướng dẫn cài đặt máy in chung tại văn phòng

## Mục đích

Hướng dẫn này giúp nhân viên TechCorp kết nối và sử dụng hệ thống máy in chung (multifunction printers – MFP) tại các tầng văn phòng, bao gồm in ấn, quét tài liệu và quản lý hạn mức in.

## Đối tượng áp dụng

- Tất cả nhân viên làm việc tại văn phòng TechCorp (Hà Nội, TP.HCM)
- Thực tập sinh, contractor có nhu cầu in ấn

## Danh sách máy in theo khu vực

| Tòa nhà / Tầng | Tên máy in (hostname) | Model | Chức năng |
|----------------|----------------------|-------|------------|
| Tòa A - Tầng 3 | TechCorp-A3-01 | Ricoh IM C4510 | In màu, scan, photocopy |
| Tòa A - Tầng 5 | TechCorp-A5-02 | Ricoh IM C3010 | In đen trắng, scan |
| Tòa B - Tầng 2 | TechCorp-B2-03 | HP LaserJet MFP M430 | In đen trắng tốc độ cao |
| Tòa B - Tầng 7 | TechCorp-B7-04 | Ricoh IM C4510 | In màu, scan, đóng ghim |

> **Mật khẩu mặc định để xác thực in ấn:** Mã số nhân viên (ví dụ: `NV01234`). Không thay đổi mật khẩu này.

## Cài đặt máy in trên các hệ điều hành

### Trên Windows 10/11 (thiết bị công ty)

1. Kết nối vào mạng nội bộ (có dây hoặc Wi-Fi **TechCorp_5G**).
2. Mở **File Explorer**, nhập đường dẫn: `\\print.techcorp.local`
3. Danh sách máy in hiện ra. Nhấp chuột phải vào máy in bạn muốn (ví dụ `TechCorp-A3-01`) → chọn **Connect**.
4. Hệ thống tự động tải driver. Chờ thông báo "Ready".
5. Mở tài liệu bất kỳ → **Print** → chọn máy in vừa cài → in thử.

> **Nếu không thấy danh sách:** Gõ `\\print.techcorp.local` vào hộp thoại Run (Windows + R). Nếu vẫn lỗi, liên hệ IT qua số 8888.

### Trên macOS (thiết bị công ty)

1. Vào **System Settings** → **Printers & Scanners**.
2. Nhấn **Add Printer**, chọn tab **IP**.
3. Nhập:
   - **Address:** `print.techcorp.local`
   - **Protocol:** Line Printer Daemon (LPD)
   - **Queue:** tên máy in (ví dụ: `TechCorp-A3-01`)
4. Tại mục **Use** chọn **Generic PCL Printer** (hoặc tải driver Ricoh/HP từ cổng nội bộ nếu cần).
5. Nhấn **Add**. Xác thực bằng tài khoản AD (username: `techcorp\ten_dang_nhap`, password: mật khẩu AD).
6. In thử.

### Trên Ubuntu Linux (dành cho kỹ sư)

- Sử dụng CUPS: truy cập `http://localhost:631` → Administration → Add Printer → Internet Printing Protocol (IPP) → URL: `ipp://print.techcorp.local/printers/TechCorp-A3-01`
- Cần cài driver `printer-driver-ricoh` hoặc `hplip`.

## Hướng dẫn in ấn và quét tài liệu

### In ấn

- **In hai mặt (duplex):** Mặc định được bật trên tất cả máy in. Nếu muốn in một mặt, chọn "Print on one side" trong cài đặt in.
- **In màu:** Chỉ áp dụng cho máy có chức năng in màu (Ricoh). Mỗi bản in màu tính 5 điểm so với 1 điểm của in đen trắng (xem hạn mức bên dưới).
- **Đóng ghim / đục lỗ:** Chỉ có trên máy `TechCorp-B7-04`. Chọn "Staple" trong driver.

### Quét tài liệu

1. Đặt tài liệu lên khay kính hoặc ADF (Automatic Document Feeder).
2. Trên màn hình cảm ứng của máy in, chọn **Scan to Email** hoặc **Scan to Network Folder**.
3. Đăng nhập bằng mã nhân viên.
4. Chọn định dạng (PDF, JPEG) và độ phân giải (300 dpi là chuẩn).
5. Nhấn Start. File scan sẽ được gửi đến email công ty hoặc thư mục `\\files.techcorp.local\Scans\<tên bạn>`.

## Hạn mức in và báo cáo

- Mỗi nhân viên được **200 điểm in** mỗi tháng (reset vào ngày 1).
  - 1 điểm = 1 mặt A4 đen trắng.
  - 2 điểm = 1 mặt A3 đen trắng.
  - 5 điểm = 1 mặt A4 màu.
- Kiểm tra hạn mức: truy cập `https://print.techcorp.local/reports` (đăng nhập AD).
- Vượt hạn mức: yêu cầu Manager phê duyệt qua ticket IT, hoặc tự trả phí (theo bảng giá nội bộ).

## Xử lý sự cố thường gặp

| Sự cố | Giải pháp |
|-------|------------|
| Máy in báo "Offline" | Kiểm tra kết nối mạng của máy in (xem đèn Ethernet trên máy). Nếu vẫn lỗi, báo IT. |
| In ra ký tự lạ, không đúng font | Cài lại driver (tải từ `https://it-portal.techcorp.local/drivers`). |
| Mất giấy / kẹt giấy | Mở nắp máy, lấy giấy kẹt theo hướng dẫn trên màn hình. Nếu không được, gọi IT. |
| Không thể quét đến email | Kiểm tra địa chỉ email trong cấu hình máy in (phải là email công ty). Liên hệ IT nếu chưa có. |

## Câu hỏi thường gặp (FAQ)

**1. Tôi có thể in từ thiết bị cá nhân (điện thoại, laptop riêng) không?**  
Chỉ được phép in từ thiết bị công ty. Thiết bị cá nhân muốn in phải cài đặt qua cổng web print: `https://print.techcorp.local/webprint` (xác thực bằng AD) và tải file lên.

**2. Làm thế nào để in tài liệu mật mà không lưu lại trên máy in?**  
Sử dụng chức năng **Secure Print**: trong driver chọn "Print → Job Type → Secure Print", nhập mã PIN 4 số. Sau đó đến máy in, nhập PIN để in ngay – tài liệu sẽ không được lưu trong bộ nhớ máy.

**3. Tôi thấy mực in báo hết, ai có trách nhiệm thay?**  
IT sẽ thay mực định kỳ hoặc khi nhận cảnh báo từ máy. Bạn không cần tự thay, chỉ cần báo qua ticket nếu máy báo lỗi hơn 1 ngày chưa được xử lý.

**4. Hạn mức in có thể chuyển sang tháng sau không?**  
Không, điểm in không được cộng dồn. Hãy sử dụng hợp lý, in nháp nên dùng giấy tái chế ở khay 2 của máy.
