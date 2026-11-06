# Hướng dẫn lập và thực thi ExecPlan
- Mục đích: vừa là kế hoạch triển khai, vừa là nhật ký tiến độ cho những công việc phức tạp, kéo dài hoặc có nhiều bước phụ thuộc
- Cụ thể: Khi nhắc tới tệp, ghi đường dẫn **tính từ thư mục gốc repository**. Khi nhắc tới hàm, lớp hoặc mô-đun, sử dụng tên chính xác nếu đã xác minh trong mã nguồn. Không bịa đường dẫn hay lệnh kiểm thử.
- Là tài liệu sống: Trong quá trình thực thi,  phải cập nhật ExecPlan để phản ánh cả hiện tại, lịch sử ra quyết định

# Mẫu

## Quy ước cốt lõi

- ExecPlan chỉ chứa **tiêu chí hoàn thành**, không chứa hướng dẫn từng bước.
- Mỗi tiêu chí là một checkbox và **một link** tới file chứa nội dung chi tiết.
- Không chép báo cáo, bảng số liệu hay nhật ký vào ExecPlan.
- Chỉ đánh dấu `[x]` khi tiêu chí có bằng chứng trong file liên kết.
- Mỗi file nghiệm thu có **một bằng chứng chính** đặt ngay dưới tiêu đề.
- Mỗi thông tin chỉ được trình bày ở **một file**; file khác chỉ link tới.
- Mỗi bằng chứng chỉ được link ở **một nơi trực tiếp sử dụng**.
- File chỉ đo trạng thái ban đầu (ví dụ kết quả quét) không dùng làm bằng chứng cho kết quả cuối.
- Kết quả cuối phải có bảng tổng hợp riêng, dẫn lại từ các bằng chứng đã duyệt.
- Khi nhắc tới tệp, ghi đường dẫn **tính từ thư mục gốc repository**.

## Dạng tối thiểu của một ExecPlan

```markdown
# <Tên công việc> — <phạm vi/kỳ>

Chỉ đánh dấu `[x]` khi tiêu chí có bằng chứng trong file liên kết.
Nội dung chi tiết và báo cáo không chép vào ExecPlan.

## <Tên nhóm công việc>

- [ ] <Tiêu chí hoàn thành> — [<Tên bằng chứng>](<đường-dẫn>).
- [ ] <Tiêu chí hoàn thành> — [<Tên bằng chứng>](<đường-dẫn>).
```

Số nhóm, tên nhóm và số tiêu chí mỗi nhóm do công việc quyết định; không cần theo một danh sách cố định.

## Dạng tối thiểu của một file bằng chứng nghiệm thu

Không đặt khuôn cố định. File chỉ cần:

- Tiêu đề nêu đúng tiêu chí mà nó chứng minh.
- Một dòng **`Bằng chứng chính:`** kèm link.
- Phần nội dung tuỳ tiêu chí: bảng, quy tắc, danh sách hoặc kết luận.
- Các link bằng chứng bổ trợ nếu cần truy vết.

```markdown
# <Tên tiêu chí>

> **Bằng chứng chính:** [<Tên bằng chứng>](<đường-dẫn>) — <một câu nói file này chứng minh điều gì>.

<Nội dung tự do: bảng, quy tắc, danh sách hoặc kết luận.>

## Bằng chứng bổ trợ

- [<Tên file>](<đường-dẫn>)
```
