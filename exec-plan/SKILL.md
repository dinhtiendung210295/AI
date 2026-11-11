---
name: exec-plan
description: Lập, cập nhật và nghiệm thu ExecPlan ngắn gọn cho người và AI cùng đọc; tổ chức tiêu chí, bằng chứng và kế hoạch con theo cấu trúc fractal cho công việc phức tạp.
---

# ExecPlan

## Purpose

ExecPlan là danh sách tiêu chí hoàn thành và bằng chứng nghiệm thu dùng chung cho người và AI. Giữ lớp tổng quan ngắn gọn; cho phép đọc sâu qua các file liên kết khi cần.

## Plan Structure

- Ngoài tiêu đề nêu công việc, phạm vi và các nhóm cần thiết, ExecPlan chỉ gồm tiêu chí hoàn thành. Mỗi tiêu chí có một checkbox và đúng một link tới file bằng chứng nghiệm thu duy nhất.
- Mỗi tiêu chí diễn đạt một kết quả có thể kiểm chứng, đủ rõ điều kiện hoàn thành; không mô tả các bước thực hiện hoặc dùng kết luận chung chung như “hoàn thiện”.
- Ưu tiên checklist để người đọc dễ quét và AI dễ cập nhật. Chỉ dùng bảng khi cần đối chiếu; không tự thêm các cột quản lý không cần thiết.
- Chỉ chia nhóm khi giúp đọc dễ hơn. Số nhóm, tên nhóm và số tiêu chí do công việc quyết định, không theo danh sách cố định.
- Rút gọn bằng cách giới hạn nội dung, không cắt mất điều kiện nghiệm thu hoặc áp giới hạn cứng số dòng, số từ.
- Dùng [mẫu ExecPlan](assets/exec-plan.md) để tạo kế hoạch trong repository đang thực hiện công việc; thay placeholder bằng nội dung thực tế, bỏ nhóm không cần thiết.

## Evidence Structure

- Một file bằng chứng là đầu mối nghiệm thu duy nhất của một tiêu chí, không có nghĩa tiêu chí chỉ được có một tài liệu chứng minh.
- Dùng [mẫu bằng chứng](assets/acceptance-evidence.md) làm điểm khởi đầu; không áp đặt khuôn nội dung cố định.
- Tiêu đề nêu đúng tiêu chí được chứng minh. Ngay dưới tiêu đề có một dòng **`Bằng chứng chính:`** kèm link tới một bằng chứng chính.
- Nội dung tùy tiêu chí: kết luận, bảng, quy tắc hoặc danh sách. Giải thích, báo cáo, lịch sử ra quyết định và link tới bằng chứng bổ trợ nằm trong file này hoặc các file được liên kết từ đây, không nằm trong ExecPlan.

## Fractal Structure

- Ở mọi cấp, ExecPlan tuân theo cùng cấu trúc: tiêu chí có thể kiểm chứng, checkbox và một link bằng chứng.
- Khi một tiêu chí có nhiều kết quả thành phần cần theo dõi riêng, có thể phân rã thành một file ExecPlan con. Không bắt buộc số cấp hoặc tạo cây thư mục chỉ để đủ hình thức.
- Kế hoạch cha giữ kết quả tổng thể; kế hoạch con giữ tiêu chí thành phần. Không chép toàn bộ tiêu chí con lên cha.
- Tiêu chí cha vẫn chỉ link tới file bằng chứng của nó. File bằng chứng này liên kết tới ExecPlan con và các bằng chứng bổ trợ cần thiết; không thêm link kế hoạch con trên dòng tiêu chí cha.
- ExecPlan con theo dõi các kết quả thành phần, không thay thế bằng chứng nghiệm thu của tiêu chí cha.

## Progress and Acceptance

- Phải cập nhật tiêu chí và checkbox theo tiến độ thực tế. Checkbox thể hiện trạng thái nghiệm thu; nhật ký và lịch sử ra quyết định được lưu trong các file liên kết.
- Chỉ đánh dấu `[x]` khi tiêu chí có bằng chứng trong file liên kết.
- Hoàn thành tiêu chí con là cơ sở để nghiệm thu cha, không tự động khiến tiêu chí cha được đánh dấu `[x]`. Phải xác minh kết quả tổng thể qua file bằng chứng của cha.
- File chỉ đo trạng thái ban đầu (ví dụ kết quả quét) không dùng làm bằng chứng cho kết quả cuối.
- Không bắt buộc tạo bảng tổng hợp kết quả riêng vì ExecPlan đã tổng hợp tiêu chí và trạng thái. Chỉ thêm bảng trong file bằng chứng khi cần chứng minh một kết quả khác, không sao chép lại kế hoạch.

## Rules

- ExecPlan chỉ chứa tiêu chí hoàn thành; không chứa hướng dẫn từng bước, nội dung chi tiết, báo cáo, bảng số liệu hay nhật ký.
- Mỗi thông tin chỉ được trình bày ở một file; file khác chỉ link tới.
- Mỗi bằng chứng chỉ được link ở một nơi trực tiếp sử dụng.
- Khi nhắc tới tệp của công việc, ghi đường dẫn tính từ thư mục gốc repository.
- Các liên kết tài nguyên trong skill này được tính từ thư mục chứa `SKILL.md`.
- Khi nhắc tới hàm, lớp hoặc mô-đun, sử dụng tên chính xác nếu đã xác minh trong mã nguồn.
- Không bịa đường dẫn hay lệnh kiểm thử.
