# Hướng dẫn lập và thực thi ExecPlan
- Mục đích: vừa là kế hoạch triển khai, vừa là nhật ký tiến độ cho những công việc phức tạp, kéo dài hoặc có nhiều bước phụ thuộc
- Cụ thể: Khi nhắc tới tệp, ghi đường dẫn **tính từ thư mục gốc repository**. Khi nhắc tới hàm, lớp hoặc mô-đun, sử dụng tên chính xác nếu đã xác minh trong mã nguồn. Không bịa đường dẫn hay lệnh kiểm thử.
- Là tài liệu sống: Trong quá trình thực thi,  phải cập nhật ExecPlan để phản ánh cả hiện tại, lịch sử ra quyết định


## Mẫu
---

# [Tên công việc]
**Cập nhật gần nhất:** [YYYY-MM-DD HH:mm, múi giờ]  


## Purpose / Big Picture — Mục tiêu và bức tranh tổng thể

[Giải thích vấn đề từ góc nhìn người sử dụng. Mô tả hành vi trước và sau thay đổi, lợi ích đạt được và cách người dùng tự quan sát kết quả.]

## Progress — Tiến độ

- [ ] [Mốc kèm điều kiện hoàn thành].
- [ ] [Mốc kèm điều kiện hoàn thành].
- [ ] [Kiểm thử và nghiệm thu cuối].

Cập nhật trạng thái ngay khi có bằng chứng hoàn thành hoàn toàn một mốc


## Plan of Work — Kế hoạch thực hiện

**[Tên mốc]** [các tệp/hàm cụ thể, kết quả nhìn thấy được và cách kiểm chứng độc lập.]

**[Tên mốc]** [Tiếp nối từ milestone trước, mô tả công việc và bằng chứng hoàn tất.]


## Outcomes & Retrospective — Kết quả và tổng kết

[Bổ sung khi đóng từng mốc lớn. Đối chiếu kết quả với mục tiêu ban đầu; ghi điều đã đạt, chưa đạt, kiểm thử đã chạy, nợ kỹ thuật và bài học.]

## Nhật ký
Bảng gồm có các cột:
- Ngày giờ: 
- Loại: Bất ngờ (nhận ra plan bị sai hoặc chưa có thông tin mới quan trọng có thể làm đổi hướng plan ), Quyết định của người dùng 
- Bằng chứng: Lệnh, log, tệp, kết quả test, câu hỏi người dùng và lựa chọn đề xuất
- Hành động đối ứng: Đã làm gì
