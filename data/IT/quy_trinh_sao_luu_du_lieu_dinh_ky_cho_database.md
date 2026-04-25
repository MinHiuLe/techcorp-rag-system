# Quy trình sao lưu dữ liệu định kỳ cho Database

## Mục đích
Quy trình này xác định các bước sao lưu tự động và thủ công các hệ cơ sở dữ liệu quan trọng của TechCorp (PostgreSQL, MongoDB) nhằm đảm bảo khả năng phục hồi dữ liệu khi xảy ra sự cố.

## Đối tượng áp dụng
- DBA và DevOps engineer chịu trách nhiệm vận hành database.
- Developer cần self-service backup cho môi trường staging.

## Hệ thống cơ sở dữ liệu
| Hệ thống | Loại DB | Môi trường | Tần suất backup |
|----------|---------|------------|-----------------|
| user-db | PostgreSQL 15 | Production | 6 giờ/lần (full) + WAL archiving |
| payment-db | PostgreSQL 15 | Production | 6 giờ/lần (full) |
| analytics-db | MongoDB 7 | Production | 24 giờ/lần |
| staging-db | PostgreSQL 15 | Staging | 24 giờ/lần (theo yêu cầu dev) |

## Quy trình tự động
1. **Cron job trên backup server** kích hoạt script `pg_backup.sh` hoặc `mongo_backup.py`.
2. **Full backup** được nén và mã hoá bằng AES-256 trước khi đẩy lên **Amazon S3 bucket** `techcorp-db-backups`.
3. **WAL files** (PostgreSQL) được stream đến S3 mỗi 5 phút để hỗ trợ Point-in-Time Recovery.
4. **Kiểm tra định kỳ:** Mỗi tuần, DBA restore bản backup mới nhất vào môi trường sandbox để xác nhận tính toàn vẹn.

## Quy trình thủ công (khi cần)
```bash
# PostgreSQL
pg_dump -U admin -h db-host -Fc mydb > /backups/mydb_$(date +%Y%m%d).dump

# MongoDB
mongodump --uri="mongodb://user:pass@host:27017" --archive=/backups/mongo_$(date +%Y%m%d).gz --gzip
```
> **Lưu ý:** Không lưu backup trực tiếp trên máy chạy database chính. Sử dụng nơi lưu trữ ngoài (off-site).

## Hạn chế và thời gian lưu trữ
- Backup production giữ trong 30 ngày, sau đó tự động xoá.
- Backup staging giữ trong 7 ngày.
- Yêu cầu giữ lâu hơn phải tạo ticket **IT-Access-Request** và được Tech Lead phê duyệt.

## Metadata (RAG)
doc_type: operational_procedure  
system: database  
category: backup_and_recovery  
security_level: internal  
embedding_priority: high

---

# Hướng dẫn sử dụng Microsoft Teams cho cuộc họp nội bộ

## Mục đích
Giúp nhân viên TechCorp sử dụng hiệu quả Microsoft Teams cho họp hành, chia sẻ màn hình và cộng tác từ xa.

## Đối tượng áp dụng
- Toàn bộ nhân viên có tài khoản Office 365 của công ty.

## Các thao tác cơ bản
1. **Lên lịch họp**  
   - Mở Outlook, tạo sự kiện, bật **Teams Meeting**.  
   - Hoặc vào Teams → Calendar → New meeting.  
2. **Tham gia họp**  
   - Click link trong email hoặc vào Teams → Calendar → Join.  
3. **Chia sẻ màn hình**  
   - Trong cuộc họp, nhấn **Share content** → chọn cửa sổ hoặc toàn màn hình.  
4. **Ghi hình cuộc họp**  
   - Nhấn **More actions** → Start recording. Bản ghi sẽ được lưu vào OneDrive/SharePoint của người tổ chức.

## Quy tắc ứng xử trong cuộc họp trực tuyến
- Bật camera khi có thể.
- Tắt micro khi không nói.
- Sử dụng tính năng **Raise hand** để phát biểu.
- Không chia sẻ thông tin mật qua màn hình nếu có khách mời bên ngoài.

## Xử lý sự cố thường gặp
| Sự cố | Giải pháp |
|-------|-----------|
| Không nghe thấy âm thanh | Kiểm tra thiết bị âm thanh trong Settings → Devices |
| Màn hình đen khi share | Tắt/bật lại hardware acceleration trong Teams Settings |
| Không vào được phòng họp | Kiểm tra lịch họp có bị huỷ, thử vào bằng phone |

## Metadata (RAG)
doc_type: end_user_guide  
system: communication  
category: collaboration_tools  
security_level: internal  
platform: microsoft_teams  
embedding_priority: medium

---

# Chính sách quản lý thiết bị di động (BYOD)

## Mục đích
Quy định việc sử dụng thiết bị cá nhân (điện thoại, máy tính bảng) để truy cập tài nguyên công ty, nhằm đảm bảo an toàn dữ liệu mà vẫn hỗ trợ làm việc linh hoạt.

## Đối tượng áp dụng
- Nhân viên, thực tập sinh có nhu cầu dùng thiết bị cá nhân cho công việc.

## Điều kiện được phép
1. Thiết bị phải cài hệ điều hành được hỗ trợ: iOS 16+, Android 13+, iPadOS 16+.
2. Phải cài đặt **Microsoft Intune Company Portal** và đăng ký thiết bị với IT.
3. Bật mã hoá toàn bộ thiết bị (FileVault/BitLocker trên máy tính, encryption mặc định trên mobile).
4. Cài đặt phần mềm diệt virus theo yêu cầu (CrowdStrike Falcon cho mobile nếu được cấp).

## Các hành vi bị cấm
- Chia sẻ mã PIN/mật khẩu thiết bị với người khác.
- Cài đặt ứng dụng từ nguồn không chính thức (third-party app store cho Android).
- Lưu dữ liệu công ty vào các dịch vụ đám mây cá nhân (iCloud, Google Drive cá nhân).
- Kết nối vào mạng Wi-Fi công cộng không an toàn khi đang truy cập VPN.

## Quy trình báo mất thiết bị
1. Ngay khi phát hiện mất, gọi hotline **8888** hoặc gửi email `security@techcorp.com`.
2. IT sẽ tiến hành **remote wipe** toàn bộ dữ liệu công ty trên thiết bị qua Intune.
3. Nhân viên phải thông báo cho quản lý trực tiếp.

## Metadata (RAG)
doc_type: it_policy  
system: mobile_device_management  
category: byod  
security_level: internal  
compliance: endpoint_protection  
embedding_priority: high

---

# Hướng dẫn cài đặt và cấu hình máy chủ ảo (VM) cho developer

## Mục đích
Tài liệu này hướng dẫn developer tạo và quản lý máy ảo trên nền tảng **TechCorp Private Cloud (vSphere)** để phục vụ phát triển và kiểm thử.

## Đối tượng áp dụng
- Developer, QA Engineer cần môi trường biệt lập.

## Yêu cầu trước
- Đã được cấp quyền truy cập **vSphere Client** (ticket tạo qua Jira project `IT-Access-Request`).
- VPN hoặc mạng nội bộ để kết nối đến `vcsa.techcorp.local`.

## Các bước tạo VM
1. Đăng nhập vào **vSphere Client** tại `https://vcsa.techcorp.local/ui`.
2. Chọn **Hosts and Clusters** → chuột phải vào Resource Pool của team → **New Virtual Machine**.
3. Chọn **Create a new virtual machine**.
4. Cấu hình:
   - **Name:** `dev-<tên_bạn>-<mô_tả>` (vd: `dev-nguyenvana-api-test`)
   - **Datastore:** `SSD_Production_01`
   - **Guest OS:** Ubuntu 22.04 LTS (hoặc Windows Server 2022 nếu cần)
   - **CPU:** 4 vCPU (tối đa)
   - **Memory:** 8 GB (tối đa)
   - **Disk:** 100 GB (mặc định)
5. Gắn ISO cài đặt từ thư viện Content Library `ISO_Library`.
6. Sau khi tạo, bật nguồn, mở **Web Console** để cài OS.
7. Cấu hình IP tĩnh theo subnet của team.

## Quy định sử dụng
- VM không dùng quá 3 ngày sẽ tự động tắt (có thể báo IT để giữ lâu hơn).
- Không cài đặt phần mềm không phục vụ công việc.
- Tự chịu trách nhiệm backup dữ liệu quan trọng, VM có thể bị reset hàng tháng.
