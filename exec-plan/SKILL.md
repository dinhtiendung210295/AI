---
name: exec-plan
description: Lập, cập nhật và nghiệm thu ExecPlan ngắn gọn cho người và AI cùng đọc; tổ chức tiêu chí, bằng chứng và kế hoạch con theo cấu trúc fractal cho công việc phức tạp.
---

# ExecPlan

ExecPlan là danh sách tiêu chí hoàn thành và bằng chứng nghiệm thu cho người và AI cùng đọc; chi tiết được truy vết qua liên kết.

## Plan Structure

- Ngoài tiêu đề công việc/phạm vi và nhóm cần thiết, chỉ ghi **checkbox + kết quả có thể kiểm chứng + đúng một link tới file bằng chứng nghiệm thu**. Nêu đủ điều kiện hoàn thành, tránh câu chung chung; không chứa bước thực hiện, giải thích, báo cáo hay nhật ký.
- Ưu tiên checklist; chỉ dùng bảng khi cần đối chiếu, không thêm cột thừa. Chia nhóm tùy công việc để dễ đọc, không áp khuôn cố định hoặc giới hạn số dòng/từ làm mất ý.
- Tạo kế hoạch trong repository công việc từ [mẫu ExecPlan](assets/exec-plan.md); thay placeholder, bỏ nhóm không cần.

## Evidence Structure

- Mỗi tiêu chí có một file đầu mối nghiệm thu: tiêu đề nêu đúng tiêu chí, ngay dưới là dòng **`Bằng chứng chính:`** kèm một link. File có thể liên kết nhiều tài liệu bổ trợ.
- Dùng [mẫu bằng chứng](assets/acceptance-evidence.md), không áp khuôn nội dung: kết luận, bảng, quy tắc, giải thích, báo cáo và lịch sử ra quyết định nằm tại đây hoặc các file liên kết.
- Không bắt buộc bảng tổng hợp riêng; chỉ thêm trong file bằng chứng khi chứng minh kết quả khác, không chép lại kế hoạch.

## Fractal Structure

- Áp dụng cùng cấu trúc ở mọi cấp. Chỉ tách thành file ExecPlan con khi có nhiều kết quả thành phần cần theo dõi riêng; không ép số cấp hay tạo cây thư mục hình thức.
- Cha giữ kết quả tổng thể, con giữ tiêu chí thành phần, không sao chép lên cha. Truy cập con qua file bằng chứng của cha, không thêm link trên dòng tiêu chí; kế hoạch con không thay thế bằng chứng của cha.

## Progress and Acceptance

- Phải cập nhật tiêu chí và checkbox theo thực tế; chỉ đánh dấu `[x]` khi file liên kết có bằng chứng nghiệm thu. Đo trạng thái ban đầu không chứng minh kết quả cuối.
- Con hoàn thành không tự động hoàn thành cha: phải xác minh kết quả tổng thể qua file bằng chứng của cha.

## Rules

- Mỗi thông tin chỉ trình bày ở một file; nơi khác chỉ link tới. Mỗi bằng chứng chỉ được link ở một nơi trực tiếp sử dụng.
- Đường dẫn công việc tính từ gốc repository; link tài nguyên skill tính từ thư mục chứa `SKILL.md`.
- Chỉ dùng tên hàm, lớp, mô-đun đã xác minh trong mã nguồn; không bịa đường dẫn hoặc lệnh kiểm thử.
