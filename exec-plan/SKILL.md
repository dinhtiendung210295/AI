---
name: exec-plan
description: Lập, cập nhật và nghiệm thu ExecPlan cho công việc phức tạp, kéo dài hoặc có nhiều bước phụ thuộc; quản lý tiêu chí hoàn thành và bằng chứng liên kết.
---

# ExecPlan

## Purpose

ExecPlan vừa là kế hoạch triển khai, vừa là nhật ký tiến độ. Đây là tài liệu sống, phải được cập nhật trong quá trình thực thi để phản ánh hiện tại và lịch sử ra quyết định. Nội dung chi tiết được lưu trong các file liên kết, không chép vào ExecPlan.

## Workflow

### 1. Create

- Xác định phạm vi công việc và các tiêu chí hoàn thành.
- Dùng [mẫu ExecPlan](assets/exec-plan.md) để tạo kế hoạch trong repository đang thực hiện công việc; thay các placeholder bằng nội dung thực tế.
- Số nhóm, tên nhóm và số tiêu chí mỗi nhóm do công việc quyết định; không cần theo một danh sách cố định.
- Mỗi tiêu chí là một checkbox và một link tới file chứa nội dung chi tiết, bằng chứng nghiệm thu của tiêu chí đó.

### 2. Update

- Cập nhật tiêu chí và trạng thái theo tiến độ thực tế.
- Lưu nội dung chi tiết, báo cáo và lịch sử ra quyết định trong các file liên kết; không chép báo cáo, bảng số liệu hay nhật ký vào ExecPlan.
- Mỗi thông tin chỉ được trình bày ở một file; file khác chỉ link tới.
- Mỗi bằng chứng chỉ được link ở một nơi trực tiếp sử dụng.

### 3. Accept

- Khi tạo file nghiệm thu, dùng [mẫu bằng chứng](assets/acceptance-evidence.md) làm điểm khởi đầu, không áp đặt khuôn nội dung cố định.
- Tiêu đề phải nêu đúng tiêu chí mà file chứng minh.
- Mỗi file nghiệm thu có một dòng **`Bằng chứng chính:`** kèm link ngay dưới tiêu đề.
- Nội dung tùy tiêu chí: bảng, quy tắc, danh sách hoặc kết luận. Thêm link bằng chứng bổ trợ nếu cần truy vết.
- Chỉ đánh dấu `[x]` khi tiêu chí có bằng chứng trong file liên kết.
- File chỉ đo trạng thái ban đầu (ví dụ kết quả quét) không dùng làm bằng chứng cho kết quả cuối.
- Kết quả cuối phải có bảng tổng hợp riêng, dẫn lại từ các bằng chứng đã duyệt.

## Rules

- ExecPlan chỉ chứa tiêu chí hoàn thành, không chứa hướng dẫn từng bước.
- Khi nhắc tới tệp của công việc, ghi đường dẫn tính từ thư mục gốc repository. Các liên kết tài nguyên trong skill này được tính từ thư mục chứa `SKILL.md`.
- Khi nhắc tới hàm, lớp hoặc mô-đun, sử dụng tên chính xác nếu đã xác minh trong mã nguồn.
- Không bịa đường dẫn hay lệnh kiểm thử.
